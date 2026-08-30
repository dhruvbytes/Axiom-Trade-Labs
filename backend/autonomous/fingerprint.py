# backend/autonomous/fingerprint.py

import json
import hashlib
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Set

class FingerprintManager:
    """
    In-memory state manager to prevent LLM spam and duplicate autonomous proposals.
    Strictly handles in-flight suppression and material change cooldowns.
    """
    def __init__(self):
        # Maps fingerprint hash -> UTC datetime expiry
        self._cooldowns: Dict[str, datetime] = {}
        # Set of fingerprint hashes currently being processed (in-flight)
        self._in_flight: Set[str] = set()
        # Async lock to prevent race conditions when checking/setting state
        self._lock = asyncio.Lock()

    def generate_fingerprint(
        self, 
        strategy_id: str, 
        symbol: str, 
        trigger_context: str, 
        price_bucket: str, 
        position_state: str
    ) -> str:
        """
        Creates a deterministic hash based ONLY on material facts.
        Noisy ticks or timestamps are intentionally excluded.
        """
        data = {
            "strategy": strategy_id,
            "symbol": symbol,
            "context": trigger_context,
            "price_bucket": price_bucket,  # e.g., "150.5" (rounded to coarse bucket)
            "position": position_state     # e.g., "NONE" or "LONG"
        }
        # Canonical JSON string sorting keys ensures deterministic hashing
        canonical_string = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_string.encode('utf-8')).hexdigest()

    async def acquire_processing_lock(self, fingerprint: str) -> bool:
        """
        Attempts to acquire the right to process this fingerprint.
        Returns True if acquired, False if currently in-flight or in cooldown.
        """
        async with self._lock:
            now_utc = datetime.now(timezone.utc)

            # 1. Check if in cooldown
            if fingerprint in self._cooldowns:
                if now_utc < self._cooldowns[fingerprint]:
                    return False  # Suppressed by cooldown
                else:
                    # Cooldown expired, clean it up
                    del self._cooldowns[fingerprint]

            # 2. Check if currently in-flight
            if fingerprint in self._in_flight:
                return False  # Suppressed by in-flight lock

            # 3. Acquire
            self._in_flight.add(fingerprint)
            return True

    async def release_and_cooldown(self, fingerprint: str, cooldown_seconds: int = 300):
        """
        Releases the in-flight lock and applies a cooldown to prevent immediate re-triggering.
        If cooldown_seconds is 0, it can be re-triggered immediately (e.g., on failure).
        """
        async with self._lock:
            if fingerprint in self._in_flight:
                self._in_flight.remove(fingerprint)
            
            if cooldown_seconds > 0:
                expiry = datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)
                self._cooldowns[fingerprint] = expiry