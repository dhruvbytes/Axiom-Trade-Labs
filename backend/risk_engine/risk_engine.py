# backend/risk_engine/risk_engine.py
from typing import List

from backend.risk_engine.risk_models import (
    RiskDecision, RiskGateResult, RiskEngineOutput, 
    SystemHardLimits, UserRiskProfile, AssetFreshnessPolicy,
    UniversalTradeProposal, SystemFacts
)
from backend.risk_engine.payoff_utils import calculate_payoff_profile, PayoffResult
from backend.risk_engine.risk_checkers import (
    check_freshness_gate, check_semantic_gate, check_loss_drawdown_gate,
    check_payoff_risk_gate, check_account_state_gate, check_budget_gate,
    check_projected_portfolio_gate, check_market_regime_gate, check_volatility_sizing_gate
)

class RiskEngine:
    def __init__(self):
        self.hard_limits = SystemHardLimits()
        self.risk_profile = UserRiskProfile()
        self.freshness_policy = AssetFreshnessPolicy()

    def evaluate_proposal(
        self,
        proposal: UniversalTradeProposal,
        facts: SystemFacts,
        daily_loss_pct: float = 0.0 # Kept as parameter since it requires historical daily equity tracking outside facts
    ) -> RiskEngineOutput:
        """
        The Master NMLI Pipeline. Runs the TradeProposal through 9 deterministic gates sequentially.
        """
        gate_results: List[RiskGateResult] = []
        
        # ---------------------------------------------------------
        # GATE 1: SEMANTIC / STRUCTURAL
        # ---------------------------------------------------------
        res_semantic = check_semantic_gate(proposal)
        gate_results.append(res_semantic)
        if res_semantic.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # GATE 2: FRESHNESS
        # ---------------------------------------------------------
        res_fresh = check_freshness_gate(proposal, facts, self.freshness_policy)
        gate_results.append(res_fresh)
        if res_fresh.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # PRE-COMPUTATION: PIECEWISE PAYOFF GRAPH
        # ---------------------------------------------------------
        payoff: PayoffResult = calculate_payoff_profile(proposal, facts)

        # ---------------------------------------------------------
        # GATE 3: PAYOFF RISK (Infinite Risk Check)
        # ---------------------------------------------------------
        res_payoff = check_payoff_risk_gate(payoff)
        gate_results.append(res_payoff)
        if res_payoff.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # GATE 4: LOSS / DRAWDOWN (Kill Switch Check)
        # ---------------------------------------------------------
        res_loss = check_loss_drawdown_gate(daily_loss_pct, self.hard_limits, self.risk_profile)
        gate_results.append(res_loss)
        if res_loss.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # GATE 5: ACCOUNT STATE / MARGIN
        # ---------------------------------------------------------
        res_account = check_account_state_gate(proposal, facts, payoff)
        gate_results.append(res_account)
        if res_account.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # GATE 6: BUDGET VERIFICATION
        # ---------------------------------------------------------
        res_budget = check_budget_gate(proposal, payoff)
        gate_results.append(res_budget)
        if res_budget.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # GATE 7: PROJECTED PORTFOLIO CONCENTRATION
        # ---------------------------------------------------------
        res_portfolio = check_projected_portfolio_gate(proposal, facts, self.hard_limits, self.risk_profile)
        gate_results.append(res_portfolio)
        if res_portfolio.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # GATE 8: MARKET REGIME
        # ---------------------------------------------------------
        regime_state = "Neutral" # Derived natively from facts now instead of external function call overhead for simplicity in gating, can be expanded.
        if facts.market_state.spy_price > facts.market_state.spy_sma_50 and (facts.market_state.spy_atr_14/facts.market_state.spy_price) < 0.015:
             regime_state = "Risk-On"
        elif facts.market_state.spy_price <= facts.market_state.spy_sma_50 and (facts.market_state.spy_atr_14/facts.market_state.spy_price) > 0.015:
             regime_state = "Risk-Off"
             
        res_regime = check_market_regime_gate(regime_state)
        gate_results.append(res_regime)
        if res_regime.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # GATE 9: VOLATILITY SIZING
        # ---------------------------------------------------------
        res_volatility = check_volatility_sizing_gate(proposal, facts, facts.market_state.spy_atr_14, self.risk_profile)
        gate_results.append(res_volatility)
        if res_volatility.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # FINAL DETERMINATION
        # ---------------------------------------------------------
        return self._build_final_output(gate_results)

    def _build_final_output(self, gate_results: List[RiskGateResult]) -> RiskEngineOutput:
        """Aggregates all gate results to determine the final system status."""
        has_blocks = any(res.status == RiskDecision.BLOCK for res in gate_results)
        has_reviews = any(res.status == RiskDecision.REVIEW for res in gate_results)
        
        if has_blocks:
            final_decision = RiskDecision.BLOCK
            block_reason = next(res.explanation for res in gate_results if res.status == RiskDecision.BLOCK)
            summary = f"Proposal REJECTED. {block_reason}"
        elif has_reviews:
            final_decision = RiskDecision.REVIEW
            summary = "Proposal requires REVIEW due to policy or market regime flags."
        else:
            final_decision = RiskDecision.ALLOW
            summary = "Proposal passes all system hard limits and user policies."

        return RiskEngineOutput(
            final_decision=final_decision,
            gate_results=gate_results,
            summary_explanation=summary
        )

master_risk_engine = RiskEngine()