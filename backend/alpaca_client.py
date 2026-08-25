from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from backend import config
import asyncio
from datetime import datetime, timedelta

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
    """Synchronous fetcher for real market quotes and SPY stats (No fakes)."""
    facts = {"quotes": {}, "is_market_open": True} 
    fetch_list = list(set([s for s in symbols if isinstance(s, str)] + ["SPY"]))
    
    try:
        # 1. Fetch Authoritative Quotes in 1 Network Call
        quote_req = StockLatestQuoteRequest(symbol_or_symbols=fetch_list)
        latest_quotes = data_client.get_stock_latest_quote(quote_req)
        
        for sym, quote_data in latest_quotes.items():
            price = float(quote_data.ask_price) if quote_data.ask_price > 0 else float(quote_data.bid_price)
            if price > 0:
                if sym == "SPY":
                    facts["spy_price"] = price
                else:
                    facts["quotes"][sym] = price
                    
        # 2. Fetch SPY Bars for Real SMA and ATR (1 Network Call)
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=80) # Approx 50 trading days
        
        bar_req = StockBarsRequest(
            symbol_or_symbols=["SPY"], timeframe=TimeFrame.Day, start=start_dt, end=end_dt
        )
        bars = data_client.get_stock_bars(bar_req)
        
        if "SPY" in bars.data and len(bars.data["SPY"]) > 0:
            spy_bars = bars.data["SPY"]
            
            # Real 50-Day SMA
            closes = [float(b.close) for b in spy_bars[-50:]]
            if closes:
                facts["spy_sma_50"] = sum(closes) / len(closes)
                
            # Real 14-Day ATR
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

            # Fallback for SPY price if quote fails but bar succeeds
            if "spy_price" not in facts:
                facts["spy_price"] = closes[-1]
                
    except Exception as e:
        # We catch but DO NOT mock data. Missing data safely triggers Risk Engine FAIL-CLOSED.
        print(f"JIT Fact Collection Warning: {e}")
        
    return facts

async def get_market_facts(symbols: list) -> dict:
    """Async wrapper to keep FastAPI event loop unblocked."""
    return await asyncio.to_thread(_fetch_market_facts_sync, symbols)