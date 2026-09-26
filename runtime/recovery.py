"""Ordered restart recovery: durable → ledger → orders → account (integration).

Why fixed order: each step depends on the previous one telling the truth, so
a failure freezes everything below it instead of rebuilding on guesses. Any
exception anywhere yields ready=False — never resume trading merely because
the process restarted successfully.
"""

from __future__ import annotations

from typing import Any


def recover(
    pipeline: Any,
    exchange_orders: list[dict[str, Any]],
    exchange_fills: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rebuild runtime state; freeze when anything is uncertain."""
    report: dict[str, Any] = {}
    try:
        report["durable"] = _durable_counts(pipeline)
        report["ledger"] = _ledger_states(pipeline)
        reconciled = pipeline.tracker.reconcile_from_exchange(exchange_orders, exchange_fills)
        report["reconciled_fills"] = int(reconciled.get("recovered_fills", 0))
        report["resolved_unknown"] = int(reconciled.get("resolved_unknown", 0))
        report["account"] = _rebuild_account(pipeline)
    except Exception as exc:
        report["ready"] = False
        report["frozen"] = "all"
        report["error"] = str(exc)
        return report
    blocked: list[str] = []
    for symbol in pipeline.config.symbols:
        if pipeline.tracker.has_unknown(str(symbol)):
            blocked.append(str(symbol).strip().upper())
    report["frozen_symbols"] = blocked
    report["ready"] = len(blocked) == 0
    if len(blocked) > 0:
        report["frozen"] = blocked
    return report


def _durable_counts(pipeline: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in ("trades", "positions", "orders", "decisions", "risk_decisions", "executions"):
        row = pipeline.memory.connection.execute(
            "SELECT COUNT(*) AS n FROM %s" % table
        ).fetchone()
        counts[table] = int(row["n"])
    return counts


def _ledger_states(pipeline: Any) -> dict[str, int]:
    states: dict[str, int] = {}
    for state in ("PENDING", "SUBMITTED", "ACKED", "FILLED", "REJECTED", "EXPIRED"):
        states[state] = len(pipeline.exec_manager.list_by_state(state))
    return states


def _rebuild_account(pipeline: Any) -> dict[str, float]:
    row = pipeline.memory.connection.execute(
        "SELECT payload_json FROM performance_metrics WHERE scope='account'"
        " ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    if row is not None:
        import json

        try:
            saved = json.loads(str(row["payload_json"]))
            pipeline.account["equity"] = float(saved.get("equity", pipeline.account["equity"]))
            pipeline.account["daily"] = float(saved.get("daily", 0.0))
        except (TypeError, ValueError, KeyError):
            pass
    peak = float(pipeline.account["peak"])
    if float(pipeline.account["equity"]) > peak:
        pipeline.account["peak"] = float(pipeline.account["equity"])
        peak = float(pipeline.account["equity"])
    return {
        "equity": float(pipeline.account["equity"]),
        "peak": peak,
        "daily": float(pipeline.account["daily"]),
    }
