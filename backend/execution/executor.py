# backend/execution/executor.py

import asyncio
from typing import Dict, Any
from .models import ExecutableTask, ExecutionResult, ExecutionState
from .journal import execution_journal

# Import the existing MCP Client Manager abstractly
from backend.mcp_client_manager import mcp_manager

class CoreXExecutor:
    """
    Idempotent Deterministic Execution Machine (CORE-X).
    Enforces strict At-Most-Once dispatch for mutations and handles autonomous retries.
    """
    def __init__(self):
        # In-process locks for concurrent single-flight protection
        self._locks: Dict[str, asyncio.Lock] = {}
        
    def _get_lock(self, ik: str) -> asyncio.Lock:
        if ik not in self._locks:
            self._locks[ik] = asyncio.Lock()
        return self._locks[ik]
        
    async def execute(self, task: ExecutableTask, timeout_seconds: float = 10.0) -> ExecutionResult:
        ik = task.idempotency_key
        lock = self._get_lock(ik)
        
        async with lock:
            # 1. Deduplication via SQLite WAL (Atomic Insert)
            is_new, state, cached_data, err_ctx = execution_journal.insert_or_get_status(
                ik=ik,
                intent_nonce=task.intent_nonce,
                tool_name=task.tool_request.tool_name,
                is_mutating=task.is_mutating,
                risk_auth_hash=task.risk_token
            )
            
            if not is_new:
                # 2. Replay / Duplicate Handling (Safe Return)
                return self._handle_duplicate(ik, state, cached_data, err_ctx)
                
            # 3. Transition to RISK_AUTHORIZED (Task model itself enforces Risk Token existence)
            execution_journal.transition_state(ik, ExecutionState.RECEIVED, ExecutionState.RISK_AUTHORIZED)
            
            # 4. Dispatch (Point of No Return for Mutations)
            execution_journal.transition_state(ik, ExecutionState.RISK_AUTHORIZED, ExecutionState.DISPATCHED)
            
            try:
                # 5. Actual MCP Execution wrapped in Strict Timeout
                raw_result = await asyncio.wait_for(
                    mcp_manager.execute_tool(task.tool_request.tool_name, task.tool_request.arguments),
                    timeout=timeout_seconds
                )
                
                # 6. Safe Result Extraction across different MCP SDK versions
                is_err = getattr(raw_result, 'is_error', getattr(raw_result, 'isError', False))
                
                if is_err:
                    error_msg = getattr(raw_result, 'content', "Unknown MCP Error")
                    execution_journal.transition_state(ik, ExecutionState.DISPATCHED, ExecutionState.SUCCEEDED, error_context=str(error_msg))
                    return ExecutionResult(idempotency_key=ik, status=ExecutionState.SUCCEEDED, error_message=str(error_msg))
                else:
                    # Parse textual content blocks 
                    result_text = " ".join([c.text for c in raw_result.content if getattr(c, 'type', '') == 'text'])
                    payload = {"result": result_text}
                    execution_journal.transition_state(ik, ExecutionState.DISPATCHED, ExecutionState.SUCCEEDED, result_payload=payload)
                    return ExecutionResult(idempotency_key=ik, status=ExecutionState.SUCCEEDED, data=payload)
                    
            except asyncio.TimeoutError:
                # TIMEOUT LOGIC - CRUCIAL SAFETY BOUNDARY
                if task.is_mutating:
                    execution_journal.transition_state(ik, ExecutionState.DISPATCHED, ExecutionState.EXECUTION_UNCERTAIN, error_context="TIMEOUT_AFTER_DISPATCH")
                    return ExecutionResult(idempotency_key=ik, status=ExecutionState.EXECUTION_UNCERTAIN, error_message="Timeout after dispatch on MUTATING tool. Halt.", reconciliation_required=True)
                else:
                    execution_journal.transition_state(ik, ExecutionState.DISPATCHED, ExecutionState.FAILED_SAFE, error_context="TIMEOUT_AFTER_DISPATCH")
                    return ExecutionResult(idempotency_key=ik, status=ExecutionState.FAILED_SAFE, error_message="Timeout after dispatch on READ-ONLY tool. Safe to retry.")
                    
            except Exception as e:
                # Transport Drops, Broken Pipes, etc.
                if task.is_mutating:
                    execution_journal.transition_state(ik, ExecutionState.DISPATCHED, ExecutionState.EXECUTION_UNCERTAIN, error_context=f"EXCEPTION: {str(e)}")
                    return ExecutionResult(idempotency_key=ik, status=ExecutionState.EXECUTION_UNCERTAIN, error_message=f"Crash during MUTATING tool: {str(e)}", reconciliation_required=True)
                else:
                    execution_journal.transition_state(ik, ExecutionState.DISPATCHED, ExecutionState.FAILED_SAFE, error_context=f"EXCEPTION: {str(e)}")
                    return ExecutionResult(idempotency_key=ik, status=ExecutionState.FAILED_SAFE, error_message=str(e))
                    
    def _handle_duplicate(self, ik: str, state: ExecutionState, data: Any, err_ctx: str) -> ExecutionResult:
        """Returns structured result for requests that were already processed."""
        if state == ExecutionState.SUCCEEDED:
            return ExecutionResult(idempotency_key=ik, status=state, data=data, error_message=err_ctx, is_cached_replay=True)
        elif state == ExecutionState.FAILED_SAFE:
            return ExecutionResult(idempotency_key=ik, status=state, error_message=err_ctx, is_cached_replay=True)
        elif state == ExecutionState.EXECUTION_UNCERTAIN:
            return ExecutionResult(idempotency_key=ik, status=state, error_message=err_ctx, is_cached_replay=True, reconciliation_required=True)
        else:
            return ExecutionResult(idempotency_key=ik, status=state, error_message="Concurrent execution blocked. Awaiting resolution.", is_cached_replay=True)

# Global Singleton Instance for FastAPI to use
corex_executor = CoreXExecutor()