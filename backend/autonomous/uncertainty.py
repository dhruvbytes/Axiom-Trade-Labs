# backend/autonomous/uncertainty.py

import logging
from backend.autonomous.models import ProposalPriority

logger = logging.getLogger(__name__)

class UncertaintyGate:
    """
    Enforces CORE-X uncertainty semantics at the Admission Boundary.
    If CORE-X returns ExecutionState.EXECUTION_UNCERTAIN (reconciliation_required=True),
    the account is locked here. All new trading proposals (P2-P5) are blocked 
    until a P1_RECONCILIATION clears the state.
    """
    def __init__(self):
        # Tracks accounts currently in an UNCERTAIN state in-memory.
        # This state is dynamically updated by the downstream worker after calling CORE-X.
        self._uncertain_accounts = set()

    def set_uncertainty(self, account_id: str, is_uncertain: bool):
        """Marks or clears the uncertainty state for a specific account."""
        if is_uncertain:
            self._uncertain_accounts.add(account_id)
            logger.warning(f"Account '{account_id}' marked UNCERTAIN via CORE-X. New trading proposals deferred.")
        else:
            self._uncertain_accounts.discard(account_id)
            logger.info(f"Account '{account_id}' UNCERTAIN state cleared. Normal admission resumed.")

    def is_uncertain(self, account_id: str) -> bool:
        """Returns True if the account is currently in an uncertain execution state."""
        return account_id in self._uncertain_accounts

    def can_admit_proposal(self, account_id: str, priority: ProposalPriority) -> bool:
        """
        Determines if a proposal can pass the gate based on current account state.
        Only P1_RECONCILIATION can pass if the account is UNCERTAIN.
        """
        if self.is_uncertain(account_id):
            if priority == ProposalPriority.P1_RECONCILIATION:
                return True
            else:
                logger.warning(
                    f"Blocked {priority.name} proposal for '{account_id}'. "
                    f"Account requires P1_RECONCILIATION to clear CORE-X uncertainty."
                )
                return False
        
        # If not uncertain, all valid proposals can proceed to Risk Engine
        return True

# Singleton instance to be used by the Shared Admission Worker
uncertainty_gate = UncertaintyGate()