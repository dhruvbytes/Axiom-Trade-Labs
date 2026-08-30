# backend/autonomous/worker.py

import logging
import asyncio
from typing import Dict, Any, Optional
from backend.autonomous.admission import UnifiedProposal
from backend.autonomous.uncertainty import uncertainty_gate

# Safe imports for CORE-X. Mocks fallback for isolated testing so it doesn't break.
try:
    from backend.execution.models import ExecutionState
except ImportError:
    class ExecutionState:
        SUCCEEDED = "SUCCEEDED"
        FAILED_SAFE = "FAILED_SAFE"
        EXECUTION_UNCERTAIN = "EXECUTION_UNCERTAIN"

logger = logging.getLogger(__name__)

class RiskDecision:
    """Mock enum mapping to your existing backend.risk.engine decisions"""
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"

class ProposalProcessor:
    """
    The single-threaded worker per account that safely bridges the Priority Scheduler 
    with the authoritative Risk Engine and CORE-X execution layer.
    """
    def __init__(self):
        pass

    async def fetch_authoritative_facts(self, account_id: str) -> Optional[Dict[str, Any]]:
        logger.debug(f"Fetching authoritative Alpaca facts for {account_id}...")
        return {"buying_power": 25000.0, "positions": []}

    async def evaluate_risk(self, proposal: UnifiedProposal, facts: Dict[str, Any]) -> str:
        return RiskDecision.ALLOW 

    async def dispatch_to_corex(self, proposal: UnifiedProposal, mock_result: Optional[Dict] = None) -> Any:
        """
        Bridges the NMLI proposal to the existing CORE-X executor.
        CORE-X handles the timeout, idempotency, and SQLite journaling.
        """
        if mock_result:
            return mock_result
            
        # In actual integration, we convert UnifiedProposal -> ExecutableTask
        # and invoke: return await corex_executor.execute(task)
        class MockResult:
            status = ExecutionState.SUCCEEDED
        return MockResult()

    async def process_critical_section(
        self, 
        proposal: UnifiedProposal, 
        account_lock: asyncio.Lock,
        mock_risk_decision: Optional[str] = None,
        mock_facts_fail: bool = False,
        mock_corex_result: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        The locked critical section. Prevents race conditions around Buying Power.
        The lock is ONLY released after CORE-X durably journals the terminal state.
        """
        async with account_lock:
            # 1. Uncertainty Check
            if not uncertainty_gate.can_admit_proposal(proposal.account_id, proposal.priority):
                return {"status": "DEFERRED", "reason": "Account is UNCERTAIN. Awaiting P1_RECONCILIATION."}

            # 2. Authoritative Fact Refresh
            facts = None if mock_facts_fail else await self.fetch_authoritative_facts(proposal.account_id)
            if not facts:
                logger.error("Failed to fetch authoritative facts. Failing closed.")
                return {"status": "FAILED", "reason": "Authoritative facts unavailable or stale."}

            # 3. Risk Engine Integration
            decision = mock_risk_decision or await self.evaluate_risk(proposal, facts)

            # 4. Interpret Risk Decision
            if decision == RiskDecision.ALLOW:
                logger.info(f"Risk ALLOWED for {proposal.source}. Dispatching to CORE-X.")
                
                # 5. CORE-X Execution (Inside the lock!)
                result = await self.dispatch_to_corex(proposal, mock_corex_result)
                
                # Safe status extraction
                status = result.get("status") if isinstance(result, dict) else getattr(result, "status", None)
                
                # 6. Apply Uncertainty Gate rule based on durable CORE-X state
                if status == getattr(ExecutionState, "EXECUTION_UNCERTAIN", "EXECUTION_UNCERTAIN"):
                    logger.critical(f"CORE-X returned UNCERTAIN for {proposal.account_id}. Locking account.")
                    uncertainty_gate.set_uncertainty(proposal.account_id, True)
                    return {"status": "EXECUTION_UNCERTAIN", "reason": "Network failure after dispatch."}
                
                return {"status": "EXECUTED", "corex_status": status}
            
            elif decision == RiskDecision.BLOCK:
                logger.warning(f"Risk BLOCKED proposal from {proposal.source}.")
                return {"status": "BLOCKED", "reason": "Risk Engine Blocked."}
            
            elif decision == RiskDecision.REVIEW:
                if proposal.source == "HUMAN_SCSV":
                    return {"status": "REVIEW_REQUIRED", "reason": "Manual review required by Risk Engine."}
                else:
                    return {"status": "REVIEW_DROPPED", "reason": "Autonomous proposals cannot be reviewed. Dropped."}

            return {"status": "FAILED", "reason": "Unknown Risk Decision."}