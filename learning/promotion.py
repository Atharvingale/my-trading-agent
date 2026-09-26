"""Learning-pipeline promotion: validated lesson + PASS + approval (Module 9).

Why a wrapper, not a parallel path: the binding promotion rule already lives
in strategies.promotion.promote_candidate (live PASS plus explicit human
approval into an immutable version). This module adds the learning-plane
precondition — a human-VALIDATED lesson — then delegates, so no candidate can
reach production around the gate. Disable and rollback only move status
pointers; version history is never edited or deleted.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from strategies.promotion import promote_candidate as _promote_candidate


def promote_candidate(
    *,
    lesson_id: str,
    lesson_engine: Any,
    strategy_id: str,
    edge_validation_record_id: str,
    registry: Any,
    reviews: Any,
    versions: Any,
    approver: str,
    rationale: str,
    version_id: str | None = None,
) -> Any:
    """Promote a validated lesson's candidate; refuse everything else.

    Raises KeyError for unknown lessons, ValueError for unvalidated ones,
    and StrategyNotGatedError when the linked gate record is missing or not
    a current PASS — the acceptance refusal, verified by unit test.
    """
    token = str(lesson_id).strip()
    if not token:
        raise ValueError("lesson_id must be non-empty")
    lesson = lesson_engine.get(token)
    if str(lesson.get("status", "")) != "VALIDATED":
        raise ValueError(
            "lesson %s is %s, not VALIDATED" % (token, lesson.get("status"))
        )
    return _promote_candidate(
        strategy_id=strategy_id,
        edge_validation_record_id=edge_validation_record_id,
        registry=registry,
        reviews=reviews,
        versions=versions,
        approver=approver,
        rationale=rationale,
        version_id=version_id,
    )


class StrategyStatus:
    """Active-version pointer plus disable flags; history never deleted."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS strategy_status (
                strategy_id TEXT PRIMARY KEY,
                active_version_id TEXT NOT NULL,
                disabled INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS status_history (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                action TEXT NOT NULL,
                version_id TEXT,
                approver TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> StrategyStatus:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def set_active(self, strategy_id: str, version_id: str, approver: str, rationale: str) -> None:
        """Point a strategy at a version; rollback is this same instant call."""
        name = str(strategy_id).strip()
        if not name:
            raise ValueError("strategy_id must be non-empty")
        vid = str(version_id).strip()
        if not vid:
            raise ValueError("version_id must be non-empty")
        who = str(approver).strip()
        if not who:
            raise ValueError("approver must be non-empty")
        why = str(rationale).strip()
        if not why:
            raise ValueError("rationale must be non-empty")
        moment = datetime.now(timezone.utc).isoformat()
        found = self.connection.execute(
            "SELECT strategy_id FROM strategy_status WHERE strategy_id=?", (name,)
        ).fetchone()
        if found is None:
            self.connection.execute(
                "INSERT INTO strategy_status (strategy_id, active_version_id, disabled, updated_at)"
                " VALUES (?, ?, 0, ?)",
                (name, vid, moment),
            )
        else:
            self.connection.execute(
                "UPDATE strategy_status SET active_version_id=?, updated_at=? WHERE strategy_id=?",
                (vid, moment, name),
            )
        self.connection.execute(
            "INSERT INTO status_history (strategy_id, action, version_id, approver, reason, created_at)"
            " VALUES (?, 'ACTIVATE', ?, ?, ?, ?)",
            (name, vid, who, why, moment),
        )
        self.connection.commit()

    def rollback(self, strategy_id: str, version_id: str, approver: str, rationale: str) -> None:
        """Instant rollback: one pointer write to a prior version, audited."""
        self.set_active(strategy_id, version_id, approver, "rollback: " + str(rationale).strip())

    def disable(self, strategy_id: str, approver: str, reason: str) -> None:
        """Halt a strategy without deleting any version history."""
        self._flag(str(strategy_id), True, approver, reason, "DISABLE")

    def enable(self, strategy_id: str, approver: str, reason: str) -> None:
        self._flag(str(strategy_id), False, approver, reason, "ENABLE")

    def _flag(self, strategy_id: str, disabled: bool, approver: str, reason: str, action: str) -> None:
        name = str(strategy_id).strip()
        if not name:
            raise ValueError("strategy_id must be non-empty")
        who = str(approver).strip()
        if not who:
            raise ValueError("approver must be non-empty")
        why = str(reason).strip()
        if not why:
            raise ValueError("reason must be non-empty")
        moment = datetime.now(timezone.utc).isoformat()
        found = self.connection.execute(
            "SELECT strategy_id FROM strategy_status WHERE strategy_id=?", (name,)
        ).fetchone()
        if found is None:
            self.connection.execute(
                "INSERT INTO strategy_status (strategy_id, active_version_id, disabled, updated_at)"
                " VALUES (?, '', ?, ?)",
                (name, 1 if disabled else 0, moment),
            )
        else:
            self.connection.execute(
                "UPDATE strategy_status SET disabled=?, updated_at=? WHERE strategy_id=?",
                (1 if disabled else 0, moment, name),
            )
        self.connection.execute(
            "INSERT INTO status_history (strategy_id, action, version_id, approver, reason, created_at)"
            " VALUES (?, ?, NULL, ?, ?, ?)",
            (name, action, who, why, moment),
        )
        self.connection.commit()

    def is_disabled(self, strategy_id: str) -> bool:
        row = self.connection.execute(
            "SELECT disabled FROM strategy_status WHERE strategy_id=?", (str(strategy_id),)
        ).fetchone()
        if row is None:
            return False
        return int(row["disabled"]) == 1

    def active_version(self, strategy_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT active_version_id FROM strategy_status WHERE strategy_id=?", (str(strategy_id),)
        ).fetchone()
        if row is None:
            return None
        token = str(row["active_version_id"]).strip()
        return token or None

    def history(self, strategy_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM status_history WHERE strategy_id=? ORDER BY event_id", (str(strategy_id),)
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            entry: dict[str, Any] = {}
            for key in row.keys():
                entry[key] = row[key]
            result.append(entry)
        return result
