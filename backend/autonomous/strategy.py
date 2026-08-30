# backend/autonomous/strategy.py

from typing import Dict, Any, List
from backend.autonomous.models import AutonomousEvent
from backend.autonomous.universe import UniversePriority
from backend.autonomous.trigger import EscalationLevel

class UniverseRequirement:
    """Defines an asset a strategy needs the Watcher to monitor."""
    def __init__(self, symbol: str, priority: UniversePriority):
        self.symbol = symbol.upper()
        self.priority = priority

class BaseStrategy:
    """
    The absolute boundary for autonomous strategy logic.
    CRITICAL RULE:
    - STRATEGIES CANNOT EXECUTE TRADES.
    - STRATEGIES CANNOT BYPASS RISK ENGINE.
    - STRATEGIES CANNOT CALL CORE-X.
    They only observe events and return explicit Trigger Intents.
    """
    strategy_id: str = "BASE_STRATEGY"
    
    def get_universe_requirements(self) -> List[UniverseRequirement]:
        """Returns the list of assets this strategy needs to monitor."""
        return []
        
    def evaluate(self, event: AutonomousEvent) -> Dict[str, Any]:
        """
        Evaluates a normalized market event deterministically.
        Must return a dict containing at minimum:
        - is_triggered: bool
        If True, must also include:
        - level: EscalationLevel (0 to 3)
        - reason: str (Passed to LLM or Validator)
        - price_bucket: str (For Material Change Fingerprint)
        - position_state: str (For Material Change Fingerprint)
        - strategy_constraints: Dict (Limits LLM hallucination, e.g. allowed_actions)
        """
        return {"is_triggered": False}