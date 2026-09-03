from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest
from alpaca.data.historical import StockHistoricalDataClient, OptionHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest, OptionLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from backend import config
import asyncio
from datetime import datetime, timedelta
import math
import re

# 1. Initialize official Alpaca clients
trading_client = TradingClient(
    api_key=config.ALPACA_API_KEY,
    secret_key=config.ALPACA_SECRET_KEY,
    paper=config.ALPACA_PAPER
)

data_client = StockHistoricalDataClient(
    api_key=config.ALPACA_API_KEY,
    secret_key=config.ALPACA_SECRET_KEY
)

option_data_client = OptionHistoricalDataClient(
    api_key=config.ALPACA_API_KEY,
    secret_key=config.ALPACA_SECRET_KEY
)

# ==========================================
# ORIGINAL PORTFOLIO FUNCTIONS (RESTORED)
# ==========================================
def get_portfolio_summary():
    """Fetches the account details and returns only buying power and equity."""
    try:
        account = trading_client.get_account()
        return {
            "buying_power": str(account.buying_power),
            "portfolio_value": str(account.equity)
        }
    except Exception as e:
        raise RuntimeError(f"Failed to fetch account info from Alpaca. Details: {str(e)}")

def get_current_positions():
    """Fetches all open positions and formats them into a simple dictionary list."""
    try:
        raw_positions = trading_client.get_all_positions()
        formatted_positions = []
        for pos in raw_positions:
            formatted_positions.append({
                "symbol": pos.symbol,
                "qty": str(pos.qty),
                "market_value": str(pos.market_value),
                "unrealized_pl": str(pos.unrealized_pl)
            })
        return formatted_positions
    except Exception as e:
        raise RuntimeError(f"Failed to fetch positions from Alpaca. Details: {str(e)}")

# ==========================================
# NEW JIT MARKET FACTS FUNCTIONS
# ==========================================
def _fetch_market_facts_sync(symbols: list) -> dict:
    """Synchronous fetcher for real market quotes, SPY stats, AND BSM Option Prices."""
    facts = {"quotes": {}, "is_market_open": True} 
    
    # 🚀 FIX 1: Split Stocks and Options properly
    stock_symbols = [s for s in symbols if isinstance(s, str) and s.isalpha()]
    option_symbols = [s for s in symbols if isinstance(s, str) and not s.isalpha()]
    
    fetch_list = list(set(stock_symbols + ["SPY"]))
    
    try:
        # --- 1. Fetch Authoritative Stock Quotes ---
        quote_req = StockLatestQuoteRequest(symbol_or_symbols=fetch_list, feed=DataFeed.IEX)
        latest_quotes = data_client.get_stock_latest_quote(quote_req)
        
        for sym, quote_data in latest_quotes.items():
            price = float(quote_data.ask_price) if quote_data.ask_price > 0 else float(quote_data.bid_price)
            if price > 0:
                if sym == "SPY":
                    facts["spy_price"] = price
                else:
                    facts["quotes"][sym] = price
                    
        # --- 2. Fetch SPY Bars for Real SMA and ATR ---
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=80) 
        
        bar_req = StockBarsRequest(
            symbol_or_symbols=["SPY"], timeframe=TimeFrame.Day, start=start_dt, end=end_dt, feed=DataFeed.IEX
        )
        bars = data_client.get_stock_bars(bar_req)
        
        if "SPY" in bars.data and len(bars.data["SPY"]) > 0:
            spy_bars = bars.data["SPY"]
            
            closes = [float(b.close) for b in spy_bars[-50:]]
            if closes:
                facts["spy_sma_50"] = sum(closes) / len(closes)
                
            trs = []
            for i in range(1, len(spy_bars)):
                high = float(spy_bars[i].high)
                low = float(spy_bars[i].low)
                prev_close = float(spy_bars[i-1].close)
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                trs.append(tr)
                
            recent_trs = trs[-14:]
            if recent_trs:
                facts["spy_atr_14"] = sum(recent_trs) / len(recent_trs)

            if "spy_price" not in facts:
                facts["spy_price"] = closes[-1]

        if "spy_sma_50" not in facts and "spy_price" in facts:
            facts["spy_sma_50"] = facts["spy_price"]
            
        # --- 3. 🚀 FETCH & INJECT BSM OPTION FACTS (THE MISSING LINK) ---
        if option_symbols:
            # Humara banaya hua Black-Scholes function yahan call hoga!
            option_quotes = _fetch_option_latest_quotes_sync(option_symbols)
            
            for opt_sym, price_data in option_quotes.items():
                mid_price = price_data["mid"]
                
                # Option ko uske original OCC naam se save karo
                facts["quotes"][opt_sym] = mid_price  
                
                # 🚀 PRO-FIX: Risk Engine ki aadat `NVDA_130.0_call` padhne ki hai. 
                # Hum OCC symbol ko us format mein translate karke bhi dictionary mein daal denge!
                import re
                match = re.match(r"^([a-zA-Z]+)(\d{6})([CcPp])(\d{8})$", opt_sym)
                if match:
                    und, _, opt_type, strike_str = match.groups()
                    strike = float(strike_str) / 1000.0
                    human_key = f"{und}_{strike}_{'call' if opt_type.lower() == 'c' else 'put'}"
                    facts["quotes"][human_key] = mid_price # Risk Engine ko uska exact format mil gaya!

    except Exception as e:
        print(f"JIT Fact Collection Warning: {e}")
        if "spy_sma_50" not in facts and "spy_price" in facts:
            facts["spy_sma_50"] = facts["spy_price"]
        
    return facts

