"""Low-cost performance-drift detection for bounded strategy preference updates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DriftAssessment:
    detected: bool
    observations: int
    ewma_success: float
    reason: str


class OutcomeDriftMonitor:
    """Detect sustained poor paper outcomes, not single-trade noise."""

    def __init__(self, minimum_observations: int = 8, decay: float = 0.85, threshold: float = 0.35):
        self.minimum_observations = minimum_observations
        self.decay = decay
        self.threshold = threshold

    def assess(self, successes: Iterable[bool]) -> DriftAssessment:
        values = list(successes)
        if len(values) < self.minimum_observations:
            return DriftAssessment(False, len(values), 0.5, "Insufficient mature outcomes for drift assessment.")

        ewma = 0.5
        for success in values:
            ewma = (self.decay * ewma) + ((1.0 - self.decay) * float(success))
        detected = ewma < self.threshold
        return DriftAssessment(
            detected=detected,
            observations=len(values),
            ewma_success=round(ewma, 4),
            reason="Sustained outcome degradation detected." if detected else "Outcome performance remains within drift tolerance.",
        )

