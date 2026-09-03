"""Typed, bounded contracts for the autonomous decision layer.

These objects intentionally describe decisions and evidence, never risk-policy
changes or executable authority.  Execution still requires the existing
Admission -> Risk -> CORE-X path.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class RegimeLabel(str, Enum):
    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    STRESS = "STRESS"
    UNKNOWN = "UNKNOWN"


class DecisionStatus(str, Enum):
    NO_TRADE = "NO_TRADE"
    PROPOSED = "PROPOSED"
    DEFERRED = "DEFERRED"
    BLOCKED = "BLOCKED"


class HypothesisAction(str, Enum):
    BUY_STOCK = "BUY_STOCK"
    SELL_STOCK = "SELL_STOCK"
    BUY_CALL = "BUY_CALL"
    BUY_PUT = "BUY_PUT"
    NO_TRADE = "NO_TRADE"


class OptionContractFact(BaseModel):
    """Authoritative option contract evidence fact."""
    model_config = ConfigDict(extra="forbid")

    contract_symbol: str
    underlying_symbol: str
    strike: float
    expiry: str
    option_type: str
    bid: float = Field(ge=0.0)
    ask: float = Field(ge=0.0)
    mid: float = Field(gt=0.0)
    spread_pct: float = Field(ge=0.0)
    open_interest: int = Field(ge=0)
    dte: int = Field(ge=0)
    quote_timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ContextSnapshot(BaseModel):
    """A compact, authoritative-at-collection-time view of one decision."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(default_factory=lambda: uuid4().hex)
    observed_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    symbol: str
    event_price: float = Field(gt=0)
    material_change_pct: float
    equity: float = Field(gt=0)
    buying_power: float = Field(ge=0)
    positions: List[Dict[str, Any]] = Field(default_factory=list)
    spy_price: float = Field(gt=0)
    spy_sma_50: float = Field(gt=0)
    spy_atr_14: float = Field(ge=0)
    is_market_open: bool = True
    data_fresh: bool = True
    provenance: str = "Alpaca_IEX_Basic_Tier"

    def held_quantity(self) -> float:
        for position in self.positions:
            if str(position.get("symbol", "")).upper() == self.symbol.upper():
                try:
                    return float(position.get("qty", 0))
                except (TypeError, ValueError):
                    return 0.0
        return 0.0


class RegimeEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: RegimeLabel
    confidence: float = Field(ge=0.0, le=1.0)
    volatility_pct: float = Field(ge=0.0)
    transition_pending: bool = False
    reason: str = Field(max_length=240)


class EvidenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complete: bool
    data_fresh: bool
    facts: Dict[str, Any] = Field(default_factory=dict)
    missing: List[str] = Field(default_factory=list)
    llm_used: bool = False
    reason: str = Field(max_length=240)


class HypothesisEvaluation(BaseModel):
    """One approved analytical approach evaluated against current context."""

    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    display_name: str
    eligible: bool
    action: HypothesisAction
    expected_direction: int = Field(ge=-1, le=1)
    evidence_requirements: List[str] = Field(default_factory=list)
    base_confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(max_length=240)
    requires_llm_synthesis: bool = False
    is_risk_reduction: bool = False


class CandidateScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    posterior_mean: float = Field(ge=0.0, le=1.0)
    observations: int = Field(ge=0)
    score: float = Field(ge=0.0, le=1.0)
    selected: bool = False


class DecisionReceipt(BaseModel):
    """Append-only receipt describing a bounded choice, including abstention."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(default_factory=lambda: uuid4().hex)
    created_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    account_id: str = "default_account"
    trigger_fingerprint: str
    snapshot: ContextSnapshot
    regime: RegimeEstimate
    evaluations: List[HypothesisEvaluation]
    evidence: Dict[str, EvidenceResult] = Field(default_factory=dict)
    candidate_scores: List[CandidateScore] = Field(default_factory=list)
    selected_hypothesis_id: str = "no_trade"
    status: DecisionStatus
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(max_length=300)
    proposal_payload: Optional[Dict[str, Any]] = None
    outcome_due_at_utc: Optional[str] = None
    selected_contract_symbol: Optional[str] = None


class OutcomeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome_id: str = Field(default_factory=lambda: uuid4().hex)
    decision_id: str
    hypothesis_id: str
    regime: RegimeLabel
    symbol: str
    expected_direction: int = Field(ge=-1, le=1)
    entry_price: float = Field(gt=0)
    exit_price: float = Field(gt=0)
    gross_return_pct: float
    success: bool
    completed_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "PAPER_MARK_TO_MARKET"
    contract_symbol: Optional[str] = None
    contract_entry_price: Optional[float] = None
    contract_exit_price: Optional[float] = None

