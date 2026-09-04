import os
import sqlite3
import json
import asyncio
from datetime import datetime, timezone
from backend.autonomous.decision_models import RuntimePolicy
from backend.autonomous.uncertainty import uncertainty_gate
from backend.autonomous.ui_events import ui_broadcaster, UIActivityEvent, UIEventCategory, UIEventStatus
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_DB_PATH = os.path.join(BASE_DIR, "decision_journal.db")

class RuntimePolicyManager:
    def __init__(self):
        self._current_policy = RuntimePolicy()
        self._lock = asyncio.Lock()
        self._bootstrap_db()
        self._load_latest_policy()

    def _bootstrap_db(self):
        with sqlite3.connect(SQLITE_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runtime_policy_audit (
                    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT,
                    source TEXT,
                    policy_json TEXT
                )
            """)

    def _load_latest_policy(self):
        with sqlite3.connect(SQLITE_DB_PATH) as conn:
            row = conn.execute("SELECT policy_json FROM runtime_policy_audit ORDER BY version_id DESC LIMIT 1").fetchone()
            if row:
                try:
                    self._current_policy = RuntimePolicy(**json.loads(row[0]))
                except Exception:
                    pass # Fails safely to default if corrupted

    def get_current(self) -> RuntimePolicy:
        """Returns the immutable RCU snapshot for the current evaluation cycle."""
        return self._current_policy

    async def apply_policy(self, new_policy: RuntimePolicy, source: str = "USER") -> RuntimePolicy:
        async with self._lock:
            # 1. Validation occurred via Pydantic on endpoint entry
            # 2. Persist complete snapshot
            with sqlite3.connect(SQLITE_DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO runtime_policy_audit (timestamp_utc, source, policy_json) VALUES (?, ?, ?)",
                    (datetime.now(timezone.utc).isoformat(), source, new_policy.model_dump_json())
                )
            
            # 3. Atomic in-memory swap
            self._current_policy = new_policy
            
            # 4. Trigger EXISTING UncertaintyGate (Exactly 60 seconds)
            uncertainty_gate.set_uncertainty("default_account", True)
            
            # 5. Emit Audit/UI Event
            ui_broadcaster.publish(UIActivityEvent(
                category=UIEventCategory.SYSTEM,
                status=UIEventStatus.WARNING,
                message=f"Runtime policy transition initiated by {source}. System frozen for 60s.",
            ))
            
            return self._current_policy

runtime_policy_manager = RuntimePolicyManager()