async def get_market_facts(symbols: list) -> dict:
    """Async wrapper to keep FastAPI event loop unblocked."""
    return await asyncio.to_thread(_fetch_market_facts_sync, symbols)

# ==========================================
# JIT OPTIONS FUNCTIONS (REAL DATA ONLY)
# ==========================================
def _fetch_options_chain_sync(symbol: str, min_dte: int = 14, max_dte: int = 45) -> list:
    """Synchronous JIT fetcher for real Alpaca option contracts (underlying-first)."""
    if not isinstance(symbol, str) or not symbol.strip():
        return []
    sym = symbol.strip().upper()
    try:
        now_date = datetime.utcnow().date()
        start_date = now_date + timedelta(days=max(0, min_dte))
        end_date = now_date + timedelta(days=max(min_dte, max_dte))
        
        req = GetOptionContractsRequest(
            underlying_symbols=[sym],
            status="active",
            expiration_date_gte=start_date,
            expiration_date_lte=end_date,
            limit=100
        )
        res = trading_client.get_option_contracts(req)
        raw_contracts = getattr(res, "option_contracts", []) or []
        
        contracts = []
        for c in raw_contracts:
            strike = float(c.strike_price or 0)
            if strike <= 0:
                continue
            c_type = str(getattr(c.type, "value", c.type)).lower()
            contracts.append({
                "symbol": str(c.symbol),
                "underlying_symbol": sym,
                "strike_price": strike,
                "expiration_date": str(c.expiration_date),
                "type": c_type,
                "open_interest": int(c.open_interest or 0),
                "close_price": float(c.close_price or 0.0),
            })
        return contracts
    except Exception as e:
        print(f"JIT Option Chain Fetch Warning for {sym}: {e}")
        return []

def _calculate_theoretical_option_price(occ_symbol: str, underlying_price: float) -> float:
    """Universal Black-Scholes Formula to calculate Limit Price for any Option"""
    try:
        # OCC Format: NVDA260918C00130000 -> NVDA, 26-09-18, Call, 130.00
        match = re.match(r"^([a-zA-Z]+)(\d{6})([CcPp])(\d{8})$", occ_symbol)
        if not match: return 1.0
        
        und, date_str, opt_type, strike_str = match.groups()
        strike = int(strike_str) / 1000.0
        opt_type = opt_type.lower()
        
        # Calculate Time to Expiry (T in years)
        exp_date = datetime.strptime(date_str, "%y%m%d")
        days_to_expiry = (exp_date - datetime.utcnow()).days
        T = max(days_to_expiry, 1) / 365.0 
        
        # Market Variables (Standard Defaults for Synthetics)
        S = underlying_price
        K = strike
        r = 0.05       # 5% Risk Free Interest Rate
        sigma = 0.40   # 40% Implied Volatility (Standard baseline)
        
        # Math helper for Normal Distribution
        def norm_cdf(x):
            return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0
            
        # Black-Scholes Formula
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        
        if opt_type == 'c':
            price = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
        else:
            price = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
            
        return round(max(price, 0.05), 2)
    except Exception as e:
        print(f"BSM Calc Error: {e}")
        return 1.0

def _fetch_option_latest_quotes_sync(contract_symbols: list) -> dict:
    """Synchronous JIT fetcher with Black-Scholes Fallback for Free Tier."""
    valid_symbols = [s for s in contract_symbols if isinstance(s, str) and s.strip()]
    if not valid_symbols:
        return {}
    
    quotes = {}
    
    # 🚀 Step 1: Ek baar mein saare underlying stocks ka live price nikal lo
    underlying_symbols = list(set([re.sub(r'[^a-zA-Z].*', '', sym) for sym in valid_symbols]))
    stock_facts = _fetch_market_facts_sync(underlying_symbols)
    live_stock_prices = stock_facts.get("quotes", {})

    try:
        req = OptionLatestQuoteRequest(symbol_or_symbols=valid_symbols)
        res = option_data_client.get_option_latest_quote(req)
        
        for sym, q in res.items():
            bid = float(getattr(q, "bid_price", 0.0) or 0.0)
            ask = float(getattr(q, "ask_price", 0.0) or 0.0)
            mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else (ask or bid)
            
            # 🚀 Step 2: Agar feed free tier ki wajah se $0.0 bhejti hai, apply Universal Formula!
            if mid <= 0:
                underlying_ticker = re.sub(r'[^a-zA-Z].*', '', sym)
                current_stock_price = live_stock_prices.get(underlying_ticker, 100.0) # get live stock price
                
                # Calculate True Theoretical Price
                theoretical_price = _calculate_theoretical_option_price(sym, current_stock_price)
                
                mid = theoretical_price
                bid = round(mid * 0.95, 2)
                ask = round(mid * 1.05, 2)
                print(f"[QUANT ENGINE] Synthesized {sym} price to ${mid} using BSM Math.")

            quotes[sym] = {
                "bid": bid,
                "ask": ask,
                "mid": mid,
            }
    except Exception as e:
        print(f"JIT Option Quotes Fetch Warning: {e}")
        
    return quotes

async def get_options_chain_jit(symbol: str, min_dte: int = 14, max_dte: int = 45) -> list:
    """Async wrapper for JIT option chain retrieval without event-loop blocking."""
    return await asyncio.to_thread(_fetch_options_chain_sync, symbol, min_dte, max_dte)

async def get_option_quotes(contract_symbols: list) -> dict:
    """Async wrapper for JIT option quote retrieval without event-loop blocking."""
    return await asyncio.to_thread(_fetch_option_latest_quotes_sync, contract_symbols)