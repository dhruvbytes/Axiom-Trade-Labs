# backend/tool_router/schemas.py

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone

# ==========================================
# ENUMS
# ==========================================
class RequestSource(str, Enum):
    HUMAN_CHAT = "HUMAN_CHAT"
    AUTONOMOUS_TRIGGER = "AUTONOMOUS_TRIGGER"

class RouterStatus(str, Enum):
    SUCCESS = "SUCCESS"
    ROUTING_UNCERTAIN = "ROUTING_UNCERTAIN"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
    NO_RELEVANT_TOOL = "NO_RELEVANT_TOOL"
    INVALID_REQUEST = "INVALID_REQUEST"

class EntityType(str, Enum):
    TICKER = "TICKER"
    COMPANY_NAME = "COMPANY_NAME"
    QUANTITY = "QUANTITY"
    DATE = "DATE"
    TIME_RANGE = "TIME_RANGE"
    OTHER = "OTHER"

# ==========================================
# ROUTING & ENTITY MODELS
# ==========================================
class RoutingContext(BaseModel):
    """Context of the request, supporting both human and autonomous origins."""
    original_request: str = Field(description="The exact text string to be routed.")
    source: RequestSource = Field(default=RequestSource.HUMAN_CHAT, description="Origin of the request.")
    request_id: str = Field(description="Unique identifier for traceability.")
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ExtractedEntity(BaseModel):
    """A deterministically extracted entity (e.g., Ticker). No guessing allowed."""
    entity_type: EntityType
    value: str = Field(description="The normalized value, e.g., 'AAPL'")
    raw_text: str = Field(description="The original text matched, e.g., 'Apple'")

class ToolRequest(BaseModel):
    """The router's declaration of a tool it intends to execute."""
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(description="Why this tool is required (Capability mapping).")
    is_required: bool = Field(default=True, description="If True, failure of this tool fails the intent.")

class RoutingDecision(BaseModel):
    """The output of the NLU/Lexical routing layer."""
    detected_intent: str = Field(default="UNKNOWN", description="The identified capability domain.")
    routing_score: float = Field(default=0.0, description="BM25/Lexical score (0.0 to 1.0). NOT a probability.")
    status: RouterStatus
    extracted_entities: List[ExtractedEntity] = Field(default_factory=list)
    selected_tools: List[ToolRequest] = Field(default_factory=list)

# ==========================================
# EXECUTION & PROVENANCE MODELS
# ==========================================
class DataProvenance(BaseModel):
    """CRITICAL: Tracks exactly where financial data came from and its age."""
    source_tool: str = Field(description="Exact MCP tool name used.")
    retrieved_at_utc: str = Field(description="ISO timestamp of data retrieval.")
    is_cached: bool = Field(description="True if pulled from memory, False if live from Alpaca.")
    data_age_seconds: float = Field(default=0.0, description="How old the data is relative to now.")

class ToolResult(BaseModel):
    """Strict wrapper for MCP tool outputs preventing silent nulls or fake data."""
    tool_name: str
    is_success: bool = Field(description="Must be explicitly evaluated.")
    data: Optional[Any] = Field(default=None, description="The actual data payload if successful.")
    error_message: Optional[str] = Field(default=None, description="Explicit error reason if failed.")
    provenance: Optional[DataProvenance] = Field(default=None)

# ==========================================
# FINAL OUTPUT MODEL (THE MARKET BRIEF)
# ==========================================
class MarketBrief(BaseModel):
    """
    The compact, token-efficient summary sent to the Main Gemini Reasoning Agent.
    Replaces massive FunctionDeclarations. Heavily guards against hallucinations.
    """
    router_status: RouterStatus
    intent: str = Field(description="What the router thought the user wanted.")
    routing_score: float
    data_timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Clearly separating successful data from failures
    successful_observations: Dict[str, ToolResult] = Field(
        default_factory=dict, 
        description="Map of tool_name -> ToolResult (contains data and provenance)."
    )
    failed_tools: List[ToolResult] = Field(
        default_factory=list, 
        description="Tools that threw exceptions, timed out, or had missing tickers."
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "router_status": "SUCCESS",
                "intent": "ACCOUNT_AND_MARKET",
                "routing_score": 0.85,
                "successful_observations": {
                    "get_latest_quote": {
                        "tool_name": "get_latest_quote",
                        "is_success": True,
                        "data": {"AAPL": {"price": 150.25}},
                        "provenance": {
                            "source_tool": "alpaca_mcp:get_latest_quote",
                            "retrieved_at_utc": "2026-08-18T16:43:00Z",
                            "is_cached": False,
                            "data_age_seconds": 0.5
                        }
                    }
                },
                "failed_tools": []
            }
        }