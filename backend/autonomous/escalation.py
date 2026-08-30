# backend/autonomous/escalation.py

import logging
from typing import Optional, Dict, Any
from backend.autonomous.trigger import EscalationLevel, TriggerResult
from backend.autonomous.models import MarketBrief

logger = logging.getLogger(__name__)

class EscalationManager:
    """
    Strictly routes triggers into HOT, WARM, or COLD paths.
    Guarantees the LLM is never invoked on the HOT path.
    """
    def __init__(self):
        pass

    async def process_trigger(self, trigger: TriggerResult) -> Optional[Dict[str, Any]]:
        """
        Routes the qualified trigger based on its escalation level.
        Returns an NMLI proposal dict or None (NO_ACTION).
        """
        if trigger.level == EscalationLevel.LEVEL_1_DETERMINISTIC:
            # HOT PATH (No Data Fetch, No LLM): Immediate NMLI Proposal
            logger.info(f"Escalation [LEVEL 1]: Deterministic HOT path for {trigger.strategy_id}")
            return await self._handle_level_1(trigger)
            
        elif trigger.level in [EscalationLevel.LEVEL_2_ENRICH, EscalationLevel.LEVEL_3_LLM]:
            # WARM PATH: Fetch targeted authoritative data
            logger.info(f"Escalation [WARM PATH]: Enriching data for {trigger.strategy_id}")
            market_brief = await self._warm_path_enrichment(trigger)
            
            if trigger.level == EscalationLevel.LEVEL_3_LLM and market_brief:
                # COLD PATH: Invoke LLM reasoning safely
                logger.info(f"Escalation [COLD PATH]: Invoking LLM for {trigger.strategy_id}")
                return await self._cold_path_llm(market_brief)
            
            # If it was only Level 2, or brief generation failed, default to NO_ACTION
            return None
        
        return None

    async def _handle_level_1(self, trigger: TriggerResult) -> Optional[Dict[str, Any]]:
        """HOT PATH: Deterministic NMLI generation (E.g., Hard stop-loss)."""
        # Returns a strict NMLI structure (Mocked for routing test)
        return {
            "tool_name": "place_stock_order",
            "arguments": {"symbol": "MOCK", "side": "sell", "qty": "1"},
            "metadata": {"source": "AUTONOMOUS_TRIGGER", "is_deterministic": True}
        }

    async def _warm_path_enrichment(self, trigger: TriggerResult) -> Optional[MarketBrief]:
        """WARM PATH: Fetches targeted data and builds a Market Brief (Implemented in Part 9)."""
        return MarketBrief(
            trigger_reason=trigger.context.get("reason", "Unknown"),
            current_facts={"price": 100},
            portfolio_exposure={"held": 0},
            strategy_constraints=trigger.context.get("strategy_constraints", {})
        )

    async def _cold_path_llm(self, brief: MarketBrief) -> Optional[Dict[str, Any]]:
        """COLD PATH: Calls the LLM with strict resource boundaries (Implemented in Part 10)."""
        return {
            "tool_name": "place_option_order",
            "arguments": {"qty": "1"},
            "metadata": {"source": "AUTONOMOUS_TRIGGER", "is_deterministic": False}
        }