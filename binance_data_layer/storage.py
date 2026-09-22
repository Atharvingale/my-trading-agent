"""SQLite persistence for normalized market events and feature snapshots."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS market_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stream TEXT NOT NULL,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_time_ms INTEGER NOT NULL,
    received_time_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_market_events_symbol_time
    ON market_events(symbol, event_time_ms);
CREATE TABLE IF NOT EXISTS feature_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    event_time TEXT NOT NULL,
    created_time_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_features_symbol_time
    ON feature_snapshots(symbol, created_time_ms);
CREATE TABLE IF NOT EXISTS breadth_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_time_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS data_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component TEXT NOT NULL,
    symbol TEXT,
    status TEXT NOT NULL,
    observed_time_ms INTEGER NOT NULL,
    details_json TEXT NOT NULL
);
"""


class MarketStore:
    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def save_event(
        self,
        *,
        stream: str,
        symbol: str,
        event_type: str,
        event_time_ms: int,
        received_time_ms: int,
        payload: Mapping[str, Any],
    ) -> None:
        self.connection.execute(
            """INSERT INTO market_events
            (stream, symbol, event_type, event_time_ms, received_time_ms, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (stream, symbol, event_type, event_time_ms, received_time_ms, json.dumps(payload, separators=(",", ":"))),
        )
        self.connection.commit()

    def save_features(self, snapshot: Mapping[str, Any], created_time_ms: int) -> None:
        self.connection.execute(
            """INSERT INTO feature_snapshots
            (symbol, event_time, created_time_ms, payload_json)
            VALUES (?, ?, ?, ?)""",
            (snapshot["symbol"], snapshot["event_time"], created_time_ms, json.dumps(dict(snapshot), separators=(",", ":"))),
        )
        self.connection.commit()

    def save_breadth(self, snapshot: Mapping[str, Any], created_time_ms: int | None = None) -> None:
        self.connection.execute(
            "INSERT INTO breadth_snapshots (created_time_ms, payload_json) VALUES (?, ?)",
            (int(created_time_ms if created_time_ms is not None else time.time() * 1000), json.dumps(dict(snapshot), separators=(",", ":"))),
        )
        self.connection.commit()

    def save_health(
        self,
        *,
        component: str,
        symbol: str | None,
        status: str,
        observed_time_ms: int,
        details: Mapping[str, Any],
    ) -> None:
        self.connection.execute(
            """INSERT INTO data_health
            (component, symbol, status, observed_time_ms, details_json)
            VALUES (?, ?, ?, ?, ?)""",
            (component, symbol, status, observed_time_ms, json.dumps(dict(details), separators=(",", ":"))),
        )
        self.connection.commit()

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for table in ("market_events", "feature_snapshots", "data_health"):
            result[table] = int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return result
