"""Asyncio task supervisor for 24/7 runtime (Module 11).

Why asyncio supervision: the market-data collector already manages background
tasks this way, so one mechanism covers every worker with no new dependency.
Each worker runs as an isolated task from a fresh factory per restart — one
worker's crash restarts only that worker with backoff while the rest continue.
No new decision is allowed until portfolio state is rebuilt from exchange
truth plus durable local records after any (re)start.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, List

from monitoring.health import HealthMonitor


# Restart backoff defaults: first retry fast, then exponential, capped so a
# flapping worker cannot hot-loop the process.
BACKOFF_INITIAL_SECONDS = 1.0
BACKOFF_FACTOR = 2.0
BACKOFF_MAX_SECONDS = 60.0


class Supervisor:
    """Isolated asyncio supervision with rebuild-before-decisions gating."""

    def __init__(
        self,
        *,
        backoff_initial: float = BACKOFF_INITIAL_SECONDS,
        backoff_factor: float = BACKOFF_FACTOR,
        backoff_max: float = BACKOFF_MAX_SECONDS,
        health_monitor: HealthMonitor | None = None,
    ) -> None:
        if backoff_initial <= 0 or backoff_factor < 1.0 or backoff_max <= 0:
            raise ValueError("backoff parameters must be positive with factor >= 1")
        self.backoff_initial = float(backoff_initial)
        self.backoff_factor = float(backoff_factor)
        self.backoff_max = float(backoff_max)
        self.health = health_monitor if health_monitor is not None else HealthMonitor()
        self.factories: Dict[str, Callable[[], Awaitable[None]]] = {}
        self.tasks: Dict[str, asyncio.Task[None]] = {}
        self.crash_counts: Dict[str, int] = {}
        self.total_restarts: Dict[str, int] = {}
        self.events: List[Dict[str, Any]] = []
        self._stop = False
        self._ready = False
        self._rebuild_hook: Callable[[], Awaitable[Dict[str, Any]]] | None = None
        self._kill_hook: Callable[[str], None] | None = None
        self.portfolio_state: Dict[str, Any] = {}

    # -- configuration --
    def register_worker(self, name: str, factory: Callable[[], Awaitable[None]]) -> None:
        """Register one supervised worker; factories must build fresh coroutines."""
        token = str(name).strip()
        if not token:
            raise ValueError("worker name must be non-empty")
        if token in self.factories:
            raise ValueError("worker already registered: %s" % token)
        self.factories[token] = factory
        self.crash_counts[token] = 0
        self.total_restarts[token] = 0

    def set_rebuild_hook(self, hook: Callable[[], Awaitable[Dict[str, Any]]]) -> None:
        """Hook rebuilding portfolio state from exchange plus durable records."""
        self._rebuild_hook = hook

    def set_kill_hook(self, hook: Callable[[str], None]) -> None:
        """Independent halt path, callable even when workers malfunction."""
        self._kill_hook = hook

    def allow_decisions(self) -> bool:
        """False until a rebuild completes after any (re)start."""
        return self._ready

    def trip_kill_switch(self, reason: str) -> None:
        if self._kill_hook is None:
            raise ValueError("no kill hook registered")
        self._kill_hook(str(reason))

    def request_stop(self) -> None:
        self._stop = True

    def backoff_for(self, worker: str) -> float:
        """Current restart delay for a worker from its consecutive crashes."""
        crashes = int(self.crash_counts.get(str(worker), 0))
        if crashes <= 0:
            return 0.0
        delay = self.backoff_initial
        step = 1
        while step < crashes:
            delay = delay * self.backoff_factor
            step = step + 1
        if delay > self.backoff_max:
            return self.backoff_max
        return delay

    # -- runtime --
    async def rebuild(self) -> Dict[str, Any]:
        """Run the rebuild hook and open the decision gate only on success."""
        self._ready = False
        if self._rebuild_hook is None:
            self.portfolio_state = {}
            self._ready = True
            return {}
        state = await self._rebuild_hook()
        if not isinstance(state, dict):
            raise ValueError("rebuild hook must return a state dict")
        rebuilt: Dict[str, Any] = {}
        for key in state:
            rebuilt[key] = state[key]
        self.portfolio_state = rebuilt
        self._ready = True
        self._log("supervisor", "rebuilt", "portfolio state rebuilt before resume")
        return rebuilt

    async def run(self) -> None:
        """Supervise until request_stop; isolates and restarts crashed workers."""
        self._stop = False
        await self.rebuild()
        for name in self.factories:
            self._launch(name)
        while self._stop is False:
            await asyncio.sleep(0.05)
            for name in list(self.tasks.keys()):
                task = self.tasks[name]
                if task.done():
                    await self._handle_finished(name, task)
            if len(self.tasks) == 0 and len(self.factories) > 0:
                break
        await self._shutdown()

    async def run_once(self, timeout_seconds: float = 5.0) -> None:
        """Bounded supervision window for tests and dry runs."""
        try:
            await asyncio.wait_for(self.run(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            self.request_stop()
            await self._shutdown()

    def restart_down_workers(self, now_ms: int) -> List[str]:
        """Restart workers the health monitor reports DOWN (hung workers)."""
        restarted: List[str] = []
        for name in self.health.down_workers(now_ms):
            if name in self.factories:
                restarted.append(name)
        return restarted

    async def _handle_finished(self, name: str, task: asyncio.Task[None]) -> None:
        del self.tasks[name]
        if self._stop:
            return
        try:
            task.result()
        except asyncio.CancelledError:
            self._log(name, "cancelled", "worker cancelled during shutdown")
            return
        except Exception as exc:
            crashes = int(self.crash_counts.get(name, 0)) + 1
            self.crash_counts[name] = crashes
            self.total_restarts[name] = int(self.total_restarts.get(name, 0)) + 1
            self.health.note_restart(name)
            delay = self.backoff_for(name)
            self._log(name, "crashed", "%s; restart in %.1fs" % (exc, delay))
            if delay > 0:
                await asyncio.sleep(delay)
            if self._stop is False:
                self._launch(name)
            return
        self.crash_counts[name] = 0
        self._log(name, "exited", "worker finished cleanly; not relaunched")

    def _launch(self, name: str) -> None:
        factory = self.factories[name]
        self.tasks[name] = asyncio.ensure_future(factory())

    async def _shutdown(self) -> None:
        for name in list(self.tasks.keys()):
            task = self.tasks[name]
            if task.done() is False:
                task.cancel()
        for name in list(self.tasks.keys()):
            try:
                await self.tasks[name]
            except (asyncio.CancelledError, Exception):
                pass
        self.tasks = {}

    def _log(self, worker: str, event: str, detail: str) -> None:
        entry: Dict[str, Any] = {}
        entry["worker"] = worker
        entry["event"] = event
        entry["detail"] = detail
        entry["at"] = time.time()
        self.events.append(entry)


def default_worker_names() -> List[str]:
    """The eight supervised workers from the Module 11 spec, in fixed order."""
    names: List[str] = []
    for name in (
        "market_observer",
        "context_builder",
        "strategy_engine",
        "decision_engine",
        "risk_engine",
        "n8n_client",
        "trade_monitor",
        "learning_worker",
    ):
        names.append(name)
    return names
