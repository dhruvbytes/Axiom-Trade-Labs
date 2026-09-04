"""Bounded adaptive controller placed before Admission -> Risk -> CORE-X."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Dict, Optional, Set, Tuple
from uuid import uuid4
from typing import Any
from backend import alpaca_client
from backend.autonomous.decision_ledger import DecisionLedger, decision_ledger
from backend.autonomous.decision_models import (
    ContextSnapshot,
    DecisionReceipt,
    DecisionStatus,
    HypothesisAction,
)

from backend.autonomous.settings_manager import runtime_policy_manager
from backend.autonomous.evidence import EvidencePlanner
from backend.autonomous.hypotheses import BoundedHypothesisRegistry
from backend.autonomous.outcomes import OutcomeMonitor
from backend.autonomous.regime import RegimeEstimator
from backend.autonomous.selector import BoundedContextualSelector
from backend.autonomous.trigger import TriggerResult
from backend.autonomous.models import AutonomousEvent
from backend.autonomous.ui_events import (
    SafeEventMetadata,
    UIActivityEvent,
    UIEventCategory,
    UIEventStatus,
    ui_broadcaster,
)

@dataclass
class ControllerResult:
    receipt: Optional[DecisionReceipt]
    proposal_payload: Optional[Dict]
    is_risk_reduction: bool = False


class AuthoritativeContextBuilder:
    """Collects the compact facts needed for a decision, separately from risk."""

    def __init__(
        self,
        portfolio_summary_fetcher: Callable[[], Dict],
        positions_fetcher: Callable[[], list],
        market_facts_fetcher: Callable[[list], Awaitable[Dict]],
    ):
        self.portfolio_summary_fetcher = portfolio_summary_fetcher
        self.positions_fetcher = positions_fetcher
        self.market_facts_fetcher = market_facts_fetcher

    async def build(self, event: AutonomousEvent) -> Optional[ContextSnapshot]:
        try:
            summary, positions, market_facts = await asyncio.gather(
                asyncio.to_thread(self.portfolio_summary_fetcher),
                asyncio.to_thread(self.positions_fetcher),
                self.market_facts_fetcher([event.symbol]),
            )
            equity = float(summary.get("portfolio_value", 0))
            buying_power = float(summary.get("buying_power", 0))
            spy_price = float(market_facts.get("spy_price", 0))
            spy_sma_50 = float(market_facts.get("spy_sma_50", spy_price))
            spy_atr_14 = float(market_facts.get("spy_atr_14", 0))
            quote_price = float(market_facts.get("quotes", {}).get(event.symbol, event.price or 0))
            if min(equity, spy_price, spy_sma_50, quote_price) <= 0 or event.price is None or event.price <= 0:
                return None
            material_change = float(event.raw_data.get("material_change_pct", 0.0))
            return ContextSnapshot(
                symbol=event.symbol.upper(),
                event_price=float(event.price),
                material_change_pct=material_change,
                equity=equity,
                buying_power=max(0.0, buying_power),
                positions=positions,
                spy_price=spy_price,
                spy_sma_50=spy_sma_50,
                spy_atr_14=max(0.0, spy_atr_14),
                is_market_open=bool(market_facts.get("is_market_open", True)),
                data_fresh=True,
            )
        except Exception:
            return None


class BoundedDecisionController:
    """Coordinates context, approved hypotheses, evidence, and safe abstention."""

    def __init__(
        self,
        context_builder: AuthoritativeContextBuilder,
        ledger: DecisionLedger = decision_ledger,
        registry: Optional[BoundedHypothesisRegistry] = None,
        regime_estimator: Optional[RegimeEstimator] = None,
        selector: Optional[BoundedContextualSelector] = None,
        evidence_planner: Optional[EvidencePlanner] = None,
        outcome_monitor: Optional[OutcomeMonitor] = None,
    ):
        self.context_builder = context_builder
        self.ledger = ledger
        self.registry = registry or BoundedHypothesisRegistry()
        self.regime_estimator = regime_estimator or RegimeEstimator()
        self.selector = selector or BoundedContextualSelector()
        self.evidence_planner = evidence_planner or EvidencePlanner(
            option_chain_fetcher=alpaca_client.get_options_chain_jit,
            option_quotes_fetcher=alpaca_client.get_option_quotes,
        )
        self.suspended_hypotheses: Set[Tuple[str, str]] = set()
        self.outcome_monitor = outcome_monitor or OutcomeMonitor(
            ledger=ledger,
            market_facts_fetcher=context_builder.market_facts_fetcher,
            option_quotes_fetcher=alpaca_client.get_option_quotes,
            on_drift=self._on_drift,
        )

    async def start(self) -> None:
        await asyncio.to_thread(self.ledger.bootstrap)
        await self.outcome_monitor.recover_due()

    async def stop(self) -> None:
        await self.outcome_monitor.stop()

    async def handle_trigger(self, event: AutonomousEvent, trigger: TriggerResult) -> ControllerResult:
        # 🚀 1. Obtain ONE immutable snapshot for the entire evaluation
        policy_snapshot = runtime_policy_manager.get_current()
        
        snapshot = await self.context_builder.build(event)
        if snapshot is None:
            # STRICT OBSERVABILITY: Log the fail-closed event to the UI instead of silent failure
            ui_broadcaster.publish(
                UIActivityEvent(
                    category=UIEventCategory.DECISION,
                    status=UIEventStatus.BLOCKED,
                    message="Decision aborted: Missing authoritative market context.",
                    safe_metadata=SafeEventMetadata(
                        symbol=event.symbol, 
                        reason="Stale or missing JIT facts (SPY/Quotes). Safe fail-closed triggered."
                    )
                )
            )
            return ControllerResult(receipt=None, proposal_payload=None)

        regime = self.regime_estimator.update(snapshot)
        
        # 🚀 2. Options continuity validation: inject toggle into registry
        original_evaluations = self.registry.evaluate(
            snapshot, regime, allow_options=policy_snapshot.allow_auto_options
        )
        evaluations = []
        evidence = {}
        for evaluation in original_evaluations:
            if (evaluation.hypothesis_id, regime.label.value) in self.suspended_hypotheses:
                evaluations.append(evaluation.model_copy(update={"eligible": False, "reason": "Suspended after sustained paper-outcome drift."}))
                continue
            evidence_result = await self.evidence_planner.collect(evaluation, snapshot)
            evidence[evaluation.hypothesis_id] = evidence_result
            if evaluation.hypothesis_id != "no_trade" and not evidence_result.complete:
                evaluations.append(evaluation.model_copy(update={"eligible": False, "reason": evidence_result.reason}))
            else:
                evaluations.append(evaluation)

        preferences = {
            evaluation.hypothesis_id: await asyncio.to_thread(
                self.ledger.get_preference, evaluation.hypothesis_id, regime.label
            )
            for evaluation in evaluations
            if evaluation.eligible
        }
        
        # 🚀 3. Pass minimum_action_score dynamically to selector if needed (Assuming selector uses it internally)
        selected, candidate_scores, confidence = self.selector.select(
            evaluations,
            regime.label,
            lambda hypothesis_id, _: preferences[hypothesis_id],
        )

        selected_contract = None
        selected_contract_symbol = None
        if selected.action in (HypothesisAction.BUY_CALL, HypothesisAction.BUY_PUT):
            ev_result = evidence.get(selected.hypothesis_id)
            if ev_result and ev_result.facts:
                selected_contract = ev_result.facts.get("jit_option_contract")
                if selected_contract:
                    selected_contract_symbol = selected_contract.get("contract_symbol")

        status = DecisionStatus.NO_TRADE
        reason = selected.reason
        payload = None
        decision_id = uuid4().hex
        
        # 🚀 4. Check policy_snapshot.allow_new_risk here!
        if selected.action != HypothesisAction.NO_TRADE and policy_snapshot.allow_new_risk:
            payload = self._proposal_payload(
                snapshot, trigger, decision_id, selected.hypothesis_id, selected.action, policy_snapshot.max_auto_stock_qty, selected_contract
            )
            if payload is not None:
                # 🚀 5. Attach risk_per_trade_pct dynamically for the Risk Engine to read from proposal
                payload["metadata"]["dynamic_risk_per_trade_pct"] = policy_snapshot.risk_per_trade_pct
                status = DecisionStatus.PROPOSED
                reason = f"Selected {selected.display_name} after bounded contextual comparison."
            else:
                status = DecisionStatus.NO_TRADE
                reason = "Option proposal could not be constructed from contract evidence."
        elif selected.action != HypothesisAction.NO_TRADE:
            reason = "Approved hypothesis selected, but static paper-burn-in policy currently permits no new risk."

        due_at = datetime.now(timezone.utc) + timedelta(seconds=max(1, 300)) # Defaulted to 300s horizon
        receipt = DecisionReceipt(
            decision_id=decision_id,
            trigger_fingerprint=trigger.fingerprint,
            snapshot=snapshot,
            regime=regime,
            evaluations=evaluations,
            evidence=evidence,
            candidate_scores=candidate_scores,
            selected_hypothesis_id=selected.hypothesis_id,
            status=status,
            confidence=confidence,
            reason=reason,
            proposal_payload=payload,
            outcome_due_at_utc=due_at.isoformat(),
            selected_contract_symbol=selected_contract_symbol,
        )
        await asyncio.to_thread(self.ledger.record_decision, receipt)
        self.outcome_monitor.schedule(receipt)
        msg = (
            f"Selected {selected.display_name} ({selected_contract_symbol})."
            if (status == DecisionStatus.PROPOSED and selected_contract_symbol)
            else (
                f"Selected {selected.display_name}."
                if status == DecisionStatus.PROPOSED
                else "Autonomous decision: NO_TRADE."
            )
        )
        ui_broadcaster.publish(
            UIActivityEvent(
                category=UIEventCategory.DECISION,
                status=UIEventStatus.SUCCESS if status == DecisionStatus.PROPOSED else UIEventStatus.INFO,
                message=msg,
                safe_metadata=SafeEventMetadata(
                    symbol=snapshot.symbol,
                    decision_id=receipt.decision_id,
                    regime=regime.label.value,
                    hypothesis=selected.hypothesis_id,
                    confidence=confidence,
                    reason=reason,
                    contract_symbol=selected_contract_symbol,
                    asset_class="option" if selected_contract_symbol else "equity",
                ),
            )
        )
        return ControllerResult(
            receipt=receipt,
            proposal_payload=payload,
            is_risk_reduction=selected.is_risk_reduction,
        )

    def _proposal_payload(
        self,
        snapshot: ContextSnapshot,
        trigger: TriggerResult,
        decision_id: str,
        hypothesis_id: str,
        action: HypothesisAction,
        max_auto_stock_qty: int, # 🚀 6. Added qty as parameter
        selected_contract: Optional[Dict] = None,
    ) -> Optional[Dict]:
        if action in (HypothesisAction.BUY_CALL, HypothesisAction.BUY_PUT):
            if not selected_contract or not selected_contract.get("contract_symbol"):
                return None
            return {
                "tool_name": "place_option_order",
                "arguments": {
                    "symbol": selected_contract["contract_symbol"],
                    "side": "buy",
                    "qty": "1",
                    "type": "market",
                    "time_in_force": "day",
                    "position_intent": "buy_to_open",
                },
                "metadata": {
                    "source": "AUTONOMOUS_DECISION",
                    "decision_id": decision_id,
                    "trigger_fingerprint": trigger.fingerprint,
                    "hypothesis_id": hypothesis_id,
                    "asset_class": "option",
                    "underlying_symbol": snapshot.symbol,
                    "strike": selected_contract.get("strike"),
                    "expiry": selected_contract.get("expiry"),
                    "option_type": selected_contract.get("option_type"),
                    "contract_mid": selected_contract.get("mid"),
                    "provenance": snapshot.provenance,
                },
            }

        side = "buy" if action == HypothesisAction.BUY_STOCK else "sell"
        return {
            "tool_name": "place_stock_order",
            "arguments": {
                "symbol": snapshot.symbol,
                "side": side,
                "qty": str(max_auto_stock_qty), # 🚀 7. Dynamic qty used here
                "type": "market",
                "time_in_force": "day",
            },
            "metadata": {
                "source": "AUTONOMOUS_DECISION",
                "decision_id": decision_id,
                "trigger_fingerprint": trigger.fingerprint,
                "hypothesis_id": hypothesis_id,
                "provenance": snapshot.provenance,
            },
        }

    def _on_drift(self, hypothesis_id: str, regime: str, assessment: object) -> None:
        self.suspended_hypotheses.add((hypothesis_id, regime))
        ui_broadcaster.publish(
            UIActivityEvent(
                category=UIEventCategory.LEARNING,
                status=UIEventStatus.WARNING,
                message="Outcome drift detected; analytical approach suspended.",
                safe_metadata=SafeEventMetadata(hypothesis=hypothesis_id, regime=regime, reason=getattr(assessment, "reason", "Drift detected")),
            )
        )

    def status_snapshot(self) -> Dict[str, Any]:
        """Provides a safe, public status snapshot for admin/observability APIs."""
        regime_label = (
            self.regime_estimator._accepted.value
            if hasattr(self.regime_estimator, "_accepted")
            else "UNKNOWN"
        )
        policy_snapshot = runtime_policy_manager.get_current() # 🚀 8. Status API reads active snapshot
        return {
            "policy": {
                "outcome_horizon_seconds": 300,
                "max_auto_stock_quantity": policy_snapshot.max_auto_stock_qty,
                "allow_new_risk": policy_snapshot.allow_new_risk,
                "allow_auto_options": policy_snapshot.allow_auto_options,
            },
            "regime": regime_label,
            "suspended_hypotheses": [
                {"hypothesis_id": hyp, "regime": reg}
                for hyp, reg in self.suspended_hypotheses
            ],
            "active_scheduled_outcomes": len(self.outcome_monitor._scheduled),
        }