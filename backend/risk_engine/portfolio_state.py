# backend/risk_engine/portfolio_state.py
from typing import List, Dict
from backend.risk_engine.risk_models import UniversalTradeProposal, SystemFacts, AssetClass, Side

# ==========================================
# 1. PROJECTED PORTFOLIO CONCENTRATION (HYBRID LOGIC)
# ==========================================
def calculate_projected_concentration(
    proposal: UniversalTradeProposal,
    facts: SystemFacts
) -> float:
    """
    Calculates the projected weight (concentration) of the primary asset.
    - Equity uses GROSS notional exposure.
    - Options use NET notional exposure (hedged spreads).
    """
    if facts.account.equity <= 0:
        return 0.0
    
    # 1. Find existing exposure of the symbol in the portfolio
    existing_value = 0.0
    for pos in facts.current_positions:
        if pos.get('symbol') == proposal.intent.primary_underlying:
            existing_value = float(pos.get('market_value', 0.0))
            break
            
    # 2. Separate logic for Equity and Options
    proposed_equity_notional = 0.0
    proposed_option_notional = 0.0
    
    for leg in proposal.intent.legs:
        sym = leg.instrument.underlying_symbol or proposal.intent.primary_underlying
        
        if leg.instrument.asset_class == AssetClass.EQUITY:
            price = 0.0
            if sym in facts.equity_quotes:
                price = facts.equity_quotes[sym].price
            
            # 🚀 STOCKS: Always GROSS (No direction netting)
            proposed_equity_notional += leg.ratio_qty * price
            
        else:
            # 🚀 OPTIONS: Apply Direction (+1 for Buy, -1 for Sell) for Spread Netting
            direction = 1 if leg.side == Side.BUY else -1
            contract_key = f"{sym}_{leg.instrument.strike}_{leg.instrument.option_type.value}"
            multiplier = 100
            
            if contract_key in facts.option_quotes:
                multiplier = facts.option_quotes[contract_key].multiplier
            
            strike = leg.instrument.strike or 0.0
            proposed_option_notional += (leg.ratio_qty * strike * multiplier * direction)

    # 3. Combine: Gross Equity + Absolute Netted Options
    total_proposed_exposure = (proposed_equity_notional + abs(proposed_option_notional)) * proposal.intent.package_quantity
    
    projected_value = existing_value + total_proposed_exposure
    
    # 4. Calculate the projected concentration weight
    projected_weight = projected_value / facts.account.equity
    return round(projected_weight, 4)

# ==========================================
# 2. ATR POSITION SIZING LOGIC (PRESERVED AS-IS)
# ==========================================
def calculate_max_safe_shares(
    account_equity: float,
    risk_per_trade_pct: float,
    asset_atr_14: float,
    atr_multiplier: float = 2.0
) -> int:
    """
    Determines the maximum number of shares allowed based on volatility.
    """
    if asset_atr_14 <= 0 or atr_multiplier <= 0:
        return 0 
        
    risk_budget = account_equity * risk_per_trade_pct
    stop_distance = atr_multiplier * asset_atr_14
    max_shares = int(risk_budget // stop_distance)
    
    return max_shares