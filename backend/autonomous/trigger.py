# backend/autonomous/trigger.py

import logging
from typing import Optional, Dict, Any, List
from enum import IntEnum
from backend.autonomous.models import AutonomousEvent
from backend.autonomous.fingerprint import FingerprintManager

logger = logging.getLogger(__name__)

class EscalationLevel(IntEnum):
    LEVEL_0_IGNORE = 0
    LEVEL_1_DETERMINISTIC = 1  # E.g., Stop Loss hit -> Strict NMLI output
    LEVEL_2_ENRICH = 2         # Needs more data before LLM
    LEVEL_3_LLM = 3            # Send Market Brief to LLM

class TriggerResult:
    def __init__(
        self, 
        strategy_id: str, 
        level: EscalationLevel, 
        fingerprint: str, 
        context: Dict[str, Any]
    ):
        self.strategy_id = strategy_id
        self.level = level
        self.fingerprint = fingerprint
        self.context = context

class TriggerEngine:
    """
    Evaluates incoming market events against active strategies.
    Does NOT execute. Determines if an event should escalate or be ignored.
    Applies Fingerprint/Cooldown deduplication strictly.
    """
    def __init__(self, fingerprint_manager: FingerprintManager):
        self.fingerprint_manager = fingerprint_manager
        self.strategies: List[Any] = [] # List of strategy plugins

    def add_strategy(self, strategy: Any):
        self.strategies.append(strategy)

    async def evaluate_event(self, event: AutonomousEvent) -> Optional[TriggerResult]:
        """
        Runs the event through all strategies. 
        Returns the highest priority valid trigger, or None (NO_ACTION).
        """
        if not self.strategies:
            return None

        for strategy in self.strategies:
            try:
                # 1. Strategy checks if the event is relevant and meets conditions
                trigger_data = strategy.evaluate(event)
                
                if not trigger_data or not trigger_data.get("is_triggered"):
                    continue

                # 2. Material Change Fingerprint Generation
                fp = self.fingerprint_manager.generate_fingerprint(
                    strategy_id=strategy.strategy_id,
                    symbol=event.symbol,
                    trigger_context=trigger_data.get("reason", "unknown"),
                    price_bucket=trigger_data.get("price_bucket", "0.0"),
                    position_state=trigger_data.get("position_state", "NONE")
                )

                # 3. Cooldown & In-Flight Check
                can_process = await self.fingerprint_manager.acquire_processing_lock(fp)
                if not can_process:
                    logger.debug(f"Trigger suppressed by fingerprint cooldown: {fp}")
                    continue
                    
                # 4. Escalation Decision
                level = trigger_data.get("level", EscalationLevel.LEVEL_0_IGNORE)
                if level == EscalationLevel.LEVEL_0_IGNORE:
                    # Not an actionable trigger, release lock immediately
                    await self.fingerprint_manager.release_and_cooldown(fp, cooldown_seconds=0)
                    continue

                # 5. Return Qualified Trigger Candidate
                return TriggerResult(
                    strategy_id=strategy.strategy_id,
                    level=level,
                    fingerprint=fp,
                    context=trigger_data
                )
                
            except Exception as e:
                # 🛡️ FATAL EXCEPTION SHIELD: One bad strategy shouldn't crash the engine
                logger.error(f"Strategy {getattr(strategy, 'strategy_id', 'UNKNOWN')} failed safely: {e}")
                continue
                
        return None  # NO_ACTION