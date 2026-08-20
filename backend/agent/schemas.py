# backend/agent/schemas.py
from typing import List
from pydantic import BaseModel, Field
from backend.tool_router.schemas import ToolRequest
from backend.execution.models import ExecutionResult

class SystemExecutionEnvelope(BaseModel):
    """The structured, deterministic result of the entire system pipeline."""
    trace_id: str
    original_query: str
    intent_nonce: str
    status: str
    
    validated_requests: List[ToolRequest] = Field(default_factory=list)
    execution_results: List[ExecutionResult] = Field(default_factory=list)
    risk_rejections: List[str] = Field(default_factory=list)
    
    reconciliation_required: bool = False