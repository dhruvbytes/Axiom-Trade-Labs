"""The intentionally small, approved analytical-hypothesis registry."""

from __future__ import annotations
from typing import List
from backend.autonomous.decision_models import (
    ContextSnapshot, HypothesisAction, HypothesisEvaluation, RegimeEstimate, RegimeLabel,
)

class BoundedHypothesisRegistry:
    STOCK_EVIDENCE = ["fresh_symbol_quote", "fresh_market_state", "portfolio_exposure"]
    OPTION_EVIDENCE = ["fresh_symbol_quote", "fresh_market_state", "portfolio_exposure", "jit_option_contract"]

    def evaluate(self, snapshot: ContextSnapshot, regime: RegimeEstimate, allow_options: bool = True) -> List[HypothesisEvaluation]:
        change = snapshot.material_change_pct
        held_qty = snapshot.held_quantity()
        
        evaluations = [
            HypothesisEvaluation(
                hypothesis_id="trend_continuation",
                display_name="Trend continuation analysis",
                eligible=(snapshot.is_market_open and snapshot.data_fresh and change > 0 and regime.label in (RegimeLabel.RISK_ON, RegimeLabel.NEUTRAL) and not regime.transition_pending),
                action=HypothesisAction.BUY_STOCK,
                expected_direction=1,
                evidence_requirements=self.STOCK_EVIDENCE,
                base_confidence=0.68,
                reason="Positive material move assessed against current broad market state.",
            ),
            HypothesisEvaluation(
                hypothesis_id="mean_reversion",
                display_name="Mean reversion analysis",
                eligible=(snapshot.is_market_open and snapshot.data_fresh and change < 0 and regime.label == RegimeLabel.NEUTRAL and not regime.transition_pending),
                action=HypothesisAction.BUY_STOCK,
                expected_direction=1,
                evidence_requirements=self.STOCK_EVIDENCE,
                base_confidence=0.61,
                reason="Negative material move assessed as a possible temporary dislocation.",
            ),
            HypothesisEvaluation(
                hypothesis_id="defensive_reduction",
                display_name="Defensive reduction analysis",
                eligible=(snapshot.is_market_open and snapshot.data_fresh and held_qty > 0 and change < 0 and regime.label == RegimeLabel.STRESS),
                action=HypothesisAction.SELL_STOCK,
                expected_direction=-1,
                evidence_requirements=self.STOCK_EVIDENCE,
                base_confidence=0.72,
                reason="Existing exposure is reviewed during a confirmed stress state.",
                is_risk_reduction=True,
            ),
            HypothesisEvaluation(
                hypothesis_id="no_trade",
                display_name="No-trade / evidence insufficient",
                eligible=True,
                action=HypothesisAction.NO_TRADE,
                expected_direction=0,
                evidence_requirements=[],
                base_confidence=0.55,
                reason="Abstention remains a first-class, safety-preserving alternative.",
            ),
        ]

        # 🚀 THE FIX: Dynamically append Options Hypotheses if allowed
        if allow_options:
            evaluations.extend([
                HypothesisEvaluation(
                    hypothesis_id="option_bullish_directional",
                    display_name="Bullish directional option analysis",
                    eligible=(snapshot.is_market_open and snapshot.data_fresh and change > 0 and regime.label == RegimeLabel.RISK_ON and not regime.transition_pending),
                    action=HypothesisAction.BUY_CALL,
                    expected_direction=1,
                    evidence_requirements=self.OPTION_EVIDENCE,
                    base_confidence=0.66,
                    reason="Positive material move assessed; risk-on regime supports long call.",
                ),
                HypothesisEvaluation(
                    hypothesis_id="option_bearish_directional",
                    display_name="Bearish directional option analysis",
                    eligible=(snapshot.is_market_open and snapshot.data_fresh and change < 0 and regime.label in (RegimeLabel.STRESS, RegimeLabel.NEUTRAL) and not regime.transition_pending),
                    action=HypothesisAction.BUY_PUT,
                    expected_direction=-1,
                    evidence_requirements=self.OPTION_EVIDENCE,
                    base_confidence=0.64,
                    reason="Negative material move assessed; stress/neutral regime supports long put.",
                ),
            ])

        return evaluations