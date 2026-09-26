"""Health probes and binding failure responses (Module 11).

Why explicit thresholds: a worker is HEALTHY, DEGRADED, or DOWN purely from
heartbeat age and consecutive failures — no judgment calls. The failure table
maps each binding condition to its required response as a pure function, so
tests can prove every row without running the live system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


WORKERS = (
    "market_observer",
    "context_builder",
    "strategy_engine",
    "decision_engine",
    "risk_engine",
    "n8n_client",
    "trade_monitor",
    "learning_worker",
)

STATUSES = ("HEALTHY", "DEGRADED", "DOWN", "UNKNOWN")


@dataclass
class WorkerHealth:
    name: str
    status: str = "UNKNOWN"
    last_heartbeat_ms: int | None = None
    consecutive_failures: int = 0
    detail: str = ""
    restarts: int = 0


class HealthMonitor:
    """Heartbeat ledger plus failure-table evaluation for one process."""

    def __init__(
        self,
        *,
        healthy_within_ms: int = 10_000,
        down_after_ms: int = 30_000,
        max_failures: int = 3,
    ) -> None:
        if healthy_within_ms <= 0 or down_after_ms <= healthy_within_ms:
            raise ValueError("thresholds must satisfy 0 < healthy_within < down_after")
        if max_failures < 1:
            raise ValueError("max_failures must be at least 1")
        self.healthy_within_ms = int(healthy_within_ms)
        self.down_after_ms = int(down_after_ms)
        self.max_failures = int(max_failures)
        self.workers: dict[str, WorkerHealth] = {}
        for name in WORKERS:
            self.workers[name] = WorkerHealth(name=name)
        self.extra: dict[str, WorkerHealth] = {}

    def heartbeat(self, worker: str, now_ms: int, detail: str = "") -> None:
        """Record one healthy pulse; resets the failure streak."""
        record = self._record(str(worker))
        record.last_heartbeat_ms = int(now_ms)
        record.consecutive_failures = 0
        record.detail = str(detail)

    def note_failure(self, worker: str, detail: str = "") -> None:
        """Record one failure; status degrades only through evaluation."""
        record = self._record(str(worker))
        record.consecutive_failures = record.consecutive_failures + 1
        if str(detail).strip():
            record.detail = str(detail)

    def note_restart(self, worker: str) -> None:
        record = self._record(str(worker))
        record.restarts = record.restarts + 1
        record.consecutive_failures = 0
        record.last_heartbeat_ms = None

    def evaluate(self, worker: str, now_ms: int) -> str:
        """Fold heartbeats and failures into one status (fail-closed)."""
        record = self._record(str(worker))
        if record.consecutive_failures >= self.max_failures:
            record.status = "DOWN"
            return record.status
        if record.last_heartbeat_ms is None:
            if record.consecutive_failures > 0:
                record.status = "DEGRADED"
            else:
                record.status = "UNKNOWN"
            return record.status
        age = int(now_ms) - int(record.last_heartbeat_ms)
        if age < 0:
            record.status = "DEGRADED"
            return record.status
        if age <= self.healthy_within_ms:
            if record.consecutive_failures > 0:
                record.status = "DEGRADED"
            else:
                record.status = "HEALTHY"
            return record.status
        if age <= self.down_after_ms:
            record.status = "DEGRADED"
            return record.status
        record.status = "DOWN"
        return record.status

    def evaluate_all(self, now_ms: int) -> dict[str, str]:
        result: dict[str, str] = {}
        for name in self.workers:
            result[name] = self.evaluate(name, now_ms)
        for name in self.extra:
            result[name] = self.evaluate(name, now_ms)
        return result

    def down_workers(self, now_ms: int) -> list[str]:
        down: list[str] = []
        statuses = self.evaluate_all(now_ms)
        for name in statuses:
            if statuses[name] == "DOWN":
                down.append(name)
        return down

    def snapshot(self, now_ms: int) -> dict[str, Any]:
        states = self.evaluate_all(now_ms)
        workers: dict[str, Any] = {}
        for name in self.workers:
            record = self.workers[name]
            workers[name] = {
                "status": states[name],
                "last_heartbeat_ms": record.last_heartbeat_ms,
                "consecutive_failures": record.consecutive_failures,
                "restarts": record.restarts,
                "detail": record.detail,
            }
        for name in self.extra:
            record = self.extra[name]
            workers[name] = {
                "status": states[name],
                "last_heartbeat_ms": record.last_heartbeat_ms,
                "consecutive_failures": record.consecutive_failures,
                "restarts": record.restarts,
                "detail": record.detail,
            }
        return {"workers": workers, "down": self.down_workers(now_ms)}

    def _record(self, worker: str) -> WorkerHealth:
        if worker in self.workers:
            return self.workers[worker]
        if worker not in self.extra:
            self.extra[worker] = WorkerHealth(name=worker)
        return self.extra[worker]


# -- binding failure table (spec rows, pure functions) --
def required_response(condition: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map one condition to its required response; unknown fails closed."""
    token = str(condition).strip().lower()
    detail: dict[str, Any] = {}
    if context is not None:
        for key in context:
            detail[key] = context[key]
    if token == "market_data_stale":
        return {"action": "HOLD", "scope": detail.get("symbol", "all"), "reason": "stale or incomplete market data"}
    if token == "cross_exchange_contradiction":
        return {"action": "HOLD_OR_REDUCE_CONFIDENCE", "scope": detail.get("symbol", "all"),
                "reason": "contradictory venues beyond tolerance"}
    if token == "risk_unavailable":
        return {"action": "NO_EXECUTION", "scope": "all", "reason": "risk service unreachable"}
    if token == "n8n_unavailable":
        return {"action": "EXPIRE_PENDING", "scope": "all", "reason": "expire requests, never queue indefinitely"}
    if token == "execution_unreconcilable":
        return {"action": "FREEZE_NEW_ENTRIES", "scope": detail.get("symbol", "all"),
                "reason": "reconcile against exchange truth first"}
    if token == "persistence_failing":
        return {"action": "STOP_TRADING", "scope": "all", "reason": "no audit trail, no trading"}
    if token == "hermes_unhealthy":
        return {"action": "RESTART_WORKER", "scope": "hermes", "reason": "restart and verify from durable storage"}
    if token == "daily_limit_reached":
        return {"action": "KILL_SWITCH", "scope": "all", "reason": "daily loss or drawdown limit reached"}
    if token == "version_validation_fails":
        return {"action": "KEEP_EXISTING_VERSION", "scope": detail.get("strategy_id", "all"),
                "reason": "new version failed validation"}
    if token == "edge_reference_drift":
        return {"action": "HALT_STRATEGY", "scope": detail.get("strategy_id", "all"),
                "reason": "missing or drifted edge_validation reference"}
    if token == "restart":
        return {"action": "REBUILD_THEN_RESUME", "scope": "all",
                "reason": "rebuild portfolio from exchange plus durable records first"}
    return {"action": "HOLD", "scope": "all", "reason": "unknown condition fails closed"}


def evaluate_conditions(conditions: list[str]) -> list[dict[str, Any]]:
    """Evaluate a batch of active conditions in caller order (no reordering)."""
    responses: list[dict[str, Any]] = []
    for condition in conditions:
        responses.append(required_response(condition))
    return responses


@dataclass
class HoldDirective:
    """System-wide HOLD instruction for affected symbols."""

    symbols: list[str] = field(default_factory=list)
    reason: str = ""

    def holds(self, symbol: str) -> bool:
        token = str(symbol).strip().upper()
        for held in self.symbols:
            if str(held).strip().upper() == token:
                return True
        return False


def hold_for_stale_symbols(symbols: list[str], reason: str) -> HoldDirective:
    """Build the HOLD directive covering exactly the stale symbols."""
    held: list[str] = []
    for symbol in symbols:
        token = str(symbol).strip().upper()
        if token and token not in held:
            held.append(token)
    return HoldDirective(symbols=held, reason=str(reason))
