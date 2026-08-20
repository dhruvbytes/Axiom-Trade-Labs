from enum import Enum
from typing import Optional, List, Any
from pydantic import BaseModel, Field

# ==========================================
# 1. RISK DECISION ENUM
# ==========================================
class RiskDecision(str, Enum):
    """The three possible states for any risk evaluation."""
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"


# ==========================================
# 2. SYSTEM HARD LIMITS (Non-negotiable)
# ==========================================
class SystemHardLimits(BaseModel):
    """
    Absolute boundaries that the AI or User can NEVER override.
    DEMO DEFAULT / PROJECT POLICY — NOT UNIVERSAL FINANCIAL RULE
    """
    absolute_concentration_cap: float = Field(
        default=0.25, 
        description="Hard limit: Max 25% of portfolio in a single asset. DEMO DEFAULT / PROJECT POLICY — NOT UNIVERSAL FINANCIAL RULE"
    )
    absolute_daily_loss_halt: float = Field(
        default=0.05, 
        description="Hard limit: Kill switch active if daily loss exceeds 5%. DEMO DEFAULT / PROJECT POLICY — NOT UNIVERSAL FINANCIAL RULE"
    )


# ==========================================
# 3. USER RISK PROFILE (Configurable Policy)
# ==========================================
class UserRiskProfile(BaseModel):
    """
    User-configurable thresholds that trigger REVIEWs.
    DEMO DEFAULT / PROJECT POLICY — NOT UNIVERSAL FINANCIAL RULE
    """
    max_concentration: float = Field(
        default=0.15, 
        description="User policy: Max 15% concentration. DEMO DEFAULT / PROJECT POLICY — NOT UNIVERSAL FINANCIAL RULE"
    )
    risk_per_trade: float = Field(
        default=0.01, 
        description="User policy: 1% risk per trade for ATR sizing. DEMO DEFAULT / PROJECT POLICY — NOT UNIVERSAL FINANCIAL RULE"
    )
    daily_drawdown_review: float = Field(
        default=0.03, 
        description="User policy: Flag for review if daily loss hits 3%. DEMO DEFAULT / PROJECT POLICY — NOT UNIVERSAL FINANCIAL RULE"
    )


# ==========================================
# 4. RISK GATE RESULT (Output of a single layer)
# ==========================================
class RiskGateResult(BaseModel):
    """Standardized output for an individual risk gate evaluation."""
    gate_name: str = Field(description="Name of the evaluated gate (e.g., 'Account/State Gate')")
    status: RiskDecision = Field(description="ALLOW, BLOCK, or REVIEW")
    measured_value: Any = Field(default=None, description="The actual value measured by the engine")
    threshold: Any = Field(default=None, description="The policy or hard limit threshold applied")
    explanation: str = Field(description="Clear reason for the decision")
    recommended_alternative: Optional[str] = Field(default=None, description="Safer alternative if applicable")


# ==========================================
# 5. RISK ENGINE OUTPUT (Final summary)
# ==========================================
class RiskEngineOutput(BaseModel):
    """The final structured decision returned by the Master Risk Engine."""
    final_decision: RiskDecision = Field(description="The overall aggregated decision")
    gate_results: List[RiskGateResult] = Field(description="Detailed results from every evaluated gate")
    summary_explanation: str = Field(description="A brief summary of why the proposal was allowed, blocked, or flagged for review.")