"""Matures paper outcomes outside the market-event hot path."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, Optional, Set

from backend import alpaca_client
from backend.autonomous.decision_ledger import DecisionLedger, decision_ledger
from backend.autonomous.decision_models import DecisionReceipt, OutcomeRecord
from backend.autonomous.drift import OutcomeDriftMonitor
from backend.autonomous.ui_events import (
    SafeEventMetadata,
    UIActivityEvent,
    UIEventCategory,
    UIEventStatus,
    ui_broadcaster,
)


class OutcomeMonitor:
    """Marks predictions to market after a fixed horizon and updates preferences."""

    def __init__(
        self,
        ledger: DecisionLedger = decision_ledger,
        market_facts_fetcher: Optional[Callable[[list], Awaitable[Dict]]] = None,
        option_quotes_fetcher: Optional[Callable[[list], Awaitable[Dict]]] = None,
        drift_monitor: Optional[OutcomeDriftMonitor] = None,
        on_drift: Optional[Callable[[str, str, object], None]] = None,
    ):
        self.ledger = ledger
        self.market_facts_fetcher = market_facts_fetcher
        self.option_quotes_fetcher = option_quotes_fetcher
        self.drift_monitor = drift_monitor or OutcomeDriftMonitor()
        self.on_drift = on_drift
        self._scheduled: Set[str] = set()
        self._tasks: Set[asyncio.Task] = set()

    def schedule(self, receipt: DecisionReceipt) -> None:
        if not receipt.outcome_due_at_utc or receipt.decision_id in self._scheduled:
            return
        self._scheduled.add(receipt.decision_id)
        task = asyncio.create_task(self._wait_and_mature(receipt))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def recover_due(self) -> None:
        for receipt in await asyncio.to_thread(self.ledger.pending_decisions):
            await self.mature(receipt)

    async def _wait_and_mature(self, receipt: DecisionReceipt) -> None:
        try:
            due = datetime.fromisoformat(receipt.outcome_due_at_utc)
            seconds = max(0.0, (due - datetime.now(timezone.utc)).total_seconds())
            await asyncio.sleep(seconds)
            await self.mature(receipt)
        finally:
            self._scheduled.discard(receipt.decision_id)

    async def mature(self, receipt: DecisionReceipt) -> bool:
        if self.market_facts_fetcher is None:
            return False
        try:
            facts = await self.market_facts_fetcher([receipt.snapshot.symbol])
            exit_price = float(facts.get("quotes", {}).get(receipt.snapshot.symbol, 0.0))
        except Exception:
            return False
        if exit_price <= 0:
            return False

        stock_gross_return = (exit_price - receipt.snapshot.event_price) / receipt.snapshot.event_price

        # Option contract M2M evaluation if contract was selected
        contract_sym = receipt.selected_contract_symbol
        opt_entry_price = None
        opt_exit_price = None
        contract_return = None

        if contract_sym:
            # Extract entry price from evidence
            ev = receipt.evidence.get(receipt.selected_hypothesis_id)
            if ev and ev.facts:
                opt_fact = ev.facts.get("jit_option_contract")
                if opt_fact:
                    opt_entry_price = float(opt_fact.get("mid", 0.0) or opt_fact.get("ask", 0.0) or 0.0)

            # Fetch authoritative current exit quote for the option contract
            fetcher = self.option_quotes_fetcher or (lambda syms: alpaca_client.get_option_quotes(syms))
            try:
                q_map = await fetcher([contract_sym])
                q = q_map.get(contract_sym, {})
                opt_exit_price = float(q.get("mid", 0.0) or q.get("bid", 0.0) or 0.0)
            except Exception:
                opt_exit_price = None

            if opt_entry_price and opt_exit_price and opt_entry_price > 0 and opt_exit_price > 0:
                contract_return = (opt_exit_price - opt_entry_price) / opt_entry_price

        outcomes = []
        for evaluation in receipt.evaluations:
            if not evaluation.eligible:
                continue

            is_opt_hypothesis = evaluation.hypothesis_id.startswith("option_")

            if is_opt_hypothesis and evaluation.hypothesis_id == receipt.selected_hypothesis_id and contract_return is not None:
                # Real option contract M2M outcome
                gross_return = contract_return
                success = (evaluation.expected_direction * gross_return) > 0.005
                outcomes.append(
                    OutcomeRecord(
                        decision_id=receipt.decision_id,
                        hypothesis_id=evaluation.hypothesis_id,
                        regime=receipt.regime.label,
                        symbol=receipt.snapshot.symbol,
                        expected_direction=evaluation.expected_direction,
                        entry_price=opt_entry_price,
                        exit_price=opt_exit_price,
                        gross_return_pct=round(gross_return, 6),
                        success=success,
                        contract_symbol=contract_sym,
                        contract_entry_price=opt_entry_price,
                        contract_exit_price=opt_exit_price,
                    )
                )
            elif is_opt_hypothesis:
                # Counterfactual option evaluation proxy from underlying stock return
                gross_return = stock_gross_return
                success = (evaluation.expected_direction * gross_return) > 0.001
                outcomes.append(
                    OutcomeRecord(
                        decision_id=receipt.decision_id,
                        hypothesis_id=evaluation.hypothesis_id,
                        regime=receipt.regime.label,
                        symbol=receipt.snapshot.symbol,
                        expected_direction=evaluation.expected_direction,
                        entry_price=receipt.snapshot.event_price,
                        exit_price=exit_price,
                        gross_return_pct=round(gross_return, 6),
                        success=success,
                    )
                )
            elif evaluation.expected_direction == 0:
                gross_return = stock_gross_return
                success = abs(gross_return) < 0.005
                outcomes.append(
                    OutcomeRecord(
                        decision_id=receipt.decision_id,
                        hypothesis_id=evaluation.hypothesis_id,
                        regime=receipt.regime.label,
                        symbol=receipt.snapshot.symbol,
                        expected_direction=evaluation.expected_direction,
                        entry_price=receipt.snapshot.event_price,
                        exit_price=exit_price,
                        gross_return_pct=round(gross_return, 6),
                        success=success,
                    )
                )
            else:
                gross_return = stock_gross_return
                success = (evaluation.expected_direction * gross_return) > 0.001
                outcomes.append(
                    OutcomeRecord(
                        decision_id=receipt.decision_id,
                        hypothesis_id=evaluation.hypothesis_id,
                        regime=receipt.regime.label,
                        symbol=receipt.snapshot.symbol,
                        expected_direction=evaluation.expected_direction,
                        entry_price=receipt.snapshot.event_price,
                        exit_price=exit_price,
                        gross_return_pct=round(gross_return, 6),
                        success=success,
                    )
                )

        await asyncio.to_thread(self.ledger.record_outcomes, outcomes)
        await self._assess_drift(receipt)

        # Broadcast learning outcome to deterministic UI
        for out in outcomes:
            if out.hypothesis_id == receipt.selected_hypothesis_id:
                sign = "+" if out.gross_return_pct >= 0 else ""
                result_str = "WIN" if out.success else "LOSS"
                ui_broadcaster.publish(
                    UIActivityEvent(
                        category=UIEventCategory.LEARNING,
                        status=UIEventStatus.SUCCESS if out.success else UIEventStatus.INFO,
                        message=f"Outcome matured: {out.hypothesis_id} ({sign}{out.gross_return_pct:.2%}) -> {result_str}",
                        safe_metadata=SafeEventMetadata(
                            symbol=out.symbol,
                            decision_id=out.decision_id,
                            hypothesis=out.hypothesis_id,
                            regime=out.regime.value,
                            outcome=result_str,
                            contract_symbol=out.contract_symbol,
                            asset_class="option" if out.contract_symbol else "equity",
                        ),
                    )
                )

        return True

    async def _assess_drift(self, receipt: DecisionReceipt) -> None:
        for evaluation in receipt.evaluations:
            if evaluation.hypothesis_id == "no_trade" or not evaluation.eligible:
                continue
            successes = await asyncio.to_thread(
                self.ledger.recent_successes, evaluation.hypothesis_id, receipt.regime.label
            )
            assessment = self.drift_monitor.assess(successes)
            if assessment.detected and self.on_drift:
                self.on_drift(evaluation.hypothesis_id, receipt.regime.label.value, assessment)

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self._scheduled.clear()

