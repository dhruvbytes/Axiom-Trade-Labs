# backend/autonomous/ui_events.py

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)

class UIEventCategory(str, Enum):
    SYSTEM = "SYSTEM"
    MARKET = "MARKET"
    UNIVERSE = "UNIVERSE"
    RISK = "RISK"
    EXECUTION = "EXECUTION"
    DECISION = "DECISION"
    LEARNING = "LEARNING"
    RECONCILIATION = "RECONCILIATION"

class UIEventStatus(str, Enum):
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"

class SafeEventMetadata(BaseModel):
    """
    STRICTLY BOUNDED: Forbids arbitrary dictionaries.
    Only primitive allowed fields to completely prevent secret/traceback leakage.
    """
    model_config = ConfigDict(extra="forbid")
    
    symbol: Optional[str] = None
    price: Optional[float] = None
    reason: Optional[str] = None
    tier: Optional[str] = None
    decision_id: Optional[str] = None
    regime: Optional[str] = None
    hypothesis: Optional[str] = None
    confidence: Optional[float] = None
    outcome: Optional[str] = None
    contract_symbol: Optional[str] = None
    asset_class: Optional[str] = None

class UIActivityEvent(BaseModel):
    """Strict schema for events allowed to reach the frontend."""
    model_config = ConfigDict(extra="forbid")
    
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    category: UIEventCategory
    status: UIEventStatus
    message: str = Field(..., max_length=200) # Prevents massive payload flooding
    safe_metadata: SafeEventMetadata = Field(default_factory=SafeEventMetadata)

class LiveActivityBroadcaster:
    """
    Thread-safe, bounded, fire-and-forget event dispatcher.
    Zero LLM dependency.
    """
    def __init__(self, max_queue_size: int = 50):
        self._clients: set[asyncio.Queue] = set()
        self._max_queue_size = max_queue_size
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_error_log_time = 0.0

    def attach_main_loop(self):
        """Called during FastAPI startup to capture the main event loop for thread-safe cross-publishing."""
        self._main_loop = asyncio.get_running_loop()

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=self._max_queue_size)
        self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._clients.discard(q)

    def _safe_log_error(self, msg: str):
        """Rate-limited internal logging. Max 1 log per 5 seconds to prevent spam."""
        now = time.time()
        if now - self._last_error_log_time > 5.0:
            logger.error(f"[UI_BROADCASTER] {msg}")
            self._last_error_log_time = now

    def publish(self, event: UIActivityEvent):
        """Called by trading pipeline. Thread-safe, non-blocking, fail-safe."""
        
        # 🚀 ADDED: Yeh line saare UI/Learning/Execution events ko audit log file mein bhi daal degi!
        logger.info(f"[{event.category}] {event.message} | {event.safe_metadata}")

        if not self._clients:
            return
            
        try:
            json_payload = event.model_dump_json()
            if self._main_loop and not self._main_loop.is_closed():
                self._main_loop.call_soon_threadsafe(self._dispatch_to_queues, json_payload)
        except Exception as e:
            self._safe_log_error(f"Event serialization/validation failed: {e}")

    def _dispatch_to_queues(self, json_payload: str):
        """Executes strictly on the main event loop to push data into Queues."""
        for q in list(self._clients):
            try:
                q.put_nowait(json_payload)
            except asyncio.QueueFull:
                # DROP POLICY: Drop oldest or drop new? 
                # asyncio.QueueFull means we drop the new event. 
                # UI is non-critical. Trading pipeline must not be blocked.
                pass
            except Exception as e:
                self._safe_log_error(f"Queue dispatch failed: {e}")

ui_broadcaster = LiveActivityBroadcaster()
