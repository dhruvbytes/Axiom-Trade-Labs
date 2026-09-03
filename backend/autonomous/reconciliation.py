"""Fail-closed reconciliation coordination for CORE-X uncertainty."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Dict

from backend.autonomous.decision_ledger import DecisionLedger, decision_ledger
from backend.autonomous.uncertainty import UncertaintyGate, uncertainty_gate
from backend.execution.journal import ExecutionJournal, execution_journal


@dataclass(frozen=True)
class ReconciliationResult:
    status: str
    reason: str


class ReconciliationService:
    """Restores uncertainty after restart and refuses unsafe automatic clearing.

    Authoritative account/position reads are valuable evidence, but cannot prove
    the disposition of an unknown post-dispatch order on their own. Therefore an
    uncertain account remains frozen until an explicitly authorized reconciliation
    process marks the execution journal resolved.
    """

    def __init__(
        self,
        journal: ExecutionJournal = execution_journal,
        gate: UncertaintyGate = uncertainty_gate,
        ledger: DecisionLedger = decision_ledger,
        account_fetcher: Callable[[], Dict] | None = None,
        positions_fetcher: Callable[[], list] | None = None,
    ):
        self.journal = journal
        self.gate = gate
        self.ledger = ledger
        self.account_fetcher = account_fetcher
        self.positions_fetcher = positions_fetcher

    async def restore_uncertainty(self, account_id: str = "default_account") -> ReconciliationResult:
        unresolved = await asyncio.to_thread(self.journal.unresolved_execution_count)
        if unresolved:
            self.gate.set_uncertainty(account_id, True)
            reason = f"{unresolved} durable CORE-X execution record(s) require reconciliation."
            await asyncio.to_thread(self.ledger.record_reconciliation, account_id, "UNCERTAIN_RESTORED", reason)
            return ReconciliationResult("UNCERTAIN_RESTORED", reason)
        return ReconciliationResult("CLEAR", "No durable CORE-X uncertainty found at startup.")

    async def reconcile_observations(self, account_id: str = "default_account") -> ReconciliationResult:
        """Fetch evidence and retain the freeze when order disposition is unknown."""
        if self.account_fetcher is None or self.positions_fetcher is None:
            reason = "Authoritative reconciliation providers are unavailable; account remains frozen."
            await asyncio.to_thread(self.ledger.record_reconciliation, account_id, "FAILED_SAFE", reason)
            return ReconciliationResult("FAILED_SAFE", reason)
        try:
            account, positions = await asyncio.gather(
                asyncio.to_thread(self.account_fetcher),
                asyncio.to_thread(self.positions_fetcher),
            )
            if not account or positions is None:
                raise RuntimeError("authoritative account or positions are unavailable")
        except Exception as error:
            reason = f"Authoritative reconciliation failed: {error}"
            await asyncio.to_thread(self.ledger.record_reconciliation, account_id, "FAILED_SAFE", reason)
            return ReconciliationResult("FAILED_SAFE", reason)

        unresolved = await asyncio.to_thread(self.journal.unresolved_execution_count)
        if unresolved:
            self.gate.set_uncertainty(account_id, True)
            reason = f"Authoritative facts refreshed, but {unresolved} unknown execution(s) still need explicit resolution."
            await asyncio.to_thread(self.ledger.record_reconciliation, account_id, "MANUAL_RESOLUTION_REQUIRED", reason)
            return ReconciliationResult("MANUAL_RESOLUTION_REQUIRED", reason)

        # If no durable uncertainty remains, clearing an in-memory stale gate is
        # safe because CORE-X has no unresolved post-dispatch state.
        self.gate.set_uncertainty(account_id, False)
        reason = "Authoritative account facts refreshed and no unresolved CORE-X state remains."
        await asyncio.to_thread(self.ledger.record_reconciliation, account_id, "RECONCILED", reason)
        return ReconciliationResult("RECONCILED", reason)

