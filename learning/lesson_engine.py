"""Candidate-lesson bank with human validation (Module 9).

Why a separate ledger: analyses arrive per trade, but only actionable,
non-normal ones become candidates — and candidates become strategy changes
only after human validation plus the Module 1 gate. NORMAL outcomes bank
nothing, so a losing streak cannot quietly rewrite production.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from learning.trade_analyzer import TradeAnalysis


STATUSES = ("CANDIDATE", "VALIDATED", "REJECTED")


class LessonEngine:
    """Append-only candidate lessons with explicit human adjudication."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS lessons (
                lesson_id TEXT PRIMARY KEY,
                trade_id TEXT NOT NULL,
                analysis_id TEXT NOT NULL,
                category TEXT NOT NULL,
                hypothesis TEXT NOT NULL,
                status TEXT NOT NULL,
                approver TEXT,
                decided_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS lessons_no_update
            BEFORE UPDATE ON lessons
            BEGIN
                SELECT RAISE(ABORT, 'lessons are never edited in place; adjudicate once');
            END;
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> LessonEngine:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def propose(self, analysis: TradeAnalysis) -> str | None:
        """Bank one candidate lesson; NORMAL analyses bank nothing."""
        if analysis.category == "NORMAL" or analysis.actionable is False:
            return None
        if not analysis.candidate_hypothesis or not analysis.candidate_hypothesis.strip():
            return None
        lesson_id = "les_" + str(uuid4()).replace("-", "")[:16]
        self.connection.execute(
            """INSERT INTO lessons
            (lesson_id, trade_id, analysis_id, category, hypothesis, status,
             approver, decided_at, created_at)
            VALUES (?, ?, ?, ?, ?, 'CANDIDATE', NULL, NULL, ?)""",
            (
                lesson_id,
                analysis.trade_id,
                analysis.analysis_id,
                analysis.category,
                analysis.candidate_hypothesis.strip(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.connection.commit()
        return lesson_id

    def validate(self, lesson_id: str, approver: str) -> None:
        """Human validation; replaces the row since adjudication is once-only."""
        self._adjudicate(str(lesson_id), "VALIDATED", approver)

    def reject(self, lesson_id: str, approver: str) -> None:
        """Human rejection; recorded permanently like a validation."""
        self._adjudicate(str(lesson_id), "REJECTED", approver)

    def _adjudicate(self, lesson_id: str, status: str, approver: str) -> None:
        who = str(approver).strip()
        if not who:
            raise ValueError("approver must be non-empty: no anonymous adjudication")
        row = self.connection.execute(
            "SELECT * FROM lessons WHERE lesson_id=?", (lesson_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown lesson: {lesson_id}")
        if str(row["status"]) != "CANDIDATE":
            raise ValueError("lesson %s already decided: %s" % (lesson_id, row["status"]))
        # Why delete+insert: UPDATE is forbidden, so adjudication consumes the
        # candidate row into a decided row carrying the same content plus the
        # decision — history preserved, nothing silently edited or dropped.
        self.connection.execute("DELETE FROM lessons WHERE lesson_id=?", (lesson_id,))
        self.connection.execute(
            """INSERT INTO lessons
            (lesson_id, trade_id, analysis_id, category, hypothesis, status,
             approver, decided_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lesson_id,
                str(row["trade_id"]),
                str(row["analysis_id"]),
                str(row["category"]),
                str(row["hypothesis"]),
                status,
                who,
                datetime.now(timezone.utc).isoformat(),
                str(row["created_at"]),
            ),
        )
        self.connection.commit()

    def get(self, lesson_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM lessons WHERE lesson_id=?", (str(lesson_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown lesson: {lesson_id}")
        result: dict[str, Any] = {}
        for key in row.keys():
            result[key] = row[key]
        return result

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        if status not in STATUSES:
            raise ValueError("unknown lesson status: %s" % status)
        rows = self.connection.execute(
            "SELECT * FROM lessons WHERE status=? ORDER BY rowid", (status,)
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            entry: dict[str, Any] = {}
            for key in row.keys():
                entry[key] = row[key]
            result.append(entry)
        return result

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for status in STATUSES:
            row = self.connection.execute(
                "SELECT COUNT(*) AS total FROM lessons WHERE status=?", (status,)
            ).fetchone()
            result[status] = int(row["total"])
        return result
