# backend/autonomous/brief_builder.py

import logging
from typing import Dict, Any, List, Optional
from backend.autonomous.models import MarketBrief
from backend.autonomous.trigger import TriggerResult

logger = logging.getLogger(__name__)

class MarketBriefBuilder:
    """
    Constructs a compact, strictly bounded Market Brief for the LLM.
    Prevents raw ticks, full option chains, or unnecessary account secrets
    from reaching the AI.
    """

    @staticmethod
    def build_brief(
        trigger: TriggerResult,
        symbol: str,
        current_price: float,
        account_buying_power: float,
        portfolio_positions: List[Dict[str, Any]],
        narrow_options_chain: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[MarketBrief]:
        
        # 1. Freshness & Validity Check
        if current_price is None or current_price <= 0:
            logger.error(f"Failed to build Market Brief for {symbol}: Stale or invalid price.")
            return None

        # 2. Extract Relevant Portfolio Exposure (Exclude unrelated assets to save tokens)
        relevant_exposure = {
            "buying_power": account_buying_power,
            "held_positions": [
                p for p in portfolio_positions 
                if p.get("symbol") == symbol
            ]
        }

        # 3. Narrow Options Data (Safeguard against full chains)
        safe_options = None
        if narrow_options_chain is not None:
            if len(narrow_options_chain) > 5:
                logger.warning(f"Options chain too large for {symbol} brief. Truncating to 5 strikes.")
                safe_options = narrow_options_chain[:5]
            else:
                safe_options = narrow_options_chain

        # 4. Construct and return the strict MarketBrief model
        try:
            return MarketBrief(
                trigger_reason=trigger.context.get("reason", "Unknown trigger"),
                current_facts={
                    "symbol": symbol,
                    "price": current_price,
                    "market_context": trigger.context.get("market_regime", "neutral")
                },
                portfolio_exposure=relevant_exposure,
                strategy_constraints=trigger.context.get("strategy_constraints", {}),
                narrowed_option_facts=safe_options,
                provenance="Alpaca_IEX_Basic_Tier"  # Strictly enforces basic tier awareness
            )
        except Exception as e:
            logger.error(f"Error constructing Market Brief: {e}")
            return None