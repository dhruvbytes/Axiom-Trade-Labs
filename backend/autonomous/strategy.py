# backend/autonomous/strategy.py

from typing import Dict, Any, List
from backend.autonomous.models import AutonomousEvent
from backend.autonomous.universe import UniverseTier
from backend.autonomous.trigger import EscalationLevel

class UniverseRequirement:
    def __init__(self, symbol: str, priority: UniverseTier):
        self.symbol = symbol.upper()
        self.priority = priority

class BaseStrategy:
    strategy_id: str = "BASE_STRATEGY"
    
    def get_universe_requirements(self) -> List[UniverseRequirement]:
        return []
        
    def evaluate(self, event: AutonomousEvent) -> Dict[str, Any]:
        return {"is_triggered": False}

class DecisionCycleStrategy(BaseStrategy):
    strategy_id = "BOUNDED_DECISION_CYCLE"

    def evaluate(self, event: AutonomousEvent) -> Dict[str, Any]:
        material_change = float(event.raw_data.get("material_change_pct", 0.0))
        if event.price is None or event.price <= 0 or material_change == 0:
            return {"is_triggered": False}
        return {
            "is_triggered": True,
            "level": EscalationLevel.LEVEL_2_ENRICH,
            "reason": "Material price movement qualified for bounded decision review.",
            "price_bucket": "COOLDOWN_LOCKED_5_MINS", # 🛑 YAHAN SPAM KILL HOGA
            "position_state": "UNKNOWN",
            "symbol": event.symbol,
            "material_change_pct": material_change,
            "strategy_constraints": {
                "controller_only": True,
                "direct_execution_forbidden": True,
                "allowed_asset_classes": ["equity", "option"],
            },
        }