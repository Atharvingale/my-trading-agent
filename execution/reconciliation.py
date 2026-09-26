"""Local-vs-exchange reconciliation (Module 7).

Why a pure function: reconciliation compares two snapshots — locally tracked
orders and exchange truth — without network calls, so tests can prove every
divergence path. Any unreconcilable state recommends freezing new entries
rather than trading blind.
"""

from __future__ import annotations

from typing import Any


def reconcile(
    local_orders: list[dict[str, Any]], exchange_orders: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare tracked orders against exchange truth.

    Match key is order_id (falling back to execution_id when the exchange
    echoes it). Returns matched, missing_on_exchange, unknown_locally,
    mismatched lists plus an action: "ok" or "freeze_new_entries".
    """
    by_local: dict[str, dict[str, Any]] = {}
    for entry in local_orders:
        key = _local_key(entry)
        if key:
            by_local[key] = entry
    by_exchange: dict[str, dict[str, Any]] = {}
    for entry in exchange_orders:
        key = _exchange_key(entry)
        if key:
            by_exchange[key] = entry
    matched: list[dict[str, Any]] = []
    missing_on_exchange: list[dict[str, Any]] = []
    mismatched: list[dict[str, Any]] = []
    for key in by_local:
        local = by_local[key]
        if key not in by_exchange:
            missing_on_exchange.append(local)
            continue
        remote = by_exchange[key]
        problems: list[str] = []
        if _quantity(local) is not None and _quantity(remote) is not None:
            if abs(float(_quantity(local)) - float(_quantity(remote))) > 1e-9:
                problems.append("quantity differs: local %s vs exchange %s" % (
                    _quantity(local), _quantity(remote)))
        if _status(local) is not None and _status(remote) is not None:
            if str(_status(local)).upper() != str(_status(remote)).upper():
                problems.append("status differs: local %s vs exchange %s" % (
                    _status(local), _status(remote)))
        if len(problems) == 0:
            matched.append(local)
        else:
            detail: dict[str, Any] = {}
            detail["local"] = local
            detail["exchange"] = remote
            detail["problems"] = problems
            mismatched.append(detail)
    unknown_locally: list[dict[str, Any]] = []
    for key in by_exchange:
        if key not in by_local:
            unknown_locally.append(by_exchange[key])
    action = "ok"
    if len(unknown_locally) > 0 or len(mismatched) > 0:
        action = "freeze_new_entries"
    report: dict[str, Any] = {}
    report["matched"] = matched
    report["missing_on_exchange"] = missing_on_exchange
    report["unknown_locally"] = unknown_locally
    report["mismatched"] = mismatched
    report["action"] = action
    return report


def _local_key(entry: dict[str, Any]) -> str | None:
    for field in ("order_id", "execution_id", "idempotency_key"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _exchange_key(entry: dict[str, Any]) -> str | None:
    for field in ("order_id", "client_order_id", "execution_id", "idempotency_key"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _quantity(entry: dict[str, Any]) -> float | None:
    for field in ("quantity", "origQty", "executedQty"):
        if field in entry:
            try:
                value = entry[field]
                if isinstance(value, bool):
                    continue
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _status(entry: dict[str, Any]) -> str | None:
    for field in ("status", "state"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
