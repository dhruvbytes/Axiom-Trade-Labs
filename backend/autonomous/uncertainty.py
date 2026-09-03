# backend/autonomous/uncertainty.py

import logging
import time
from backend.autonomous.models import ProposalPriority
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class UncertaintyGate:
    """
    Enforces CORE-X uncertainty semantics at the Admission Boundary.
    🔥 AUTO-UNFREEZE HACK: Automatically clears the freeze after 60 seconds
    if the system crashed (Ctrl+C) or internet dropped, dropping the stuck proposal.
    """
    def __init__(self, freeze_timeout_seconds: float = 60.0):
        # Ab hum sirf account_id save nahi karenge, balki uske freeze hone ka TIME bhi save karenge
        self._uncertain_accounts = {} 
        self.freeze_timeout_seconds = freeze_timeout_seconds

    def set_uncertainty(self, account_id: str, is_uncertain: bool):
        """Marks or clears the uncertainty state for a specific account."""
        if is_uncertain:
            self._uncertain_accounts[account_id] = time.time()
            logger.warning(f"Account '{account_id}' marked UNCERTAIN. System Frozen for {self.freeze_timeout_seconds} seconds.")
        else:
            self._uncertain_accounts.pop(account_id, None)
            logger.info(f"Account '{account_id}' UNCERTAIN state explicitly cleared.")
    
    def get_uncertainty_state(self, account_id: str) -> dict:
        """Read-only method to expose authoritative freeze state for the UI."""
        if account_id in self._uncertain_accounts:
            frozen_at = self._uncertain_accounts[account_id]
            expires_at = frozen_at + self.freeze_timeout_seconds
            now = time.time()
            
            if now > expires_at:
                return {"is_frozen": False}
                
            return {
                "is_frozen": True,
                "frozen_at_utc": datetime.fromtimestamp(frozen_at, timezone.utc).isoformat(),
                "expires_at_utc": datetime.fromtimestamp(expires_at, timezone.utc).isoformat()
            }
        return {"is_frozen": False}
    
    def is_uncertain(self, account_id: str) -> bool:
        """Returns True if the account is uncertain AND the timeout hasn't expired."""
        if account_id in self._uncertain_accounts:
            frozen_at = self._uncertain_accounts[account_id]
            
            # 🚀 AUTO-UNFREEZE MAGIC
            if time.time() - frozen_at > self.freeze_timeout_seconds:
                logger.info(f"⏳ 60-second freeze expired for '{account_id}'. Dropping stuck proposal and Auto-Unfreezing!")
                self._uncertain_accounts.pop(account_id, None) # Freeze hata do
                return False
                
            return True
        return False

    def can_admit_proposal(self, account_id: str, priority: ProposalPriority) -> bool:
        """
        Determines if a proposal can pass the gate based on current account state.
        """
        if self.is_uncertain(account_id):
            if priority == ProposalPriority.P1_RECONCILIATION:
                return True
            else:
                logger.warning(
                    f"Blocked {priority.name} proposal for '{account_id}'. "
                    f"Account is temporarily frozen (Auto-unfreeze pending)."
                )
                return False
        
        # If not uncertain (or if timeout expired), all valid proposals proceed
        return True

# Singleton instance to be used by the Shared Admission Worker
uncertainty_gate = UncertaintyGate()