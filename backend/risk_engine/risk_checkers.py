# backend/risk_engine/risk_checkers.py

from datetime import timezone
from backend.risk_engine.risk_models import (
    RiskDecision, RiskGateResult, SystemHardLimits, UserRiskProfile,
    UniversalTradeProposal, SystemFacts, AssetFreshnessPolicy, AssetClass
)
from backend.risk_engine.portfolio_state import calculate_projected_concentration, calculate_max_safe_shares
from backend.risk_engine.payoff_utils import PayoffResult

# ==========================================
# 1. FRESHNESS GATE (NEW)
# ==========================================
def check_freshness_gate(proposal: UniversalTradeProposal, facts: SystemFacts, policy: AssetFreshnessPolicy) -> RiskGateResult:
    # Ensure TZ-aware math (Assume UTC)
    obs_time = proposal.timing.observation_timestamp.replace(tzinfo=timezone.utc)
    now_time = facts.timestamp.replace(tzinfo=timezone.utc)
    age_ms = (now_time - obs_time).total_seconds() * 1000
    
    has_options = any(leg.instrument.asset_class == AssetClass.OPTION for leg in proposal.intent.legs)
    sys_max = policy.max_option_age_ms if has_options else policy.max_equity_age_ms
    
    # Stricter of Agent's requested tolerance vs System's hard limit
    effective_max = min(proposal.timing.max_decision_age_ms, sys_max)
    
    if age_ms > effective_max:
        return RiskGateResult(
            gate_name="Freshness Gate", status=RiskDecision.BLOCK,
            measured_value=age_ms, threshold=effective_max,
            explanation=f"Market data is stale. Age: {age_ms}ms, Limit: {effective_max}ms."
        )
    return RiskGateResult(gate_name="Freshness Gate", status=RiskDecision.ALLOW, explanation="Market data is fresh.")

# ==========================================
# 2. SEMANTIC GATE (UPDATED)
# ==========================================
def check_semantic_gate(proposal: UniversalTradeProposal) -> RiskGateResult:
    if proposal.intent.package_quantity <= 0:
        return RiskGateResult(gate_name="Semantic Gate", status=RiskDecision.BLOCK, explanation="Package quantity must be > 0.")
    if any(leg.ratio_qty <= 0 for leg in proposal.intent.legs):
        return RiskGateResult(gate_name="Semantic Gate", status=RiskDecision.BLOCK, explanation="Leg ratio_qty must be > 0.")
    return RiskGateResult(gate_name="Semantic Gate", status=RiskDecision.ALLOW, explanation="Structural semantics are valid.")

# ==========================================
# 3. LOSS / DRAWDOWN GATE (UNCHANGED LOGIC)
# ==========================================
def check_loss_drawdown_gate(daily_loss_pct: float, limits: SystemHardLimits, profile: UserRiskProfile) -> RiskGateResult:
    if daily_loss_pct >= limits.absolute_daily_loss_halt:
        return RiskGateResult(
            gate_name="Loss/Drawdown Gate", status=RiskDecision.BLOCK,
            measured_value=daily_loss_pct, threshold=limits.absolute_daily_loss_halt,
            explanation="KILL SWITCH TRIGGERED. Daily loss exceeds hard limit."
        )
    if daily_loss_pct >= profile.daily_drawdown_review:
        return RiskGateResult(
            gate_name="Loss/Drawdown Gate", status=RiskDecision.REVIEW,
            measured_value=daily_loss_pct, threshold=profile.daily_drawdown_review,
            explanation="Account daily drawdown has exceeded user policy threshold."
        )
    return RiskGateResult(gate_name="Loss/Drawdown Gate", status=RiskDecision.ALLOW, explanation="Drawdown is within limits.")

# ==========================================
# 4. PAYOFF RISK GATE (NEW)
# ==========================================
def check_payoff_risk_gate(payoff: PayoffResult) -> RiskGateResult:
    if payoff.is_infinite_risk:
        return RiskGateResult(
            gate_name="Payoff Risk Gate", status=RiskDecision.BLOCK,
            explanation="Proposal contains infinite theoretical risk (e.g., naked short options)."
        )
    return RiskGateResult(gate_name="Payoff Risk Gate", status=RiskDecision.ALLOW, explanation="Risk is bounded and defined.")

