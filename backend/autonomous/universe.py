# backend/autonomous/universe.py

from enum import IntEnum
from typing import Set, Dict, List
import time
import logging
from backend.autonomous.ui_events import ui_broadcaster, UIActivityEvent, UIEventCategory, UIEventStatus, SafeEventMetadata

logger = logging.getLogger(__name__)

class UniverseTier(IntEnum):
    """
    Semantic tiers for market monitoring priority. 
    Distinct from Proposal Priority to prevent naming collisions.
    Lower number = Higher protection.
    """
    PORTFOLIO = 0
    USER_INTENT = 1
    MARKET_CONTEXT = 2
    DISCOVERY = 3

class MarketUniverseManager:
    """
    Manages dynamic asset subscriptions for the Watcher.
    Enforces a soft cap. PORTFOLIO always bypasses the cap.
    """
    def __init__(self, max_cap: int = 40):
        self.max_cap = max_cap
        
        # Portfolio is safety-critical. Never evicted. Stored as a set.
        self.portfolio: Set[str] = set()
        
        # Others use dict {symbol: timestamp} for LRU (Least Recently Used) eviction
        self.user_intent: Dict[str, float] = {}
        self.market_context: Dict[str, float] = {}
        self.discovery: Dict[str, float] = {}
        
        # Hooks for dynamic streamer wiring
        self.on_subscribe_hook = None
        self.on_unsubscribe_hook = None

    def _trigger_hooks(self, old_universe: set, new_universe: set):
        """Calculates exact delta and triggers streamer hooks."""
        added = new_universe - old_universe
        removed = old_universe - new_universe
        
        if added and self.on_subscribe_hook:
            for sym in added:
                self.on_subscribe_hook(sym)
                
        if removed and self.on_unsubscribe_hook:
            for sym in removed:
                self.on_unsubscribe_hook(sym)

    def add(self, symbol: str, tier: UniverseTier):
        """Adds a symbol at the specified tier and enforces the capacity cap."""
        symbol = symbol.upper()
        now = time.time()
        old_state = set(self.get_universe())

        if tier == UniverseTier.PORTFOLIO:
            self.portfolio.add(symbol)
            logger.info(f"[UNIVERSE] Added {symbol} | tier=PORTFOLIO")
            ui_broadcaster.publish(UIActivityEvent(
                category=UIEventCategory.UNIVERSE, status=UIEventStatus.INFO,
                message=f"Added {symbol} to monitoring", safe_metadata=SafeEventMetadata(symbol=symbol, tier="PORTFOLIO")
            ))
        elif tier == UniverseTier.USER_INTENT:
            self.user_intent[symbol] = now
            logger.info(f"[UNIVERSE] Added {symbol} | tier=USER_INTENT")
            ui_broadcaster.publish(UIActivityEvent(
                category=UIEventCategory.UNIVERSE, status=UIEventStatus.SUCCESS,
                message=f"Added {symbol} via User Intent", safe_metadata=SafeEventMetadata(symbol=symbol, tier="USER")
            ))
        elif tier == UniverseTier.MARKET_CONTEXT:
            self.market_context[symbol] = now
            logger.info(f"[UNIVERSE] Added {symbol} | tier=MARKET_CONTEXT")
            ui_broadcaster.publish(UIActivityEvent(
                category=UIEventCategory.UNIVERSE, status=UIEventStatus.INFO,
                message=f"Loaded broad context: {symbol}", safe_metadata=SafeEventMetadata(symbol=symbol, tier="CONTEXT")
            ))
        elif tier == UniverseTier.DISCOVERY:
            self.discovery[symbol] = now
            logger.info(f"[UNIVERSE] Added {symbol} | tier=DISCOVERY")
            ui_broadcaster.publish(UIActivityEvent(
                category=UIEventCategory.UNIVERSE, status=UIEventStatus.SUCCESS,
                message=f"Autonomously discovered: {symbol}", safe_metadata=SafeEventMetadata(symbol=symbol, tier="DISCOVERY")
            ))
            
        self._enforce_cap()
        self._trigger_hooks(old_state, set(self.get_universe()))

    def remove(self, symbol: str, tier: UniverseTier):
        """Explicitly removes a symbol from a specific tier."""
        symbol = symbol.upper()
        old_state = set(self.get_universe())
        
        if tier == UniverseTier.PORTFOLIO and symbol in self.portfolio:
            self.portfolio.remove(symbol)
        elif tier == UniverseTier.USER_INTENT and symbol in self.user_intent:
            del self.user_intent[symbol]
        elif tier == UniverseTier.MARKET_CONTEXT and symbol in self.market_context:
            del self.market_context[symbol]
        elif tier == UniverseTier.DISCOVERY and symbol in self.discovery:
            del self.discovery[symbol]
            
        self._trigger_hooks(old_state, set(self.get_universe()))

    def _enforce_cap(self):
        """
        Evicts DISCOVERY, then MARKET_CONTEXT if total size exceeds max_cap.
        PORTFOLIO will ALWAYS be preserved, even if it forces capacity overflow.
        """
        while self._current_size() > self.max_cap:
            # 1. Try to evict from DISCOVERY first (Lowest Tier)
            if self.discovery:
                oldest = min(self.discovery.keys(), key=lambda k: self.discovery[k])
                del self.discovery[oldest]
                logger.info(f"[UNIVERSE] Evicted {oldest} | tier=DISCOVERY (Capacity pressure)")
            
            # 2. Try to evict from MARKET_CONTEXT next
            elif self.market_context:
                oldest = min(self.market_context.keys(), key=lambda k: self.market_context[k])
                del self.market_context[oldest]
                logger.info(f"[UNIVERSE] Evicted {oldest} | tier=MARKET_CONTEXT (Capacity pressure)")
            
            # 3. Stop eviction. 
            # We do NOT silently evict USER_INTENT here (handled via NLU constraints).
            # We NEVER evict PORTFOLIO. Let it overflow safely.
            else:
                break

    def _current_size(self) -> int:
        return len(self.portfolio.union(self.user_intent.keys())
                   .union(self.market_context.keys())
                   .union(self.discovery.keys()))

    def get_universe(self) -> List[str]:
        """Returns the deduplicated list of all currently active symbols to stream."""
        return list(self.portfolio.union(self.user_intent.keys())
                    .union(self.market_context.keys())
                    .union(self.discovery.keys()))

    def get_universe_state(self) -> Dict[str, List[str]]:
        """Utility for debugging/testing state."""
        return {
            "PORTFOLIO": list(self.portfolio),
            "USER_INTENT": list(self.user_intent.keys()),
            "MARKET_CONTEXT": list(self.market_context.keys()),
            "DISCOVERY": list(self.discovery.keys())
        }
        
# Global singleton instance
universe_manager = MarketUniverseManager(max_cap=40)