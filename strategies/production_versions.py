"""Immutable production strategy versions (Module 4 promotion target).

Why this file exists: Module 4 may load only a validated production strategy,
which means PASS plus explicit human approval plus an immutable version row.
This store is append-only so a version can never be edited in place; a new
promotion creates a new row and the latest row for a strategy wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any


@dataclass(frozen=True)
class ProductionVersion:
    version_id: str
    strategy_id: str
    edge_validation_record_id: str
    approver: str
    rationale: str
    approved_at: datetime
    created_at: datetime


class ProductionVersionStore:
    """SQLite-backed append-only registry of approved production versions."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS strategy_versions (
                version_id TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                edge_validation_record_id TEXT NOT NULL,
                approver TEXT NOT NULL,
                rationale TEXT NOT NULL,
                approved_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_strategy_versions_strategy
                ON strategy_versions(strategy_id, created_at);
            CREATE TRIGGER IF NOT EXISTS strategy_versions_no_update
            BEFORE UPDATE ON strategy_versions
            BEGIN
                SELECT RAISE(ABORT, 'strategy_versions are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS strategy_versions_no_delete
            BEFORE DELETE ON strategy_versions
            BEGIN
                SELECT RAISE(ABORT, 'strategy_versions are append-only');
            END;
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> ProductionVersionStore:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def create_version(
        self,
        *,
        version_id: str,
        strategy_id: str,
        edge_validation_record_id: str,
        approver: str,
        rationale: str,
        approved_at: datetime | None = None,
    ) -> ProductionVersion:
        """Append one immutable version. Empty approver or rationale raises."""
        vid = str(version_id).strip()
        if not vid:
            raise ValueError("version_id must be non-empty")
        name = str(strategy_id).strip()
        if not name:
            raise ValueError("strategy_id must be non-empty")
        record = str(edge_validation_record_id).strip()
        if not record:
            raise ValueError("edge_validation_record_id must be non-empty")
        who = str(approver).strip()
        if not who:
            raise ValueError("approver must be non-empty")
        why = str(rationale).strip()
        if not why:
            raise ValueError("rationale must be non-empty")
        moment = approved_at
        if moment is None:
            moment = datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        created = datetime.now(timezone.utc)
        found = self.connection.execute(
            "SELECT 1 FROM strategy_versions WHERE version_id = ?", (vid,)
        ).fetchone()
        if found is not None:
            raise ValueError(f"production version already exists: {vid}")
        self.connection.execute(
            """INSERT INTO strategy_versions
            (version_id, strategy_id, edge_validation_record_id,
             approver, rationale, approved_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (vid, name, record, who, why, moment.isoformat(), created.isoformat()),
        )
        self.connection.commit()
        return ProductionVersion(
            version_id=vid,
            strategy_id=name,
            edge_validation_record_id=record,
            approver=who,
            rationale=why,
            approved_at=moment,
            created_at=created,
        )

    def get_active_version(self, strategy_id: str) -> ProductionVersion | None:
        """Return the latest immutable version for a strategy, or None."""
        name = str(strategy_id).strip()
        if not name:
            raise ValueError("strategy_id must be non-empty")
        row = self.connection.execute(
            """SELECT * FROM strategy_versions
            WHERE strategy_id = ? ORDER BY rowid DESC LIMIT 1""",
            (name,),
        ).fetchone()
        if row is None:
            return None
        return ProductionVersion(
            version_id=str(row["version_id"]),
            strategy_id=str(row["strategy_id"]),
            edge_validation_record_id=str(row["edge_validation_record_id"]),
            approver=str(row["approver"]),
            rationale=str(row["rationale"]),
            approved_at=datetime.fromisoformat(str(row["approved_at"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

    def is_promoted(self, strategy_id: str) -> bool:
        """True only when at least one immutable version row exists."""
        return self.get_active_version(strategy_id) is not None

    def list_versions(self, strategy_id: str | None = None) -> list[ProductionVersion]:
        """Return versions in insertion order, optionally filtered by strategy."""
        versions: list[ProductionVersion] = []
        if strategy_id is None:
            rows = self.connection.execute(
                "SELECT * FROM strategy_versions ORDER BY rowid"
            ).fetchall()
        else:
            name = str(strategy_id).strip()
            if not name:
                raise ValueError("strategy_id must be non-empty")
            rows = self.connection.execute(
                "SELECT * FROM strategy_versions WHERE strategy_id = ? ORDER BY rowid",
                (name,),
            ).fetchall()
        for row in rows:
            versions.append(
                ProductionVersion(
                    version_id=str(row["version_id"]),
                    strategy_id=str(row["strategy_id"]),
                    edge_validation_record_id=str(row["edge_validation_record_id"]),
                    approver=str(row["approver"]),
                    rationale=str(row["rationale"]),
                    approved_at=datetime.fromisoformat(str(row["approved_at"])),
                    created_at=datetime.fromisoformat(str(row["created_at"])),
                )
            )
        return versions
