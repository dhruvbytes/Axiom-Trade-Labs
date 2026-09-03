# backend/execution/journal.py

import sqlite3
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from .models import ExecutionState

# We place the DB in the same directory as this file for the hackathon
DB_PATH = os.path.join(os.path.dirname(__file__), "execution_journal.db")

class ExecutionJournal:
    """
    Industry-Grade SQLite WAL-backed persistent journal.
    Optimized for high-frequency autonomous trading loops.
    Zero schema-checks in the hot path.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        # We DO NOT auto-initialize here to prevent thread contention.
        # Bootstrapping must be called explicitly at app startup.

    def _get_conn(self) -> sqlite3.Connection:
        """Returns a tuned connection with WAL enabled."""
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        # WAL mode is crucial for concurrent reads/writes in autonomous systems
        conn.execute("PRAGMA journal_mode=WAL;")
        # Synchronous NORMAL is safe in WAL mode and much faster
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._get_conn()
        try:
            yield conn
        finally:
            conn.close()

    def bootstrap(self):
        """
        MUST be called once at application startup.
        Safely creates the schema without locking hot-paths.
        """
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_journal (
                    ik TEXT PRIMARY KEY,
                    intent_nonce TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    is_mutating BOOLEAN NOT NULL,
                    risk_auth_hash TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    mcp_result_payload TEXT,
                    error_context TEXT
                )
            """)

    def reset_for_testing(self):
        """
        Enterprise pattern for test isolation. 
        Drops the table cleanly instead of deleting the OS file.
        """
        with self._connection() as conn:
            conn.execute("DROP TABLE IF EXISTS execution_journal")
        self.bootstrap()

    def startup_sweep_crash_recovery(self) -> int:
        """
        CRASH RECOVERY: Sweeps orphan DISPATCHED states to UNCERTAIN.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.execute("""
                UPDATE execution_journal
                SET state = ?, updated_at_utc = ?, error_context = ?
                WHERE state = ?
            """, (
                ExecutionState.EXECUTION_UNCERTAIN.value,
                now,
                "PROCESS_CRASH_RECOVERY_SWEEP",
                ExecutionState.DISPATCHED.value
            ))
            return cursor.rowcount

    # ==========================================
    # HOT PATHS (Lightning Fast, Zero Schema Checks)
    # ==========================================

    def insert_or_get_status(
        self, ik: str, intent_nonce: str, tool_name: str, is_mutating: bool, risk_auth_hash: str
    ) -> Tuple[bool, ExecutionState, Optional[Dict[Any, Any]], Optional[str]]:
        """Atomic Deduplication Check."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connection() as conn:
                conn.execute("BEGIN EXCLUSIVE TRANSACTION")
                try:
                    conn.execute("""
                        INSERT INTO execution_journal 
                        (ik, intent_nonce, tool_name, is_mutating, risk_auth_hash, state, created_at_utc, updated_at_utc)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ik, intent_nonce, tool_name, is_mutating, risk_auth_hash,
                        ExecutionState.RECEIVED.value, now, now
                    ))
                    conn.execute("COMMIT")
                    return (True, ExecutionState.RECEIVED, None, None)
                except sqlite3.IntegrityError:
                    conn.execute("ROLLBACK")
                    return self._fetch_existing_state(conn, ik)
        except sqlite3.OperationalError as e:
            raise RuntimeError(f"Database missing or locked. Did you call bootstrap()? Error: {e}")

    def _fetch_existing_state(self, conn: sqlite3.Connection, ik: str) -> Tuple[bool, ExecutionState, Optional[Dict[Any, Any]], Optional[str]]:
        cursor = conn.execute("SELECT state, mcp_result_payload, error_context FROM execution_journal WHERE ik = ?", (ik,))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("Idempotency key blocked insert but record missing (Race Condition).")
        
        state_val, payload_str, error_context = row
        cached_result = json.loads(payload_str) if payload_str else None
        return (False, ExecutionState(state_val), cached_result, error_context)

    def transition_state(
        self, ik: str, expected_current_state: ExecutionState, new_state: ExecutionState,
        result_payload: Optional[Dict] = None, error_context: Optional[str] = None
    ) -> bool:
        """Atomic State Transition."""
        now = datetime.now(timezone.utc).isoformat()
        payload_str = json.dumps(result_payload) if result_payload is not None else None
        
        with self._connection() as conn:
            cursor = conn.execute("""
                UPDATE execution_journal
                SET state = ?, updated_at_utc = ?, mcp_result_payload = ?, error_context = ?
                WHERE ik = ? AND state = ?
            """, (
                new_state.value, now, payload_str, error_context,
                ik, expected_current_state.value
            ))
            return cursor.rowcount > 0

    def unresolved_execution_count(self) -> int:
        """Return durable post-dispatch uncertainty requiring reconciliation."""
        self.bootstrap()
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM execution_journal
                WHERE state IN (?, ?)
                """,
                (ExecutionState.DISPATCHED.value, ExecutionState.EXECUTION_UNCERTAIN.value),
            ).fetchone()
            return int(row[0]) if row else 0

# Singleton instance
execution_journal = ExecutionJournal()
