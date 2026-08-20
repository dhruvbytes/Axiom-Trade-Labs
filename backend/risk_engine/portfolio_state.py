from typing import List, Dict

# ==========================================
# 1. PROJECTED PORTFOLIO CONCENTRATION
# ==========================================
def calculate_projected_concentration(
    current_portfolio_equity: float,
    current_positions: List[Dict[str, float]], 
    proposed_symbol: str, 
    proposed_quantity: float, 
    proposed_price: float,
    action: str
) -> float:
    """
    Calculates the projected weight (concentration) of a specific asset in the portfolio 
    IF the proposed trade goes through.
    
    Inputs:
    - current_portfolio_equity: Total value of the account (cash + positions).
    - current_positions: List of dicts, e.g., [{'symbol': 'AAPL', 'market_value': 1500.0}, ...]
    - proposed_symbol: e.g., 'AAPL'
    - proposed_quantity: The number of shares the AI wants to trade.
    - proposed_price: The estimated price per share.
    - action: 'BUY' or 'SELL'
    
    Returns:
    - float: The projected weight as a decimal (e.g., 0.18 for 18%).
    """
    if current_portfolio_equity <= 0:
        return 0.0
    
    # 1. Find existing value of the symbol in the portfolio
    existing_value = 0.0
    for pos in current_positions:
        if pos.get('symbol') == proposed_symbol:
            existing_value = float(pos.get('market_value', 0.0))
            break
            
    # 2. Calculate the value of the proposed trade
    proposed_value = proposed_quantity * proposed_price
    
    # 3. Calculate new value based on action
    if action.upper() == 'BUY':
        projected_value = existing_value + proposed_value
    elif action.upper() == 'SELL':
        projected_value = existing_value - proposed_value
        # You can't have negative concentration in our long-only MVP
        if projected_value < 0:
            projected_value = 0.0
    else:
        # HOLD or unknown action, concentration remains unchanged
        projected_value = existing_value
        
    # 4. Calculate the projected concentration weight
    projected_weight = projected_value / current_portfolio_equity
    
    return round(projected_weight, 4)

# ==========================================
# 2. ATR POSITION SIZING LOGIC
# ==========================================
def calculate_max_safe_shares(
    account_equity: float,
    risk_per_trade_pct: float,
    asset_atr_14: float,
    atr_multiplier: float = 2.0
) -> int:
    """
    Determines the maximum number of shares allowed based on volatility.
    This is a policy-based risk-sizing approximation, NOT a guarantee of maximum actual loss.
    
    Formulas:
    Risk Budget = Total Equity * Risk Per Trade (%)
    Stop Distance ($) = Multiplier * ATR_14
    Max Safe Shares = Floor(Risk Budget / Stop Distance)
    """
    if asset_atr_14 <= 0 or atr_multiplier <= 0:
        return 0 # Cannot safely calculate sizing without volatility data
        
    # 1. Calculate the absolute dollar amount we are willing to risk
    risk_budget = account_equity * risk_per_trade_pct
    
    # 2. Calculate the assumed stop distance based on volatility
    stop_distance = atr_multiplier * asset_atr_14
    
    # 3. Calculate max shares (using floor division to be conservative)
    max_shares = int(risk_budget // stop_distance)
    
    return max_shares