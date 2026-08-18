from typing import List, Dict

from backend.risk_models import (
    RiskDecision, RiskGateResult, RiskEngineOutput, 
    SystemHardLimits, UserRiskProfile
)
from backend.risk_checkers import (
    check_semantic_gate,
    check_account_state_gate,
    check_market_regime_gate,
    check_volatility_sizing_gate,
    check_projected_portfolio_gate,
    check_loss_drawdown_gate
)
from backend.market_data_utils import calculate_atr, determine_market_regime

class RiskEngine:
    def __init__(self):
        # Initialize with our frozen default policies
        self.hard_limits = SystemHardLimits()
        self.risk_profile = UserRiskProfile()

    def evaluate_proposal(
        self,
        proposal: Dict,
        account_equity: float,
        buying_power: float,
        daily_loss_pct: float,
        current_positions: List[Dict],
        spy_price: float,
        spy_sma_50: float,
        spy_atr_14: float,
        asset_bars_14d: List[Dict] = None
    ) -> RiskEngineOutput:
        """
        The Master Pipeline. Runs the TradeProposal through all 6 gates sequentially.
        """
        gate_results: List[RiskGateResult] = []
        
        # Extract basic proposal data safely
        action = str(proposal.get("action", "")).upper()
        symbol = str(proposal.get("asset", ""))
        quantity = float(proposal.get("quantity", 0.0))
        price = float(proposal.get("estimated_price", 0.0))

        # ---------------------------------------------------------
        # GATE 1: SEMANTIC
        # ---------------------------------------------------------
        res_semantic = check_semantic_gate(action, quantity, price)
        gate_results.append(res_semantic)
        if res_semantic.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # GATE 2: LOSS / DRAWDOWN (Kill Switch Check)
        # ---------------------------------------------------------
        res_loss = check_loss_drawdown_gate(action, daily_loss_pct, self.hard_limits, self.risk_profile)
        gate_results.append(res_loss)
        if res_loss.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # GATE 3: ACCOUNT STATE
        # ---------------------------------------------------------
        res_account = check_account_state_gate(action, quantity, price, buying_power)
        gate_results.append(res_account)
        if res_account.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # GATE 4: MARKET REGIME
        # ---------------------------------------------------------
        regime_state = determine_market_regime(spy_price, spy_sma_50, spy_atr_14)
        res_regime = check_market_regime_gate(action, regime_state)
        gate_results.append(res_regime)
        if res_regime.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # GATE 5: PROJECTED PORTFOLIO CONCENTRATION
        # ---------------------------------------------------------
        res_portfolio = check_projected_portfolio_gate(
            action, symbol, quantity, price, 
            account_equity, current_positions, 
            self.hard_limits, self.risk_profile
        )
        gate_results.append(res_portfolio)
        if res_portfolio.status == RiskDecision.BLOCK:
            return self._build_final_output(gate_results)

        # ---------------------------------------------------------
        # GATE 6: VOLATILITY SIZING
        # ---------------------------------------------------------
        if asset_bars_14d and action == "BUY":
            asset_atr = calculate_atr(asset_bars_14d, period=14)
            res_volatility = check_volatility_sizing_gate(
                action, quantity, account_equity, asset_atr, self.risk_profile
            )
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
            # Find the first block reason for the summary
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

# Global singleton instance of the Risk Engine to be used by FastAPI
master_risk_engine = RiskEngine()