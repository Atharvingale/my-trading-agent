"""Human review queue for gate results (Module 15 / Module 4 boundary).

Why this file exists: a PASS is necessary but not sufficient for production.
This queue holds gate outcomes until a human explicitly approves or rejects
them. It never auto-promotes, so automation cannot wire a strategy by itself.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4


class ReviewNotFoundError(KeyError):
    """Raised when a record was never submitted for review."""


class ReviewQueue:
    """SQLite-backed, append-only human sign-off store."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS review_items (
                record_id TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                verdict TEXT NOT NULL,
                source TEXT NOT NULL,
                candidate_id TEXT,
                parent_candidate_id TEXT,
                hypothesis_id TEXT,
                signal_class TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS review_decisions (
                decision_id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL UNIQUE,
                decision TEXT NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
                approver TEXT NOT NULL,
                rationale TEXT NOT NULL,
                decided_at TEXT NOT NULL,
                FOREIGN KEY (record_id) REFERENCES review_items(record_id)
            );
            CREATE TRIGGER IF NOT EXISTS review_items_no_update
            BEFORE UPDATE ON review_items
            BEGIN
                SELECT RAISE(ABORT, 'review_items are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS review_items_no_delete
            BEFORE DELETE ON review_items
            BEGIN
                SELECT RAISE(ABORT, 'review_items are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS review_decisions_no_update
            BEFORE UPDATE ON review_decisions
            BEGIN
                SELECT RAISE(ABORT, 'review_decisions are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS review_decisions_no_delete
            BEFORE DELETE ON review_decisions
            BEGIN
                SELECT RAISE(ABORT, 'review_decisions are append-only');
            END;
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> ReviewQueue:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def submit_for_review(
        self,
        record_id: str,
        strategy_id: str,
        verdict: str,
        *,
        source: str = "HUMAN",
        candidate_id: str | None = None,
        parent_candidate_id: str | None = None,
        hypothesis_id: str | None = None,
        signal_class: str | None = None,
    ) -> str:
        """Record one gate outcome as awaiting human review. Never approves."""
        token = str(record_id).strip()
        if not token:
            raise ValueError("record_id must be non-empty")
        name = str(strategy_id).strip()
        if not name:
            raise ValueError("strategy_id must be non-empty")
        decision = str(verdict).strip().upper()
        if decision not in ("PASS", "FAIL", "NULL_RESULT", "PENDING"):
            raise ValueError("verdict must be PASS, FAIL, NULL_RESULT, or PENDING")
        origin = str(source).strip().upper() or "HUMAN"
        if origin not in ("HUMAN", "AI_RESEARCH", "TRADE_LEARNING"):
            raise ValueError("source must be HUMAN, AI_RESEARCH, or TRADE_LEARNING")
        found = self.connection.execute(
            "SELECT 1 FROM review_items WHERE record_id = ?", (token,)
        ).fetchone()
        if found is not None:
            return token
        created_at = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """INSERT INTO review_items
            (record_id, strategy_id, verdict, source,
             candidate_id, parent_candidate_id, hypothesis_id, signal_class, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                token,
                name,
                decision,
                origin,
                _clean_or_none(candidate_id),
                _clean_or_none(parent_candidate_id),
                _clean_or_none(hypothesis_id),
                _clean_or_none(signal_class),
                created_at,
            ),
        )
        self.connection.commit()
        return token

    def approve(self, record_id: str, approver: str, rationale: str) -> str:
        """Explicit human approval. Approver and rationale are required."""
        return self._decide(record_id, "APPROVED", approver, rationale)

    def reject(self, record_id: str, approver: str, rationale: str) -> str:
        """Explicit human rejection. Recorded permanently like an approval."""
        return self._decide(record_id, "REJECTED", approver, rationale)

    def _decide(self, record_id: str, decision: str, approver: str, rationale: str) -> str:
        token = str(record_id).strip()
        if not token:
            raise ValueError("record_id must be non-empty")
        who = str(approver).strip()
        if not who:
            raise ValueError("approver must be non-empty: no anonymous promotion")
        why = str(rationale).strip()
        if not why:
            raise ValueError("rationale must be non-empty: no unexplained promotion")
        item = self.connection.execute(
            "SELECT record_id FROM review_items WHERE record_id = ?", (token,)
        ).fetchone()
        if item is None:
            raise ReviewNotFoundError(f"record was never submitted for review: {token}")
        prior = self.connection.execute(
            "SELECT decision FROM review_decisions WHERE record_id = ?", (token,)
        ).fetchone()
        if prior is not None:
            raise ValueError(f"review for {token} is already decided: {prior['decision']}")
        decision_id = str(uuid4())
        decided_at = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """INSERT INTO review_decisions
            (decision_id, record_id, decision, approver, rationale, decided_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (decision_id, token, decision, who, why, decided_at),
        )
        self.connection.commit()
        return decision_id

    def get_status(self, record_id: str) -> str:
        """Return PENDING, APPROVED, REJECTED, or NOT_SUBMITTED (fail-closed)."""
        token = str(record_id).strip()
        if not token:
            raise ValueError("record_id must be non-empty")
        item = self.connection.execute(
            "SELECT record_id FROM review_items WHERE record_id = ?", (token,)
        ).fetchone()
        if item is None:
            return "NOT_SUBMITTED"
        row = self.connection.execute(
            "SELECT decision FROM review_decisions WHERE record_id = ?", (token,)
        ).fetchone()
        if row is None:
            return "PENDING"
        return str(row["decision"])

    def is_approved(self, record_id: str) -> bool:
        """True only after explicit human approval, never on PASS alone."""
        return self.get_status(record_id) == "APPROVED"

    def list_pending(self) -> list[str]:
        """Return record IDs still awaiting a human decision, in submit order."""
        pending: list[str] = []
        rows = self.connection.execute(
            "SELECT record_id FROM review_items ORDER BY rowid"
        ).fetchall()
        for row in rows:
            token = str(row["record_id"])
            if self.get_status(token) == "PENDING":
                pending.append(token)
        return pending


def _clean_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text
