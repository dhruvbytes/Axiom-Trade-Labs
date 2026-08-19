# backend/execution/models.py

import hashlib
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

# Ensure we import the strictly validated ToolRequest from 4E
from backend.tool_router.schemas import ToolRequest

class ExecutionState(str, Enum):
    """Strict State Machine for IDEM-X / CORE-X Execution Lifecycle"""
    RECEIVED = "RECEIVED"                     # Logged in journal, waiting for lock
    RISK_AUTHORIZED = "RISK_AUTHORIZED"       # Token validated, ready to dispatch
    DISPATCHED = "DISPATCHED"                 # In-flight to MCP (Point of no return for mutations)
    SUCCEEDED = "SUCCEEDED"                   # MCP returned valid output
    FAILED_SAFE = "FAILED_SAFE"               # Failed cleanly or timed out BEFORE dispatch/mutation
    EXECUTION_UNCERTAIN = "EXECUTION_UNCERTAIN" # Timeout/Crash AFTER dispatch on a mutating tool (HARD STOP)

class ExecutableTask(BaseModel):
    """
    The strictly authorized payload that 4F accepts.
    Must contain explicit Risk Authorization and Mutation Policy.
    """
    intent_nonce: str = Field(description="Unique ID for this logical attempt (Client Request ID).")
    tool_request: ToolRequest = Field(description="The fully validated 4E ToolRequest.")
    risk_token: str = Field(description="Cryptographic or UUID token from the Risk Engine.")
    is_mutating: bool = Field(description="Explicit policy flag: Does this tool modify state/money?")
    
    @property
    def idempotency_key(self) -> str:
        """
        Deterministically generates the IK.
        If the Intent, Schema (Fingerprint), or Risk Policy changes, the IK changes.
        """
        fingerprint_hash = "no_fingerprint"
        if self.tool_request.fingerprint:
            fingerprint_hash = self.tool_request.fingerprint.schema_hash
            
        # Composite identity string
        raw_identity = f"{self.intent_nonce}|{fingerprint_hash}|{self.risk_token}"
        return hashlib.sha256(raw_identity.encode('utf-8')).hexdigest()

class ExecutionResult(BaseModel):
    """Structured machine-readable result returned by 4F."""
    idempotency_key: str
    status: ExecutionState
    data: Optional[Any] = Field(default=None, description="Raw MCP output if successful.")
    error_message: Optional[str] = Field(default=None, description="Explicit error/timeout reason.")
    is_cached_replay: bool = Field(default=False, description="True if this was a safely handled duplicate.")
    reconciliation_required: bool = Field(default=False, description="True ONLY if EXECUTION_UNCERTAIN.")