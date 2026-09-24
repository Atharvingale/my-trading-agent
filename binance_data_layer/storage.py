"""SQLite persistence for normalized market events and feature snapshots."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections import deque
from pathlib import Path
from typing import Any, Mapping


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
CREATE INDEX IF NOT EXISTS idx_market_events_received_time
    ON market_events(received_time_ms);
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
CREATE INDEX IF NOT EXISTS idx_breadth_created_time
    ON breadth_snapshots(created_time_ms);
CREATE TABLE IF NOT EXISTS data_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component TEXT NOT NULL,
    symbol TEXT,
    status TEXT NOT NULL,
    observed_time_ms INTEGER NOT NULL,
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_health_observed_time
    ON data_health(observed_time_ms);
"""


class MarketStore:
    def __init__(self, database_path: str | Path, *, batch_size: int = 50) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(SCHEMA)
        self.connection.commit()
        self.batch_size = max(1, batch_size)
        self._pending: deque[tuple[str, tuple[Any, ...]]] = deque()
        self._write_queue: asyncio.Queue[tuple[str, tuple[Any, ...]] | None] | None = None
        self._writer_task: asyncio.Task[None] | None = None

    def close(self) -> None:
        self.flush()
        self.connection.close()

    def enqueue_event(
        self,
        *,
        stream: str,
        symbol: str,
        event_type: str,
        event_time_ms: int,
        received_time_ms: int,
        payload: Mapping[str, Any],
    ) -> None:
        self._queue(
            "event",
            (
                stream,
                symbol,
                event_type,
                event_time_ms,
                received_time_ms,
                json.dumps(payload, separators=(",", ":")),
            ),
        )

    def enqueue_features(self, snapshot: Mapping[str, Any], created_time_ms: int) -> None:
        self._queue(
            "features",
            (
                snapshot["symbol"],
                snapshot["event_time"],
                created_time_ms,
                json.dumps(dict(snapshot), separators=(",", ":")),
            ),
        )

    def enqueue_breadth(self, snapshot: Mapping[str, Any], created_time_ms: int | None = None) -> None:
        self._queue(
            "breadth",
            (
                int(created_time_ms if created_time_ms is not None else time.time() * 1000),
                json.dumps(dict(snapshot), separators=(",", ":")),
            ),
        )

    def enqueue_health(
        self,
        *,
        component: str,
        symbol: str | None,
        status: str,
        observed_time_ms: int,
        details: Mapping[str, Any],
    ) -> None:
        self._queue(
            "health",
            (
                component,
                symbol,
                status,
                observed_time_ms,
                json.dumps(dict(details), separators=(",", ":")),
            ),
        )

    def pending_writes(self) -> int:
        queued = 0
        if self._write_queue is not None:
            queued = self._write_queue.qsize()
        return len(self._pending) + queued

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
        self.enqueue_event(
            stream=stream,
            symbol=symbol,
            event_type=event_type,
            event_time_ms=event_time_ms,
            received_time_ms=received_time_ms,
            payload=payload,
        )
        if self._write_queue is None:
            self.flush()

    def save_features(self, snapshot: Mapping[str, Any], created_time_ms: int) -> None:
        self.enqueue_features(snapshot, created_time_ms)
        if self._write_queue is None:
            self.flush()

    def save_breadth(self, snapshot: Mapping[str, Any], created_time_ms: int | None = None) -> None:
        self.enqueue_breadth(snapshot, created_time_ms)
        if self._write_queue is None:
            self.flush()

    def save_health(
        self,
        *,
        component: str,
        symbol: str | None,
        status: str,
        observed_time_ms: int,
        details: Mapping[str, Any],
    ) -> None:
        self.enqueue_health(
            component=component,
            symbol=symbol,
            status=status,
            observed_time_ms=observed_time_ms,
            details=details,
        )
        if self._write_queue is None:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        while self._pending:
            kind, values = self._pending.popleft()
            self._execute(kind, values)
        self.connection.commit()

    def start_writer(self, queue_size: int = 10_000) -> asyncio.Queue[tuple[str, tuple[Any, ...]] | None]:
        if self._write_queue is None:
            self._write_queue = asyncio.Queue(maxsize=queue_size)
            while self._pending:
                self._write_queue.put_nowait(self._pending.popleft())
        return self._write_queue

    async def run_writer(self) -> None:
        queue = self.start_writer()
        batch: list[tuple[str, tuple[Any, ...]]] = []
        while True:
            item = await queue.get()
            if item is None:
                if batch:
                    self._commit_batch(batch)
                return
            batch.append(item)
            if len(batch) >= self.batch_size or queue.empty():
                self._commit_batch(batch)
                batch = []

    async def stop_writer(self) -> None:
        if self._write_queue is None:
            self.flush()
            return
        await self._write_queue.put(None)
        if self._writer_task is not None:
            await self._writer_task
            self._writer_task = None

    def apply_retention(
        self,
        *,
        now_ms: int | None = None,
        event_retention_days: int = 7,
        feature_retention_days: int = 7,
        breadth_retention_days: int = 7,
        health_retention_days: int = 7,
        vacuum: bool = False,
    ) -> dict[str, Any]:
        observed = int(now_ms if now_ms is not None else time.time() * 1000)
        self.flush()
        deleted = {}
        deleted["market_events"] = self._delete_older_than(
            "market_events", "received_time_ms", observed, event_retention_days
        )
        deleted["feature_snapshots"] = self._delete_older_than(
            "feature_snapshots", "created_time_ms", observed, feature_retention_days
        )
        deleted["breadth_snapshots"] = self._delete_older_than(
            "breadth_snapshots", "created_time_ms", observed, breadth_retention_days
        )
        deleted["data_health"] = self._delete_older_than(
            "data_health", "observed_time_ms", observed, health_retention_days
        )
        self.connection.commit()
        try:
            self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass
        if vacuum:
            try:
                self.connection.execute("VACUUM")
            except sqlite3.OperationalError:
                pass
        self.connection.commit()
        return {"deleted": deleted, "now_ms": observed}

    def latest_breadth(self) -> dict[str, Any] | None:
        self.flush()
        row = self.connection.execute(
            "SELECT payload_json FROM breadth_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def latest_cross_exchange(self, symbol: str) -> dict[str, Any] | None:
        self.flush()
        row = self.connection.execute(
            """SELECT payload_json FROM market_events
            WHERE event_type = 'crossExchangeConfirmation' AND symbol = ?
            ORDER BY id DESC LIMIT 1""",
            (symbol.upper(),),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def recent_health(self, limit: int = 100) -> list[dict[str, Any]]:
        self.flush()
        rows = self.connection.execute(
            """SELECT component, symbol, status, observed_time_ms, details_json
            FROM data_health ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "component": row[0],
                    "symbol": row[1],
                    "status": row[2],
                    "observed_time_ms": row[3],
                    "details": json.loads(row[4]),
                }
            )
        return result

    def recent_events(self, *, symbol: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        self.flush()
        if symbol:
            rows = self.connection.execute(
                """SELECT stream, symbol, event_type, event_time_ms, received_time_ms, payload_json
                FROM market_events WHERE symbol = ? ORDER BY id DESC LIMIT ?""",
                (symbol.upper(), limit),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """SELECT stream, symbol, event_type, event_time_ms, received_time_ms, payload_json
                FROM market_events ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "stream": row[0],
                    "symbol": row[1],
                    "event_type": row[2],
                    "event_time_ms": row[3],
                    "received_time_ms": row[4],
                    "payload": json.loads(row[5]),
                }
            )
        return result

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for table in ("market_events", "feature_snapshots", "data_health"):
            result[table] = int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return result

    def _queue(self, kind: str, values: tuple[Any, ...]) -> None:
        item = (kind, values)
        if self._write_queue is not None:
            try:
                self._write_queue.put_nowait(item)
                return
            except asyncio.QueueFull:
                pass
        self._pending.append(item)
        if len(self._pending) >= self.batch_size:
            self.flush()

    def _commit_batch(self, batch: list[tuple[str, tuple[Any, ...]]]) -> None:
        for kind, values in batch:
            self._execute(kind, values)
        self.connection.commit()

    def _execute(self, kind: str, values: tuple[Any, ...]) -> None:
        if kind == "event":
            self.connection.execute(
                """INSERT INTO market_events
                (stream, symbol, event_type, event_time_ms, received_time_ms, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)""",
                values,
            )
        elif kind == "features":
            self.connection.execute(
                """INSERT INTO feature_snapshots
                (symbol, event_time, created_time_ms, payload_json)
                VALUES (?, ?, ?, ?)""",
                values,
            )
        elif kind == "breadth":
            self.connection.execute(
                "INSERT INTO breadth_snapshots (created_time_ms, payload_json) VALUES (?, ?)",
                values,
            )
        elif kind == "health":
            self.connection.execute(
                """INSERT INTO data_health
                (component, symbol, status, observed_time_ms, details_json)
                VALUES (?, ?, ?, ?, ?)""",
                values,
            )
        else:
            raise ValueError(f"unknown persistence kind: {kind}")

    def _delete_older_than(self, table: str, column: str, now_ms: int, days: int) -> int:
        cutoff = now_ms - days * 24 * 60 * 60 * 1000
        cursor = self.connection.execute(
            f"DELETE FROM {table} WHERE {column} < ?",
            (cutoff,),
        )
        return int(cursor.rowcount)
