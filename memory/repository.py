"""Append-friendly unified store with query-enforced traceability (Module 10).

Why SQLite: stdlib only, same engine as the edge gate and MarketStore, so
the audit trail works offline without a new dependency. Migrations are
additive: migrate() records SCHEMA_VERSION in user_version and reruns the
idempotent CREATE IF NOT EXISTS script, so reopening an old file upgrades it
without data loss. edge_validation_records and strategy_versions reject
UPDATE and DELETE both in SQL triggers and at this layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from memory.schemas import CHAIN_ORDER, SCHEMA, SCHEMA_VERSION


class TraceNotFoundError(KeyError):
    """Raised when trace() cannot resolve a trade_id to a full chain."""


class MemoryRepository:
    """Unified persistence for all 20 Module 10 tables."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.migrate()
        self.connection.commit()

    def migrate(self) -> int:
        """Apply the idempotent schema and stamp the schema version."""
        self.connection.executescript(SCHEMA)
        self.connection.execute("PRAGMA user_version=%d" % SCHEMA_VERSION)
        self.connection.commit()
        return SCHEMA_VERSION

    def schema_version(self) -> int:
        row = self.connection.execute("PRAGMA user_version").fetchone()
        return int(row[0])

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> MemoryRepository:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    # -- destructive edits are refused at the repository layer --
    def update_record(self, table: str, record_id: str) -> None:
        raise ValueError("memory records are append-only, no updates: %s/%s" % (table, record_id))

    def delete_record(self, table: str, record_id: str) -> None:
        raise ValueError("memory records are append-only, no deletes: %s/%s" % (table, record_id))

    # -- supporting market tables --
    def record_raw_event(
        self,
        *,
        event_id: str,
        symbol: str,
        stream: str,
        event_type: str,
        event_time_ms: int,
        received_time_ms: int,
        payload: Mapping[str, Any] | None = None,
    ) -> str:
        eid = _require_id(event_id, "event_id")
        self._insert(
            "raw_market_events",
            {
                "event_id": eid,
                "symbol": _require_text(symbol, "symbol"),
                "stream": _require_text(stream, "stream"),
                "event_type": _require_text(event_type, "event_type"),
                "event_time_ms": int(event_time_ms),
                "received_time_ms": int(received_time_ms),
                "payload_json": _json(dict(payload) if payload is not None else {}),
                "created_at": _utc_now_text(),
            },
        )
        return eid

    def record_candle(
        self,
        *,
        candle_id: str,
        symbol: str,
        interval: str,
        open_time_ms: int,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> str:
        cid = _require_id(candle_id, "candle_id")
        self._insert(
            "candles",
            {
                "candle_id": cid,
                "symbol": _require_text(symbol, "symbol"),
                "interval": _require_text(interval, "interval"),
                "open_time_ms": int(open_time_ms),
                "open": float(open),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(volume),
                "created_at": _utc_now_text(),
            },
        )
        return cid

    def record_market_snapshot(
        self, *, snapshot_id: str, symbol: str, event_time_ms: int, payload: Mapping[str, Any]
    ) -> str:
        sid = _require_id(snapshot_id, "snapshot_id")
        self._insert(
            "feature_snapshots",
            {
                "snapshot_id": sid,
                "symbol": _require_text(symbol, "symbol"),
                "event_time_ms": int(event_time_ms),
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return sid

    def record_breadth(self, *, breadth_id: str, payload: Mapping[str, Any]) -> str:
        bid = _require_id(breadth_id, "breadth_id")
        self._insert(
            "breadth_snapshots",
            {"breadth_id": bid, "payload_json": _json(dict(payload)), "created_at": _utc_now_text()},
        )
        return bid

    def record_derivatives(
        self,
        *,
        derivatives_id: str,
        symbol: str,
        payload: Mapping[str, Any],
        funding_rate: float | None = None,
        open_interest: float | None = None,
        basis: float | None = None,
        liquidations: float | None = None,
    ) -> str:
        did = _require_id(derivatives_id, "derivatives_id")
        self._insert(
            "derivatives_snapshots",
            {
                "derivatives_id": did,
                "symbol": _require_text(symbol, "symbol"),
                "funding_rate": funding_rate,
                "open_interest": open_interest,
                "basis": basis,
                "liquidations": liquidations,
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return did

    def record_universe(self, *, history_id: str, symbols: list[str], reason: str) -> str:
        hid = _require_id(history_id, "history_id")
        names: list[str] = []
        for symbol in symbols:
            names.append(_require_text(symbol, "symbols entry"))
        self._insert(
            "universe_history",
            {
                "history_id": hid,
                "symbols_json": _json(names),
                "reason": _require_text(reason, "reason"),
                "created_at": _utc_now_text(),
            },
        )
        return hid

    def record_health(
        self,
        *,
        health_id: str,
        component: str,
        status: str,
        observed_time_ms: int,
        details: Mapping[str, Any] | None = None,
        symbol: str | None = None,
    ) -> str:
        hid = _require_id(health_id, "health_id")
        clean_symbol = None
        if symbol is not None:
            clean_symbol = _require_text(symbol, "symbol")
        self._insert(
            "data_health",
            {
                "health_id": hid,
                "component": _require_text(component, "component"),
                "symbol": clean_symbol,
                "status": _require_text(status, "status"),
                "observed_time_ms": int(observed_time_ms),
                "details_json": _json(dict(details) if details is not None else {}),
                "created_at": _utc_now_text(),
            },
        )
        return hid

    # -- chain tables --
    def record_edge_validation(
        self,
        *,
        record_id: str,
        strategy_id: str,
        strategy_family: str,
        verdict: str,
        payload: Mapping[str, Any],
        snapshot_id: str | None = None,
    ) -> str:
        rid = _require_id(record_id, "record_id")
        sid = None
        if snapshot_id is not None:
            sid = _require_text(snapshot_id, "snapshot_id")
        self._insert(
            "edge_validation_records",
            {
                "record_id": rid,
                "strategy_id": _require_text(strategy_id, "strategy_id"),
                "strategy_family": _require_text(strategy_family, "strategy_family"),
                "verdict": _require_text(verdict, "verdict"),
                "snapshot_id": sid,
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return rid

    def record_decision(
        self,
        *,
        decision_id: str,
        symbol: str,
        action: str,
        confidence: float,
        market_snapshot_id: str,
        edge_validation_record_id: str,
        payload: Mapping[str, Any],
    ) -> str:
        did = _require_id(decision_id, "decision_id")
        self._insert(
            "decisions",
            {
                "decision_id": did,
                "symbol": _require_text(symbol, "symbol"),
                "action": _require_text(action, "action"),
                "confidence": float(confidence),
                "market_snapshot_id": _require_text(market_snapshot_id, "market_snapshot_id"),
                "edge_validation_record_id": _require_text(
                    edge_validation_record_id, "edge_validation_record_id"
                ),
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return did

    def record_proposal(
        self,
        *,
        proposal_id: str,
        decision_id: str,
        strategy_id: str,
        action: str,
        edge_validation_record_id: str,
        payload: Mapping[str, Any],
    ) -> str:
        pid = _require_id(proposal_id, "proposal_id")
        self._insert(
            "strategy_proposals",
            {
                "proposal_id": pid,
                "decision_id": _require_text(decision_id, "decision_id"),
                "strategy_id": _require_text(strategy_id, "strategy_id"),
                "action": _require_text(action, "action"),
                "edge_validation_record_id": _require_text(
                    edge_validation_record_id, "edge_validation_record_id"
                ),
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return pid

    def record_evidence(
        self, *, evidence_id: str, decision_id: str, payload: Mapping[str, Any], proposal_id: str | None = None
    ) -> str:
        eid = _require_id(evidence_id, "evidence_id")
        clean_proposal = None
        if proposal_id is not None:
            clean_proposal = _require_text(proposal_id, "proposal_id")
        self._insert(
            "decision_evidence",
            {
                "evidence_id": eid,
                "decision_id": _require_text(decision_id, "decision_id"),
                "proposal_id": clean_proposal,
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return eid

    def record_risk(
        self, *, risk_decision_id: str, decision_id: str, status: str, approved_quantity: float, payload: Mapping[str, Any]
    ) -> str:
        rid = _require_id(risk_decision_id, "risk_decision_id")
        self._insert(
            "risk_decisions",
            {
                "risk_decision_id": rid,
                "decision_id": _require_text(decision_id, "decision_id"),
                "status": _require_text(status, "status"),
                "approved_quantity": float(approved_quantity),
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return rid

    def record_execution(
        self, *, execution_id: str, risk_decision_id: str, status: str, payload: Mapping[str, Any]
    ) -> str:
        eid = _require_id(execution_id, "execution_id")
        self._insert(
            "executions",
            {
                "execution_id": eid,
                "risk_decision_id": _require_text(risk_decision_id, "risk_decision_id"),
                "status": _require_text(status, "status"),
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return eid

    def record_order(
        self,
        *,
        order_id: str,
        execution_id: str,
        symbol: str,
        side: str,
        quantity: float,
        status: str,
        payload: Mapping[str, Any],
    ) -> str:
        oid = _require_id(order_id, "order_id")
        self._insert(
            "orders",
            {
                "order_id": oid,
                "execution_id": _require_text(execution_id, "execution_id"),
                "symbol": _require_text(symbol, "symbol"),
                "side": _require_text(side, "side"),
                "quantity": float(quantity),
                "status": _require_text(status, "status"),
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return oid

    def record_position(
        self, *, position_id: str, order_id: str, symbol: str, quantity: float, payload: Mapping[str, Any]
    ) -> str:
        pid = _require_id(position_id, "position_id")
        self._insert(
            "positions",
            {
                "position_id": pid,
                "order_id": _require_text(order_id, "order_id"),
                "symbol": _require_text(symbol, "symbol"),
                "quantity": float(quantity),
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return pid

    def record_trade(
        self, *, trade_id: str, position_id: str, symbol: str, pnl: float, payload: Mapping[str, Any]
    ) -> str:
        tid = _require_id(trade_id, "trade_id")
        self._insert(
            "trades",
            {
                "trade_id": tid,
                "position_id": _require_text(position_id, "position_id"),
                "symbol": _require_text(symbol, "symbol"),
                "pnl": float(pnl),
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return tid

    def record_analysis(
        self, *, analysis_id: str, trade_id: str, diagnosis: str, payload: Mapping[str, Any]
    ) -> str:
        aid = _require_id(analysis_id, "analysis_id")
        self._insert(
            "trade_analysis",
            {
                "analysis_id": aid,
                "trade_id": _require_text(trade_id, "trade_id"),
                "diagnosis": _require_text(diagnosis, "diagnosis"),
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return aid

    def record_lesson(
        self, *, lesson_id: str, analysis_id: str, status: str, payload: Mapping[str, Any]
    ) -> str:
        lid = _require_id(lesson_id, "lesson_id")
        self._insert(
            "lessons",
            {
                "lesson_id": lid,
                "analysis_id": _require_text(analysis_id, "analysis_id"),
                "status": _require_text(status, "status"),
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return lid

    def record_strategy_version(
        self,
        *,
        version_id: str,
        strategy_id: str,
        edge_validation_record_id: str,
        approver: str,
        payload: Mapping[str, Any],
        lesson_id: str | None = None,
    ) -> str:
        vid = _require_id(version_id, "version_id")
        clean_lesson = None
        if lesson_id is not None:
            clean_lesson = _require_text(lesson_id, "lesson_id")
        self._insert(
            "strategy_versions",
            {
                "version_id": vid,
                "strategy_id": _require_text(strategy_id, "strategy_id"),
                "edge_validation_record_id": _require_text(
                    edge_validation_record_id, "edge_validation_record_id"
                ),
                "lesson_id": clean_lesson,
                "approver": _require_text(approver, "approver"),
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return vid

    def record_metric(self, *, metric_id: str, scope: str, payload: Mapping[str, Any]) -> str:
        mid = _require_id(metric_id, "metric_id")
        self._insert(
            "performance_metrics",
            {
                "metric_id": mid,
                "scope": _require_text(scope, "scope"),
                "payload_json": _json(dict(payload)),
                "created_at": _utc_now_text(),
            },
        )
        return mid

    # -- reads --
    def get(self, table: str, record_id: str) -> dict[str, Any]:
        """Return one row by primary key or raise KeyError."""
        pk = _primary_key(table)
        row = self.connection.execute(
            "SELECT * FROM %s WHERE %s = ?" % (table, pk), (str(record_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown {table} record: {record_id}")
        result: dict[str, Any] = {}
        for key in row.keys():
            result[key] = row[key]
        return result

    def chain_order(self) -> tuple[str, ...]:
        return CHAIN_ORDER

    def trace(self, trade_id: str) -> dict[str, Any]:
        """Walk the full chain for one trade in spec order, or raise."""
        token = _require_text(trade_id, "trade_id")
        trade = self._fetch("trades", "trade_id", token, "trade")
        position = self._fetch("positions", "position_id", str(trade["position_id"]), "position")
        order = self._fetch("orders", "order_id", str(position["order_id"]), "order")
        execution = self._fetch(
            "executions", "execution_id", str(order["execution_id"]), "execution"
        )
        risk = self._fetch(
            "risk_decisions", "risk_decision_id", str(execution["risk_decision_id"]), "risk decision"
        )
        decision = self._fetch(
            "decisions", "decision_id", str(risk["decision_id"]), "decision"
        )
        snapshot = self._fetch(
            "feature_snapshots", "snapshot_id", str(decision["market_snapshot_id"]), "market snapshot"
        )
        edge = self._fetch(
            "edge_validation_records",
            "record_id",
            str(decision["edge_validation_record_id"]),
            "edge validation record",
        )
        proposals = self._list("strategy_proposals", "decision_id", str(decision["decision_id"]))
        evidence = self._list("decision_evidence", "decision_id", str(decision["decision_id"]))
        analysis = self._fetch_one("trade_analysis", "trade_id", str(trade["trade_id"]), "trade analysis")
        lesson = self._latest("lessons", "analysis_id", str(analysis["analysis_id"]), "lesson")
        version = self._version_for_lesson_or_edge(
            str(lesson["lesson_id"]), str(edge["record_id"])
        )
        result: dict[str, Any] = {}
        result["market_snapshot"] = snapshot
        result["edge_validation_record"] = edge
        result["decision"] = decision
        result["strategy_proposals"] = proposals
        result["decision_evidence"] = evidence
        result["risk_decision"] = risk
        result["execution"] = execution
        result["order"] = order
        result["position"] = position
        result["trade"] = trade
        result["trade_analysis"] = analysis
        result["lesson"] = lesson
        result["strategy_version"] = version
        return result

    # -- internals --
    def _insert(self, table: str, values: dict[str, Any]) -> None:
        columns: list[str] = []
        for key in values:
            columns.append(key)
        placeholders: list[str] = []
        for _column in columns:
            placeholders.append("?")
        params: list[Any] = []
        for column in columns:
            params.append(values[column])
        sql = "INSERT INTO %s (%s) VALUES (%s)" % (
            table,
            ", ".join(columns),
            ", ".join(placeholders),
        )
        self.connection.execute(sql, params)
        self.connection.commit()

    def _fetch(self, table: str, pk: str, value: str, label: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM %s WHERE %s = ?" % (table, pk), (value,)
        ).fetchone()
        if row is None:
            raise TraceNotFoundError(f"trace found no {label} for id {value}")
        result: dict[str, Any] = {}
        for key in row.keys():
            result[key] = row[key]
        return result

    def _fetch_one(self, table: str, column: str, value: str, label: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM %s WHERE %s = ? ORDER BY rowid LIMIT 1" % (table, column), (value,)
        ).fetchone()
        if row is None:
            raise TraceNotFoundError(f"trace found no {label} for id {value}")
        result: dict[str, Any] = {}
        for key in row.keys():
            result[key] = row[key]
        return result

    def _latest(self, table: str, column: str, value: str, label: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM %s WHERE %s = ? ORDER BY rowid DESC LIMIT 1" % (table, column),
            (value,),
        ).fetchone()
        if row is None:
            raise TraceNotFoundError(f"trace found no {label} for id {value}")
        result: dict[str, Any] = {}
        for key in row.keys():
            result[key] = row[key]
        return result

    def _list(self, table: str, column: str, value: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM %s WHERE %s = ? ORDER BY rowid" % (table, column), (value,)
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            entry: dict[str, Any] = {}
            for key in row.keys():
                entry[key] = row[key]
            result.append(entry)
        return result

    def _version_for_lesson_or_edge(self, lesson_id: str, edge_record_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM strategy_versions WHERE lesson_id = ? ORDER BY rowid DESC LIMIT 1",
            (lesson_id,),
        ).fetchone()
        if row is None:
            row = self.connection.execute(
                "SELECT * FROM strategy_versions WHERE edge_validation_record_id = ? ORDER BY rowid DESC LIMIT 1",
                (edge_record_id,),
            ).fetchone()
        if row is None:
            raise TraceNotFoundError(
                "trace found no strategy version for lesson %s or edge %s" % (lesson_id, edge_record_id)
            )
        result: dict[str, Any] = {}
        for key in row.keys():
            result[key] = row[key]
        return result


_PK_BY_TABLE = {
    "raw_market_events": "event_id",
    "candles": "candle_id",
    "feature_snapshots": "snapshot_id",
    "breadth_snapshots": "breadth_id",
    "derivatives_snapshots": "derivatives_id",
    "universe_history": "history_id",
    "data_health": "health_id",
    "edge_validation_records": "record_id",
    "decisions": "decision_id",
    "decision_evidence": "evidence_id",
    "strategy_proposals": "proposal_id",
    "risk_decisions": "risk_decision_id",
    "executions": "execution_id",
    "orders": "order_id",
    "positions": "position_id",
    "trades": "trade_id",
    "trade_analysis": "analysis_id",
    "lessons": "lesson_id",
    "strategy_versions": "version_id",
    "performance_metrics": "metric_id",
}


def _primary_key(table: str) -> str:
    if table not in _PK_BY_TABLE:
        raise ValueError(f"unknown memory table: {table}")
    return _PK_BY_TABLE[table]


def _require_id(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a non-empty string")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must be a non-empty string")
    return text


def _require_text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a non-empty string")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must be a non-empty string")
    return text


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()
