# backend/autonomous/models.py

from enum import IntEnum, Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone

class ProposalPriority(IntEnum):
    """
    Strict priority ranking for the Shared Proposal Admission Boundary.
    Lower number means higher priority.
    """
    P1_RECONCILIATION = 1      # Emergency CORE-X uncertainty resolution
    P2_HUMAN_EXIT = 2          # Human close/reduce-risk
    P3_AUTO_RISK_REDUCTION = 3 # Autonomous deterministic risk-reduction (e.g., stop loss)
    P4_HUMAN_NEW_RISK = 4      # Human opportunity/new open
    P5_AUTO_OPPORTUNITY = 5    # Autonomous LLM opportunity proposal

class MarketEventSource(str, Enum):
    """
    Explicitly tracking the source to ensure Basic/Paper tier compliance.
    Strictly NO SIP or OPRA feeds allowed.
    """
    WEBSOCKET_IEX = "WEBSOCKET_IEX"       # US Equities (Free/Paper tier explicitly)
    WEBSOCKET_CRYPTO = "WEBSOCKET_CRYPTO" # Crypto feeds
    REST_POLLING_IEX = "REST_POLLING_IEX" # REST API strictly using feed='iex'
    INTERNAL_SYSTEM = "INTERNAL_SYSTEM"   # Scheduled triggers, timeouts, etc.

class AutonomousEvent(BaseModel):
    """Normalized market event from Alpaca (WebSocket or REST)."""
    symbol: str
    event_type: str = Field(description="e.g., 'quote', 'trade', 'bar', 'account_update'")
    price: Optional[float] = None
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: MarketEventSource
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Original Alpaca payload")

class MaterialChangeFingerprint(BaseModel):
    """Deterministic hash representation of a market situation to prevent LLM spam."""
    hash_value: str
    strategy_id: str
    symbol: str
    created_at_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class MarketBrief(BaseModel):
    """The strict, bounded context sent to the LLM. NO raw ticks or massive chains."""
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    trigger_reason: str = Field(description="Why this brief was generated e.g., 'RSI < 30'")
    current_facts: Dict[str, Any] = Field(description="Normalized current price, spread, etc. (IEX derived)")
    portfolio_exposure: Dict[str, Any] = Field(description="Current positions for this symbol")
    strategy_constraints: Dict[str, Any] = Field(description="Allowed instruments, max risk, etc.")
    narrowed_option_facts: Optional[List[Dict[str, Any]]] = Field(
        default=None, 
        description="Max 3-5 near-the-money strikes if options strategy is triggered."
    )
    provenance: str = Field(
        default="Alpaca_IEX_Basic_Tier", 
        description="Data source authority guaranteeing free tier compliance"
    )