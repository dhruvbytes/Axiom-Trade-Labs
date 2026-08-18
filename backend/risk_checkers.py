from backend.risk_models import RiskDecision, RiskGateResult, SystemHardLimits, UserRiskProfile
from backend.portfolio_state import calculate_projected_concentration, calculate_max_safe_shares

# ==========================================
# 1. SEMANTIC GATE
# ==========================================
def check_semantic_gate(action: str, quantity: float, price: float) -> RiskGateResult:
    """Validates if the proposal makes logical sense (positive quantity, valid action)."""
    if action.upper() not in ["BUY", "SELL", "HOLD"]:
        return RiskGateResult(
            gate_name="Semantic Gate", status=RiskDecision.BLOCK,
            explanation=f"Invalid action '{action}'. Must be BUY, SELL, or HOLD."
        )
    if action.upper() in ["BUY", "SELL"] and (quantity <= 0 or price <= 0):
        return RiskGateResult(
            gate_name="Semantic Gate", status=RiskDecision.BLOCK,
            measured_value=f"Qty: {quantity}, Price: {price}",
            explanation="Quantity and price must be greater than zero for active trades."
        )
    
    return RiskGateResult(gate_name="Semantic Gate", status=RiskDecision.ALLOW, explanation="Proposal semantics are valid.")

# ==========================================
# 2. ACCOUNT / STATE GATE
# ==========================================
def check_account_state_gate(action: str, quantity: float, price: float, buying_power: float) -> RiskGateResult:
    """Validates if there is enough buying power for a BUY order."""
    if action.upper() == "BUY":
        required_cash = quantity * price
        if required_cash > buying_power:
            return RiskGateResult(
                gate_name="Account State Gate", status=RiskDecision.BLOCK,
                measured_value=required_cash, threshold=buying_power,
                explanation="Insufficient buying power to cover the proposed trade."
            )
            
    return RiskGateResult(gate_name="Account State Gate", status=RiskDecision.ALLOW, explanation="Sufficient account resources.")

# ==========================================
# 3. MARKET REGIME GATE
# ==========================================
def check_market_regime_gate(action: str, regime_state: str) -> RiskGateResult:
    """Flags new BUY orders for review if the market is under stress."""
    if action.upper() == "BUY" and regime_state == "Risk-Off":
        return RiskGateResult(
            gate_name="Market Regime Gate", status=RiskDecision.REVIEW,
            measured_value=regime_state, threshold="Risk-On / Neutral",
            explanation="Broad market is currently exhibiting high stress/downtrend (Risk-Off). Buying is heavily scrutinized."
        )
        
    return RiskGateResult(gate_name="Market Regime Gate", status=RiskDecision.ALLOW, explanation="Market regime is acceptable.")

# ==========================================
# 4. VOLATILITY SIZING GATE
# ==========================================
def check_volatility_sizing_gate(
    action: str, quantity: float, account_equity: float, 
    asset_atr_14: float, profile: UserRiskProfile
) -> RiskGateResult:
    """Checks if the requested quantity exceeds the ATR-based safety limit."""
    if action.upper() == "BUY":
        max_safe = calculate_max_safe_shares(account_equity, profile.risk_per_trade, asset_atr_14)
        if quantity > max_safe:
            return RiskGateResult(
                gate_name="Volatility Sizing Gate", status=RiskDecision.REVIEW,
                measured_value=quantity, threshold=max_safe,
                explanation="Proposed quantity exceeds policy-based risk-sizing approximation.",
                recommended_alternative=f"Reduce quantity to maximum {max_safe} shares."
            )
            
    return RiskGateResult(gate_name="Volatility Sizing Gate", status=RiskDecision.ALLOW, explanation="Position sizing is within volatility limits.")

# ==========================================
# 5. PROJECTED PORTFOLIO GATE
# ==========================================
def check_projected_portfolio_gate(
    action: str, symbol: str, quantity: float, price: float,
    current_equity: float, current_positions: list,
    limits: SystemHardLimits, profile: UserRiskProfile
) -> RiskGateResult:
    """Evaluates the resulting concentration of the asset against hard and soft limits."""
    projected_weight = calculate_projected_concentration(
        current_equity, current_positions, symbol, quantity, price, action
    )
    
    # 1. Check Hard Limit (Absolute Block)
    if projected_weight > limits.absolute_concentration_cap:
        return RiskGateResult(
            gate_name="Projected Portfolio Gate", status=RiskDecision.BLOCK,
            measured_value=projected_weight, threshold=limits.absolute_concentration_cap,
            explanation=f"Trade results in {projected_weight*100}% concentration, exceeding absolute hard limit of {limits.absolute_concentration_cap*100}%."
        )
        
    # 2. Check User Policy (Review)
    if projected_weight > profile.max_concentration:
        return RiskGateResult(
            gate_name="Projected Portfolio Gate", status=RiskDecision.REVIEW,
            measured_value=projected_weight, threshold=profile.max_concentration,
            explanation=f"Trade results in {projected_weight*100}% concentration, exceeding user policy limit of {profile.max_concentration*100}%.",
            recommended_alternative="Reduce quantity to stay within user policy."
        )
        
    return RiskGateResult(gate_name="Projected Portfolio Gate", status=RiskDecision.ALLOW, explanation="Projected concentration is safe.")

# ==========================================
# 6. LOSS / DRAWDOWN GATE (KILL SWITCH)
# ==========================================
def check_loss_drawdown_gate(
    action: str, daily_loss_pct: float, 
    limits: SystemHardLimits, profile: UserRiskProfile
) -> RiskGateResult:
    """Halts or flags buying if daily P&L goes severely negative."""
    # Only restrict new risk (BUYs). Allowing SELLs is usually fine to cut exposure.
    if action.upper() == "BUY":
        # 1. Check Hard Kill Switch
        if daily_loss_pct >= limits.absolute_daily_loss_halt:
            return RiskGateResult(
                gate_name="Loss/Drawdown Gate", status=RiskDecision.BLOCK,
                measured_value=daily_loss_pct, threshold=limits.absolute_daily_loss_halt,
                explanation="KILL SWITCH TRIGGERED. Daily loss exceeds hard limit. Halting all new BUY orders."
            )
            
        # 2. Check User Review Threshold
        if daily_loss_pct >= profile.daily_drawdown_review:
            return RiskGateResult(
                gate_name="Loss/Drawdown Gate", status=RiskDecision.REVIEW,
                measured_value=daily_loss_pct, threshold=profile.daily_drawdown_review,
                explanation="Account daily drawdown has exceeded user policy threshold. Scrutinizing new buys."
            )

    return RiskGateResult(gate_name="Loss/Drawdown Gate", status=RiskDecision.ALLOW, explanation="Drawdown is within limits.")