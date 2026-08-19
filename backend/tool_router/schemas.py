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
    
    # --- PC-SDB/EA STRICT FAIL-CLOSED STATES ---
    NEEDS_CAPABILITY_AUTHORITY = "NEEDS_CAPABILITY_AUTHORITY" # Used for 0-param tools or unauthorized fields
    REJECTED_SCHEMA_MISMATCH = "REJECTED_SCHEMA_MISMATCH"
    REJECTED_FINGERPRINT_MISMATCH = "REJECTED_FINGERPRINT_MISMATCH"
    REJECTED_EXPIRED_AUTHORIZATION = "REJECTED_EXPIRED_AUTHORIZATION"
    REJECTED_UNSUPPORTED_SCHEMA = "REJECTED_UNSUPPORTED_SCHEMA"
    REJECTED_AMBIGUOUS_BINDING = "REJECTED_AMBIGUOUS_BINDING"
    REJECTED_MISSING_ARGUMENT = "REJECTED_MISSING_ARGUMENT"

class EntityType(str, Enum):
    TICKER = "TICKER"
    COMPANY_NAME = "COMPANY_NAME"
    QUANTITY = "QUANTITY"
    DATE = "DATE"
    TIME_RANGE = "TIME_RANGE"
    OTHER = "OTHER"


# ==========================================
# STRICT PC-SDB/EA SECURITY CONTRACTS (STEP 4E)
# ==========================================
class ExecutionContractFingerprint(BaseModel):
    """Immutable fingerprint representing the exact schema and deployment state."""
    deployment_identity: str = Field(description="Configured MCP deployment identity")
    tool_name: str
    schema_hash: str = Field(description="Canonical raw inputSchema SHA-256 hash")
    schema_dialect: str = Field(default="draft-2020-12", description="Effective JSON Schema dialect")
    toolset_scope: str = Field(default="global", description="Allowed toolset or deployment scope")
    registry_generation: str = Field(description="Registry load session/generation ID")

class BindingProof(BaseModel):
    """Audit evidence that a value mapping was explicitly authorized, NOT guessed."""
    json_pointer: str = Field(description="Exact target JSON Pointer e.g., /properties/symbol")
    value_provided: Any = Field(description="The exact value being bound")
    authority_reference: str = Field(description="Explicit authority e.g., 'HUMAN_CONFIRMATION', 'WORKFLOW_ID_XYZ'")
    evidence_source: Optional[str] = Field(default=None, description="Provenance e.g., 4B Entity ID or Fact Source")

class WorkflowBindingTemplate(BaseModel):
    """Defines exactly which JSON Pointers are permitted for Autonomous Mode bindings."""
    allowed_json_pointers: List[str]
    permitted_event_fact_sources: List[str]

class WorkflowAuthorization(BaseModel):
    """Strict, authenticated, expiring authorization artifact for Autonomous/Zero-Click execution."""
    workflow_id: str
    issuer: str
    allowed_tool: str
    contract_fingerprint: ExecutionContractFingerprint
    binding_template: WorkflowBindingTemplate
    expires_at_utc: str
    is_revoked: bool = False
    replay_identity: str
    policy_scope_reference: str


# ==========================================
# ROUTING & ENTITY MODELS
# ==========================================
class RoutingContext(BaseModel):
    original_request: str = Field(description="The exact text string to be routed.")
    source: RequestSource = Field(default=RequestSource.HUMAN_CHAT, description="Origin of the request.")
    request_id: str = Field(description="Unique identifier for traceability.")
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ExtractedEntity(BaseModel):
    entity_type: EntityType
    value: str = Field(description="The normalized value, e.g., 'AAPL'")
    raw_text: str = Field(description="The original text matched, e.g., 'Apple'")

class ToolRequest(BaseModel):
    """The router's declaration of a tool it intends to execute, now backed by Explicit Authority."""
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(description="Why this tool is required (Capability mapping).")
    is_required: bool = Field(default=True, description="If True, failure of this tool fails the intent.")
    
    # --- PC-SDB/EA EXPLICIT AUTHORITY FIELDS ---
    fingerprint: Optional[ExecutionContractFingerprint] = Field(default=None, description="Schema fingerprint bound to this request.")
    binding_proofs: List[BindingProof] = Field(default_factory=list, description="Every arg must have ONE BindingProof.")
    authorization_reference: Optional[str] = Field(default=None, description="Reference to the Human/Workflow Auth.")

class RoutingDecision(BaseModel):
    detected_intent: str = Field(default="UNKNOWN", description="The identified capability domain.")
    routing_score: float = Field(default=0.0, description="BM25/Lexical score (0.0 to 1.0). NOT a probability.")
    status: RouterStatus
    extracted_entities: List[ExtractedEntity] = Field(default_factory=list)
    selected_tools: List[ToolRequest] = Field(default_factory=list)


# ==========================================
# EXECUTION & PROVENANCE MODELS
# ==========================================
class DataProvenance(BaseModel):
    source_tool: str = Field(description="Exact MCP tool name used.")
    retrieved_at_utc: str = Field(description="ISO timestamp of data retrieval.")
    is_cached: bool = Field(description="True if pulled from memory, False if live from Alpaca.")
    data_age_seconds: float = Field(default=0.0, description="How old the data is relative to now.")

class ToolResult(BaseModel):
    tool_name: str
    is_success: bool = Field(description="Must be explicitly evaluated.")
    data: Optional[Any] = Field(default=None, description="The actual data payload if successful.")
    error_message: Optional[str] = Field(default=None, description="Explicit error reason if failed.")
    provenance: Optional[DataProvenance] = Field(default=None)


# ==========================================
# FINAL OUTPUT MODEL (THE MARKET BRIEF)
# ==========================================
class MarketBrief(BaseModel):
    router_status: RouterStatus
    intent: str = Field(description="What the router thought the user wanted.")
    routing_score: float
    data_timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    successful_observations: Dict[str, ToolResult] = Field(
        default_factory=dict, 
        description="Map of tool_name -> ToolResult (contains data and provenance)."
    )
    failed_tools: List[ToolResult] = Field(
        default_factory=list, 
        description="Tools that threw exceptions, timed out, or had missing tickers."
    )