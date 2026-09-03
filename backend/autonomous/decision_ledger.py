"""Durable, bounded decision/outcome journal separate from CORE-X's journal."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from backend.autonomous.decision_models import DecisionReceipt, OutcomeRecord, RegimeLabel


DB_PATH = os.path.join(os.path.dirname(__file__), "decision_journal.db")


class DecisionLedger:
    """Small SQLite/WAL ledger for auditability and slow preference updates.

    The ledger deliberately has no access to execution authority. It records what
    the controller decided and what subsequently happened in paper-marked prices.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def bootstrap(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS autonomous_decisions (
                    decision_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    trigger_fingerprint TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    status TEXT NOT NULL,
                    selected_hypothesis_id TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    outcome_due_at_utc TEXT,
                    outcome_completed INTEGER NOT NULL DEFAULT 0,
                    terminal_status TEXT,
                    terminal_reason TEXT,
                    receipt_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS autonomous_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL,
                    hypothesis_id TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    expected_direction INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    gross_return_pct REAL NOT NULL,
                    success INTEGER NOT NULL,
                    completed_at_utc TEXT NOT NULL,
                    source TEXT NOT NULL,
                    UNIQUE(decision_id, hypothesis_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS autonomous_preferences (
                    hypothesis_id TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    alpha REAL NOT NULL,
                    beta REAL NOT NULL,
                    observations INTEGER NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(hypothesis_id, regime)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS autonomous_reconciliation (
                    reconciliation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    observed_at_utc TEXT NOT NULL
                )
                """
            )

    def record_decision(self, receipt: DecisionReceipt) -> None:
        self.bootstrap()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO autonomous_decisions (
                    decision_id, account_id, trigger_fingerprint, symbol, regime, status,
                    selected_hypothesis_id, confidence, entry_price, created_at_utc,
                    outcome_due_at_utc, receipt_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.decision_id,
                    receipt.account_id,
                    receipt.trigger_fingerprint,
                    receipt.snapshot.symbol,
                    receipt.regime.label.value,
                    receipt.status.value,
                    receipt.selected_hypothesis_id,
                    receipt.confidence,
                    receipt.snapshot.event_price,
                    receipt.created_at_utc,
                    receipt.outcome_due_at_utc,
                    receipt.model_dump_json(),
                ),
            )

    def record_terminal_result(self, decision_id: Optional[str], status: str, reason: str = "") -> None:
        if not decision_id:
            return
        self.bootstrap()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE autonomous_decisions
                SET terminal_status = ?, terminal_reason = ?
                WHERE decision_id = ?
                """,
                (status[:80], reason[:500], decision_id),
            )

    def get_preference(self, hypothesis_id: str, regime: RegimeLabel) -> Dict[str, float]:
        self.bootstrap()
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT alpha, beta, observations
                FROM autonomous_preferences
                WHERE hypothesis_id = ? AND regime = ?
                """,
                (hypothesis_id, regime.value),
            ).fetchone()
        if not row:
            # Conservative symmetric prior: no hypothesis starts favored.
            return {"alpha": 2.0, "beta": 2.0, "observations": 0}
        return {"alpha": float(row["alpha"]), "beta": float(row["beta"]), "observations": int(row["observations"])}

    def record_outcomes(self, outcomes: Iterable[OutcomeRecord]) -> None:
        outcomes = list(outcomes)
        if not outcomes:
            return
        self.bootstrap()
        now = datetime.now(timezone.utc).isoformat()
        decision_ids = set()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for outcome in outcomes:
                    decision_ids.add(outcome.decision_id)
                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO autonomous_outcomes (
                            outcome_id, decision_id, hypothesis_id, regime, symbol,
                            expected_direction, entry_price, exit_price, gross_return_pct,
                            success, completed_at_utc, source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            outcome.outcome_id,
                            outcome.decision_id,
                            outcome.hypothesis_id,
                            outcome.regime.value,
                            outcome.symbol,
                            outcome.expected_direction,
                            outcome.entry_price,
                            outcome.exit_price,
                            outcome.gross_return_pct,
                            int(outcome.success),
                            outcome.completed_at_utc,
                            outcome.source,
                        ),
                    )
                    if cursor.rowcount:
                        self._update_preference(conn, outcome, now)
                for decision_id in decision_ids:
                    conn.execute(
                        "UPDATE autonomous_decisions SET outcome_completed = 1 WHERE decision_id = ?",
                        (decision_id,),
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    @staticmethod
    def _update_preference(conn: sqlite3.Connection, outcome: OutcomeRecord, now: str) -> None:
        row = conn.execute(
            """
            SELECT alpha, beta, observations FROM autonomous_preferences
            WHERE hypothesis_id = ? AND regime = ?
            """,
            (outcome.hypothesis_id, outcome.regime.value),
        ).fetchone()
        alpha = float(row["alpha"]) if row else 2.0
        beta = float(row["beta"]) if row else 2.0
        observations = int(row["observations"]) if row else 0

        # Gentle exponential forgetting prevents stale paper results dominating
        # forever, while the floor preserves a conservative neutral prior.
        alpha = max(1.0, alpha * 0.995) + (1.0 if outcome.success else 0.0)
        beta = max(1.0, beta * 0.995) + (0.0 if outcome.success else 1.0)
        conn.execute(
            """
            INSERT INTO autonomous_preferences
            (hypothesis_id, regime, alpha, beta, observations, updated_at_utc)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(hypothesis_id, regime) DO UPDATE SET
                alpha = excluded.alpha,
                beta = excluded.beta,
                observations = excluded.observations,
                updated_at_utc = excluded.updated_at_utc
            """,
            (outcome.hypothesis_id, outcome.regime.value, alpha, beta, observations + 1, now),
        )

    def pending_decisions(self, now_utc: Optional[str] = None, limit: int = 100) -> List[DecisionReceipt]:
        self.bootstrap()
        now_utc = now_utc or datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT receipt_json FROM autonomous_decisions
                WHERE outcome_completed = 0
                  AND outcome_due_at_utc IS NOT NULL
                  AND outcome_due_at_utc <= ?
                ORDER BY outcome_due_at_utc ASC
                LIMIT ?
                """,
                (now_utc, limit),
            ).fetchall()
        return [DecisionReceipt.model_validate_json(row["receipt_json"]) for row in rows]

    def recent_successes(self, hypothesis_id: str, regime: RegimeLabel, limit: int = 20) -> List[bool]:
        self.bootstrap()
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT success FROM autonomous_outcomes
                WHERE hypothesis_id = ? AND regime = ?
                ORDER BY completed_at_utc DESC
                LIMIT ?
                """,
                (hypothesis_id, regime.value, limit),
            ).fetchall()
        return [bool(row["success"]) for row in reversed(rows)]

    def record_reconciliation(self, account_id: str, status: str, reason: str) -> None:
        self.bootstrap()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO autonomous_reconciliation (account_id, status, reason, observed_at_utc)
                VALUES (?, ?, ?, ?)
                """,
                (account_id, status[:80], reason[:500], datetime.now(timezone.utc).isoformat()),
            )
    def get_recent_decisions(self, limit: int = 30) -> List[Dict]:
        self.bootstrap()
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT decision_id, symbol, status, selected_hypothesis_id, confidence, 
                       terminal_status, terminal_reason, created_at_utc, receipt_json
                FROM autonomous_decisions
                ORDER BY created_at_utc DESC
                LIMIT ?
                """, (limit,)
            ).fetchall()
            
        results = []
        for r in rows:
            d = dict(r)
            try:
                receipt = json.loads(d["receipt_json"])
                d["contract_symbol"] = receipt.get("selected_contract_symbol")
                # Extract the actual mathematical action (BUY_CALL, BUY_STOCK, etc.)
                action = "UNKNOWN"
                for ev in receipt.get("evaluations", []):
                    if ev.get("hypothesis_id") == d["selected_hypothesis_id"]:
                        action = ev.get("action", "UNKNOWN")
                        break
                d["action"] = action
            except Exception:
                d["contract_symbol"] = None
                d["action"] = "UNKNOWN"
                
            # Strip heavy raw JSON before sending to UI to preserve performance
            d.pop("receipt_json", None)
            results.append(d)
        return results

    def get_all_preferences(self) -> List[Dict]:
        self.bootstrap()
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT hypothesis_id, regime, alpha, beta, observations, updated_at_utc FROM autonomous_preferences"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_outcomes(self, limit: int = 15) -> List[Dict]:
        self.bootstrap()
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT outcome_id, decision_id, hypothesis_id, regime, symbol, expected_direction,
                       entry_price, exit_price, gross_return_pct, success, completed_at_utc, source
                FROM autonomous_outcomes
                ORDER BY completed_at_utc DESC
                LIMIT ?
                """, (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

decision_ledger = DecisionLedger()
