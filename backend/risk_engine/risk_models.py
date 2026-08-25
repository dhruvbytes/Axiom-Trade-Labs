# backend/risk_engine/risk_models.py

from enum import Enum
from typing import Optional, List, Any, Dict
from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

# ==========================================
# 1. EXISTING RISK MODELS (PRESERVED)
# ==========================================
class RiskDecision(str, Enum):
    """The three possible states for any risk evaluation."""
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"

class SystemHardLimits(BaseModel):
    """Absolute boundaries that the AI or User can NEVER override."""
    absolute_concentration_cap: float = Field(
        default=0.25, 
        description="Hard limit: Max 25% of portfolio in a single asset."
    )
    absolute_daily_loss_halt: float = Field(
        default=0.05, 
        description="Hard limit: Kill switch active if daily loss exceeds 5%."
    )

class UserRiskProfile(BaseModel):
    """User-configurable thresholds that trigger REVIEWs."""
    max_concentration: float = Field(
        default=0.15, 
        description="User policy: Max 15% concentration."
    )
    risk_per_trade: float = Field(
        default=0.01, 
        description="User policy: 1% risk per trade for ATR sizing."
    )
    daily_drawdown_review: float = Field(
        default=0.03, 
        description="User policy: Flag for review if daily loss hits 3%."
    )

class RiskGateResult(BaseModel):
    """Standardized output for an individual risk gate evaluation."""
    gate_name: str = Field(description="Name of the evaluated gate")
    status: RiskDecision = Field(description="ALLOW, BLOCK, or REVIEW")
    measured_value: Any = Field(default=None, description="The actual value measured by the engine")
    threshold: Any = Field(default=None, description="The policy or hard limit threshold applied")
    explanation: str = Field(description="Clear reason for the decision")
    recommended_alternative: Optional[str] = Field(default=None, description="Safer alternative if applicable")

class RiskEngineOutput(BaseModel):
    """The final structured decision returned by the Master Risk Engine."""
    final_decision: RiskDecision = Field(description="The overall aggregated decision")
    gate_results: List[RiskGateResult] = Field(description="Detailed results from every evaluated gate")
    summary_explanation: str = Field(description="A brief summary of why the proposal was allowed, blocked, or flagged for review.")


# ==========================================
# 2. NMLI PROPOSAL SCHEMA (LOCKED ARCHITECTURE)
# ==========================================
class AssetClass(str, Enum):
    EQUITY = "equity"
    OPTION = "option"

class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"

class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

class PositionIntent(str, Enum):
    OPEN = "open"
    CLOSE = "close"

class ExecutionType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"

class LimitPriceEffect(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"
    NONE = "none"

class Identity(BaseModel):
    schema_version: str = Field(default="1.0", frozen=True)
    proposal_id: UUID

class Timing(BaseModel):
    trigger_source: str
    observation_timestamp: datetime
    max_decision_age_ms: int = Field(gt=0)

class Instrument(BaseModel):
    asset_class: AssetClass
    underlying_symbol: Optional[str] = None
    strike: Optional[float] = None
    expiry: Optional[date] = None
    option_type: Optional[OptionType] = None

    @model_validator(mode='after')
    def validate_option_requirements(self):
        if self.asset_class == AssetClass.OPTION:
            if self.strike is None or self.expiry is None or self.option_type is None:
                raise ValueError("strike, expiry, and option_type are REQUIRED when asset_class is option")
        return self

class Leg(BaseModel):
    instrument: Instrument
    side: Side
    position_intent: PositionIntent
    ratio_qty: int = Field(gt=0)

class Intent(BaseModel):
    primary_underlying: str
    strategy_hint: Optional[str] = None
    package_quantity: int = Field(gt=0)
    legs: List[Leg] = Field(min_length=1)

class Boundaries(BaseModel):
    execution_type: ExecutionType
    limit_price: Optional[float] = None
    limit_price_effect: Optional[LimitPriceEffect] = None
    max_capital_allocation: float = Field(ge=0.0)
    max_loss_budget: float = Field(ge=0.0)

    @model_validator(mode='after')
    def validate_execution_type_rules(self):
        if self.execution_type == ExecutionType.LIMIT:
            if self.limit_price is None or self.limit_price_effect is None:
                raise ValueError("limit_price and limit_price_effect are REQUIRED when execution_type is limit")
        elif self.execution_type == ExecutionType.MARKET:
            if self.limit_price is not None or self.limit_price_effect is not None:
                raise ValueError("limit_price and limit_price_effect must be ABSENT when execution_type is market")
        return self

class MetadataBlock(BaseModel):
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)

class UniversalTradeProposal(BaseModel):
    """The unapproved agent-generated trading intent contract."""
    identity: Identity
    timing: Timing
    intent: Intent
    boundaries: Boundaries
    metadata: MetadataBlock


# ==========================================
# 3. SYSTEM FACTS MODELS (AUTHORITATIVE)
# ==========================================
class EquityQuoteFact(BaseModel):
    symbol: str
    bid: float
    ask: float
    price: float

class OptionQuoteFact(BaseModel):
    contract_symbol: str
    underlying: str
    strike: float
    expiry: date
    option_type: OptionType
    bid: float
    ask: float
    price: float
    multiplier: int = 100

class AccountFact(BaseModel):
    equity: float
    buying_power: float
    initial_margin: float
    maintenance_margin: float

class MarketStateFact(BaseModel):
    spy_price: float
    spy_sma_50: float
    spy_atr_14: float
    is_market_open: bool

class SystemFacts(BaseModel):
    """Authoritative facts generated downstream; no AI hallucination allowed."""
    account: AccountFact
    market_state: MarketStateFact
    equity_quotes: Dict[str, EquityQuoteFact] = Field(default_factory=dict)
    option_quotes: Dict[str, OptionQuoteFact] = Field(default_factory=dict)
    current_positions: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow())


# ==========================================
# 4. SYSTEM POLICIES
# ==========================================
class AssetFreshnessPolicy(BaseModel):
    """Authoritative system limits for data freshness."""
    max_equity_age_ms: int = 5000
    max_option_age_ms: int = 2000