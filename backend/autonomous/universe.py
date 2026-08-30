# backend/autonomous/universe.py

from enum import IntEnum
from typing import Set, Dict, List
import time

class UniversePriority(IntEnum):
    P0_POSITION = 0
    P1_STRATEGY = 1
    P2_WATCHLIST = 2
    P3_DISCOVERY = 3

class MarketUniverseManager:
    """
    Manages dynamic asset subscriptions for the Watcher.
    Enforces a configurable laptop-friendly cap with strict LRU eviction policies.
    """
    def __init__(self, max_cap: int = 50):
        self.max_cap = max_cap
        
        # P0 and P1 are sets because they are never forcibly evicted by the cap
        self.p0: Set[str] = set()
        self.p1: Set[str] = set()
        
        # P2 and P3 are dicts {symbol: timestamp} to track Least Recently Used (LRU) for eviction
        self.p2: Dict[str, float] = {}
        self.p3: Dict[str, float] = {}

    def add(self, symbol: str, priority: UniversePriority):
        """Adds a symbol at the specified priority level and enforces the subscription cap."""
        symbol = symbol.upper()
        now = time.time()

        if priority == UniversePriority.P0_POSITION:
            self.p0.add(symbol)
        elif priority == UniversePriority.P1_STRATEGY:
            self.p1.add(symbol)
        elif priority == UniversePriority.P2_WATCHLIST:
            self.p2[symbol] = now
        elif priority == UniversePriority.P3_DISCOVERY:
            self.p3[symbol] = now
            
        self._enforce_cap()

    def remove(self, symbol: str, priority: UniversePriority):
        """Explicitly removes a symbol from a specific priority tier."""
        symbol = symbol.upper()
        
        if priority == UniversePriority.P0_POSITION and symbol in self.p0:
            self.p0.remove(symbol)
        elif priority == UniversePriority.P1_STRATEGY and symbol in self.p1:
            self.p1.remove(symbol)
        elif priority == UniversePriority.P2_WATCHLIST and symbol in self.p2:
            del self.p2[symbol]
        elif priority == UniversePriority.P3_DISCOVERY and symbol in self.p3:
            del self.p3[symbol]

    def _enforce_cap(self):
        """
        Evicts P3, then P2 using LRU if total size exceeds max_cap.
        P0 and P1 are mathematically protected and will never be evicted here.
        """
        while self._current_size() > self.max_cap:
            # 1. Try to evict from P3 first (Lowest Priority)
            if self.p3:
                oldest_p3 = min(self.p3.keys(), key=lambda k: self.p3[k])
                del self.p3[oldest_p3]
            # 2. Try to evict from P2 next
            elif self.p2:
                oldest_p2 = min(self.p2.keys(), key=lambda k: self.p2[k])
                del self.p2[oldest_p2]
            # 3. If only P0 and P1 remain, we must break. Safety > Cap.
            else:
                break

    def _current_size(self) -> int:
        """Returns the number of unique symbols across all tiers."""
        return len(self.p0.union(self.p1).union(self.p2.keys()).union(self.p3.keys()))

    def get_universe(self) -> List[str]:
        """Returns the deduplicated list of all currently active symbols to stream."""
        return list(self.p0.union(self.p1).union(self.p2.keys()).union(self.p3.keys()))