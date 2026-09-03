"""Small, hysteresis-protected market-state estimator for the decision layer."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict

from backend.autonomous.decision_models import ContextSnapshot, RegimeEstimate, RegimeLabel


class RegimeEstimator:
    """Infer a bounded market state without turning a state label into an order.

    State changes need repeated confirming snapshots.  This prevents one noisy
    quote from creating strategy churn while remaining inexpensive enough for a
    laptop event loop.
    """

    def __init__(self, confirmations_required: int = 2, stress_volatility_pct: float = 0.015):
        self.confirmations_required = max(1, confirmations_required)
        self.stress_volatility_pct = stress_volatility_pct
        self._accepted: RegimeLabel = RegimeLabel.UNKNOWN
        self._candidate: RegimeLabel = RegimeLabel.UNKNOWN
        self._candidate_count: int = 0

    def update(self, snapshot: ContextSnapshot) -> RegimeEstimate:
        volatility_pct = snapshot.spy_atr_14 / snapshot.spy_price if snapshot.spy_price > 0 else 0.0
        inferred = self._infer(snapshot, volatility_pct)

        if self._accepted == RegimeLabel.UNKNOWN:
            self._accepted = inferred
            self._candidate = inferred
            self._candidate_count = self.confirmations_required
            return self._estimate(inferred, volatility_pct, False, "Initial authoritative market-state estimate.")

        if inferred == self._accepted:
            self._candidate = inferred
            self._candidate_count = self.confirmations_required
            return self._estimate(inferred, volatility_pct, False, "Market state remains confirmed.")

        if inferred != self._candidate:
            self._candidate = inferred
            self._candidate_count = 1
        else:
            self._candidate_count += 1

        if self._candidate_count >= self.confirmations_required:
            previous = self._accepted
            self._accepted = inferred
            return self._estimate(inferred, volatility_pct, False, f"Market state changed from {previous.value} after confirmation.")

        return self._estimate(
            self._accepted,
            volatility_pct,
            True,
            f"Potential {inferred.value} state awaiting confirmation; retaining {self._accepted.value}.",
        )

    def _infer(self, snapshot: ContextSnapshot, volatility_pct: float) -> RegimeLabel:
        if volatility_pct >= self.stress_volatility_pct and snapshot.spy_price <= snapshot.spy_sma_50:
            return RegimeLabel.STRESS
        if snapshot.spy_price > snapshot.spy_sma_50 and volatility_pct < self.stress_volatility_pct:
            return RegimeLabel.RISK_ON
        return RegimeLabel.NEUTRAL

    @staticmethod
    def _estimate(label: RegimeLabel, volatility_pct: float, transition_pending: bool, reason: str) -> RegimeEstimate:
        confidence = 0.6 if transition_pending else 0.8
        if label == RegimeLabel.UNKNOWN:
            confidence = 0.0
        return RegimeEstimate(
            label=label,
            confidence=confidence,
            volatility_pct=round(volatility_pct, 6),
            transition_pending=transition_pending,
            reason=reason,
        )

