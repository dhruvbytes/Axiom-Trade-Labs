"""A tiny Bayesian contextual selector over the fixed hypothesis registry."""

from __future__ import annotations
from typing import Callable, Dict, Iterable, List, Tuple
from backend.autonomous.decision_models import CandidateScore, HypothesisEvaluation, RegimeLabel

class BoundedContextualSelector:
    def __init__(self, minimum_action_score: float = 0.50): # 🚀 THRESHOLD LOWERED
        self.minimum_action_score = minimum_action_score

    def select(self, evaluations: Iterable[HypothesisEvaluation], regime: RegimeLabel, preference_lookup: Callable[[str, RegimeLabel], Dict[str, float]]) -> Tuple[HypothesisEvaluation, List[CandidateScore], float]:
        evaluations = list(evaluations)
        scored: List[Tuple[HypothesisEvaluation, CandidateScore]] = []

        for evaluation in evaluations:
            if not evaluation.eligible:
                continue
            preference = preference_lookup(evaluation.hypothesis_id, regime)
            alpha, beta, observations = float(preference["alpha"]), float(preference["beta"]), int(preference["observations"])
            posterior_mean = alpha / (alpha + beta)

            score = (0.70 * evaluation.base_confidence) + (0.30 * posterior_mean)
            if evaluation.hypothesis_id == "no_trade":
                score = 0.50

            scored.append((evaluation, CandidateScore(
                hypothesis_id=evaluation.hypothesis_id, posterior_mean=round(posterior_mean, 4),
                observations=observations, score=round(min(1.0, score), 4)
            )))

        action_candidates = [pair for pair in scored if pair[0].hypothesis_id != "no_trade"]
        no_trade_pair = next(pair for pair in scored if pair[0].hypothesis_id == "no_trade")
        best_action = max(action_candidates, key=lambda pair: pair[1].score, default=None)

        if best_action is None or best_action[1].score < self.minimum_action_score:
            selected_eval, selected_score = no_trade_pair
        else:
            selected_eval, selected_score = best_action

        candidates = [candidate.model_copy(update={"selected": candidate.hypothesis_id == selected_eval.hypothesis_id}) for _, candidate in scored]
        return selected_eval, candidates, selected_score.score