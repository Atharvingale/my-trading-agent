"""Execution request state tracking with idempotent submission (Module 7).

Why a local ledger: retries and duplicate webhook deliveries must never
double-submit. The execution_id doubles as the idempotency key, and
submit_once() returns the cached outcome for any already-seen execution_id
without touching the network again. An unreachable n8n marks the request
EXPIRED rather than queueing it for a late, stale fill.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from execution.n8n_client import (
    ExecutionConfig,
    ExecutionRequest,
    N8nUnavailableError,
    RequestExpiredError,
    Sender,
    submit_request,
)


STATES = ("PENDING", "SUBMITTED", "ACKED", "FILLED", "REJECTED", "EXPIRED")
TERMINAL_SUBMITTED = ("SUBMITTED", "ACKED", "FILLED")


class ExecutionOrderManager:
    """Idempotent request → order → fill tracker backed by SQLite."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS execution_requests (
                execution_id TEXT PRIMARY KEY,
                risk_decision_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                order_type TEXT NOT NULL,
                protection_json TEXT NOT NULL,
                expiry TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL,
                order_id TEXT,
                ack_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS execution_requests_no_delete
            BEFORE DELETE ON execution_requests
            BEGIN
                SELECT RAISE(ABORT, 'execution_requests are append-only');
            END;
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> ExecutionOrderManager:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def register(self, request: ExecutionRequest) -> str:
        """Store a new request as PENDING; re-registration is a no-op."""
        found = self.connection.execute(
            "SELECT execution_id FROM execution_requests WHERE execution_id = ?",
            (request.execution_id,),
        ).fetchone()
        if found is not None:
            return request.execution_id
        moment = datetime.now(timezone.utc).isoformat()
        protection = {}
        for key in request.protection:
            protection[key] = request.protection[key]
        self.connection.execute(
            """INSERT INTO execution_requests
            (execution_id, risk_decision_id, symbol, side, quantity, order_type,
             protection_json, expiry, idempotency_key, state, order_id, ack_json,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', NULL, NULL, ?, ?)""",
            (
                request.execution_id,
                request.risk_decision_id,
                request.symbol,
                request.side,
                float(request.quantity),
                request.order_type,
                json.dumps(protection, separators=(",", ":"), sort_keys=True),
                request.expiry.isoformat(),
                request.idempotency_key,
                moment,
                moment,
            ),
        )
        self.connection.commit()
        return request.execution_id

    def get(self, execution_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM execution_requests WHERE execution_id = ?",
            (str(execution_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown execution: {execution_id}")
        result: dict[str, Any] = {}
        for key in row.keys():
            result[key] = row[key]
        return result

    def submit_once(
        self,
        request: ExecutionRequest,
        *,
        config: ExecutionConfig,
        sender: Sender | None = None,
        now: datetime,
        kill_switch_active: bool = False,
        risk_decision: Any = None,
    ) -> dict[str, Any]:
        """Submit at most once per execution_id; duplicates get the cache.

        Returns {"state": ..., "ack": ...}. Transport failure marks EXPIRED
        and raises N8nUnavailableError; expired instructions raise
        RequestExpiredError without ever sending.
        """
        self.register(request)
        current = self.get(request.execution_id)
        for done in TERMINAL_SUBMITTED:
            if current["state"] == done:
                cached: dict[str, Any] = {}
                cached["state"] = str(current["state"])
                if current["ack_json"] is not None:
                    cached["ack"] = json.loads(str(current["ack_json"]))
                else:
                    cached["ack"] = None
                cached["duplicate_suppressed"] = True
                return cached
        if current["state"] in ("REJECTED", "EXPIRED", "FILLED"):
            cached_final: dict[str, Any] = {}
            cached_final["state"] = str(current["state"])
            cached_final["ack"] = None
            cached_final["duplicate_suppressed"] = True
            return cached_final
        try:
            ack = submit_request(
                request, config=config, sender=sender, now=now,
                kill_switch_active=kill_switch_active,
                risk_decision=risk_decision,
            )
        except RequestExpiredError:
            self._set_state(request.execution_id, "EXPIRED")
            raise
        except N8nUnavailableError:
            self._set_state(request.execution_id, "EXPIRED")
            raise
        self._set_state(request.execution_id, "SUBMITTED", ack=ack)
        order_id = None
        if isinstance(ack, dict):
            raw_order = ack.get("order_id")
            if isinstance(raw_order, str) and raw_order.strip():
                order_id = raw_order.strip()
        if order_id is not None:
            self._set_state(request.execution_id, "ACKED", order_id=order_id, ack=ack)
            outcome: dict[str, Any] = {}
            outcome["state"] = "ACKED"
            outcome["ack"] = ack
            outcome["duplicate_suppressed"] = False
            return outcome
        outcome_sent: dict[str, Any] = {}
        outcome_sent["state"] = "SUBMITTED"
        outcome_sent["ack"] = ack
        outcome_sent["duplicate_suppressed"] = False
        return outcome_sent

    def mark_acked(self, execution_id: str, order_id: str) -> None:
        self._set_state(str(execution_id), "ACKED", order_id=str(order_id))

    def mark_filled(self, execution_id: str) -> None:
        self._set_state(str(execution_id), "FILLED")

    def mark_rejected(self, execution_id: str) -> None:
        self._set_state(str(execution_id), "REJECTED")

    def mark_expired(self, execution_id: str) -> None:
        self._set_state(str(execution_id), "EXPIRED")

    def list_by_state(self, state: str) -> list[dict[str, Any]]:
        if state not in STATES:
            raise ValueError("unknown execution state: %s" % state)
        rows = self.connection.execute(
            "SELECT * FROM execution_requests WHERE state = ? ORDER BY rowid", (state,)
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            entry: dict[str, Any] = {}
            for key in row.keys():
                entry[key] = row[key]
            result.append(entry)
        return result

    def _set_state(
        self, execution_id: str, state: str, order_id: str | None = None, ack: Any = None
    ) -> None:
        if state not in STATES:
            raise ValueError("unknown execution state: %s" % state)
        moment = datetime.now(timezone.utc).isoformat()
        if order_id is not None:
            self.connection.execute(
                "UPDATE execution_requests SET state=?, order_id=?, updated_at=? WHERE execution_id=?",
                (state, str(order_id), moment, str(execution_id)),
            )
        else:
            self.connection.execute(
                "UPDATE execution_requests SET state=?, updated_at=? WHERE execution_id=?",
                (state, moment, str(execution_id)),
            )
        if ack is not None:
            self.connection.execute(
                "UPDATE execution_requests SET ack_json=? WHERE execution_id=?",
                (json.dumps(ack, separators=(",", ":"), sort_keys=True, default=str), str(execution_id)),
            )
        self.connection.commit()