# ==========================================
# 5. ACCOUNT STATE / MARGIN GATE (UPDATED)
# ==========================================
def check_account_state_gate(proposal: UniversalTradeProposal, facts: SystemFacts, payoff: PayoffResult) -> RiskGateResult:
    req_cap = payoff.max_theoretical_loss
    
    if req_cap > facts.account.buying_power:
        return RiskGateResult(
            gate_name="Account State Gate", status=RiskDecision.BLOCK,
            measured_value=req_cap, threshold=facts.account.buying_power,
            explanation="Insufficient actual buying power to cover the trade margin."
        )
    if req_cap > proposal.boundaries.max_capital_allocation:
        return RiskGateResult(
            gate_name="Account State Gate", status=RiskDecision.BLOCK,
            measured_value=req_cap, threshold=proposal.boundaries.max_capital_allocation,
            explanation="Required margin exceeds agent's requested capital allocation."
        )
    return RiskGateResult(gate_name="Account State Gate", status=RiskDecision.ALLOW, explanation="Capital constraints met.")

# ==========================================
# 6. BUDGET GATE (NEW)
# ==========================================
def check_budget_gate(proposal: UniversalTradeProposal, payoff: PayoffResult) -> RiskGateResult:
    if payoff.max_theoretical_loss > proposal.boundaries.max_loss_budget:
        return RiskGateResult(
            gate_name="Budget Gate", status=RiskDecision.BLOCK,
            measured_value=payoff.max_theoretical_loss, threshold=proposal.boundaries.max_loss_budget,
            explanation="Calculated max loss exceeds agent's requested max loss budget."
        )
    return RiskGateResult(gate_name="Budget Gate", status=RiskDecision.ALLOW, explanation="Within max loss budget.")

# ==========================================
# 7. PROJECTED PORTFOLIO GATE (UPDATED)
# ==========================================
def check_projected_portfolio_gate(proposal: UniversalTradeProposal, facts: SystemFacts, limits: SystemHardLimits, profile: UserRiskProfile) -> RiskGateResult:
    projected_weight = calculate_projected_concentration(proposal, facts)
    
    if projected_weight > limits.absolute_concentration_cap:
        return RiskGateResult(
            gate_name="Projected Portfolio Gate", status=RiskDecision.BLOCK,
            measured_value=projected_weight, threshold=limits.absolute_concentration_cap,
            explanation=f"Trade results in {projected_weight*100}% exposure, exceeding absolute hard limit of {limits.absolute_concentration_cap*100}%."
        )
    if projected_weight > profile.max_concentration:
        return RiskGateResult(
            gate_name="Projected Portfolio Gate", status=RiskDecision.REVIEW,
            measured_value=projected_weight, threshold=profile.max_concentration,
            explanation=f"Trade results in {projected_weight*100}% exposure, exceeding user policy limit of {profile.max_concentration*100}%."
        )
    return RiskGateResult(gate_name="Projected Portfolio Gate", status=RiskDecision.ALLOW, explanation="Projected concentration is safe.")

# ==========================================
# 8. MARKET REGIME GATE (UNCHANGED LOGIC)
# ==========================================
def check_market_regime_gate(regime_state: str) -> RiskGateResult:
    if regime_state == "Risk-Off":
        return RiskGateResult(
            gate_name="Market Regime Gate", status=RiskDecision.REVIEW,
            measured_value=regime_state, threshold="Risk-On / Neutral",
            explanation="Broad market is currently exhibiting high stress (Risk-Off). Highly scrutinized."
        )
    return RiskGateResult(gate_name="Market Regime Gate", status=RiskDecision.ALLOW, explanation="Market regime is acceptable.")

# ==========================================
# 9. VOLATILITY SIZING GATE (UPDATED FOR NMLI)
# ==========================================
def check_volatility_sizing_gate(proposal: UniversalTradeProposal, facts: SystemFacts, asset_atr_14: float, profile: UserRiskProfile) -> RiskGateResult:
    if asset_atr_14 > 0:
        max_safe = calculate_max_safe_shares(facts.account.equity, profile.risk_per_trade, asset_atr_14)
        
        # Sizing check is primarily for direct equity legs
        total_equity_qty = sum(
            leg.ratio_qty * proposal.intent.package_quantity 
            for leg in proposal.intent.legs if leg.instrument.asset_class == AssetClass.EQUITY
        )
        
        if total_equity_qty > max_safe:
            return RiskGateResult(
                gate_name="Volatility Sizing Gate", status=RiskDecision.REVIEW,
                measured_value=total_equity_qty, threshold=max_safe,
                explanation="Proposed quantity exceeds ATR policy-based risk-sizing approximation."
            )
    return RiskGateResult(gate_name="Volatility Sizing Gate", status=RiskDecision.ALLOW, explanation="Position sizing is within volatility limits.")