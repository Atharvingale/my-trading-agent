"""Supervisor worker coroutines over the live pipeline (integration).

Why queues, not direct calls: each of the eight supervised workers owns one
stage and backpressure is explicit (bounded queues), so a slow venue cannot
silently reorder decisions. Every stage calls the same pipeline methods the
synchronous path uses — no duplicated stage logic. Workers heartbeat every
loop; any crash restarts only that worker under the supervisor.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable

from execution.n8n_client import build_request
from runtime.pipeline import HermesPipeline


def make_queues(maxsize: int = 100) -> dict[str, asyncio.Queue]:
    """One bounded queue per handoff; full queues apply backpressure."""
    queues: dict[str, asyncio.Queue] = {}
    for name in ("snapshots", "contexts", "proposals", "decisions", "risks", "executions", "closed_trades"):
        queues[name] = asyncio.Queue(maxsize=maxsize)
    return queues


def make_workers(
    pipeline: HermesPipeline,
    queues: dict[str, asyncio.Queue],
    health: Any,
    stop: asyncio.Event,
    *,
    feed: Callable[[], list[dict[str, Any]]] | None = None,
    submit_fn: Callable[..., dict[str, Any]] | None = None,
    now_ms_fn: Callable[[], int] | None = None,
    exchange_truth_fn: Callable[[], tuple[list[dict[str, Any]], list[dict[str, Any]]]] | None = None,
) -> dict[str, Callable[[], Any]]:
    """Build the eight real worker factories sharing one pipeline."""

    def now_ms() -> int:
        if now_ms_fn is not None:
            return int(now_ms_fn())
        import time

        return int(time.time() * 1000)

    def moment() -> datetime:
        return datetime.fromtimestamp(float(now_ms()) / 1000.0, tz=timezone.utc)

    def market_worker():
        async def run() -> None:
            while stop.is_set() is False:
                health.heartbeat("market_observer", now_ms())
                items: list[dict[str, Any]] = []
                if feed is not None:
                    try:
                        items = feed()
                    except Exception:
                        items = []
                for item in items:
                    await queues["snapshots"].put(item)
                await asyncio.sleep(0.1)

        return run()

    def context_worker():
        async def run() -> None:
            while stop.is_set() is False:
                health.heartbeat("context_builder", now_ms())
                try:
                    item = await asyncio.wait_for(queues["snapshots"].get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                try:
                    emitted = pipeline.observer.refresh_once(
                        {str(item["symbol"]): item["snapshot"]},
                        {str(item["symbol"]): item.get("event_time_ms")},
                        breadth=item.get("breadth"),
                        health_entries=item.get("health_entries"),
                        now_ms=now_ms(),
                    )
                except Exception:
                    continue
                for context in emitted:
                    await queues["contexts"].put(context)

        return run()

    def strategy_worker():
        async def run() -> None:
            while stop.is_set() is False:
                health.heartbeat("strategy_engine", now_ms())
                try:
                    context = await asyncio.wait_for(queues["contexts"].get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                try:
                    proposals = pipeline.proposals_for(context)
                except Exception:
                    continue
                await queues["proposals"].put({"context": context, "proposals": proposals})

        return run()

    def decision_worker():
        async def run() -> None:
            while stop.is_set() is False:
                health.heartbeat("decision_engine", now_ms())
                try:
                    item = await asyncio.wait_for(queues["proposals"].get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                context = item["context"]
                proposals = item["proposals"]
                try:
                    decision, record = pipeline.decide_for(context, proposals, now_ms())
                except Exception:
                    continue
                pipeline.counters["decisions"] = pipeline.counters["decisions"] + 1
                if decision.action == "HOLD" or len(proposals) == 0:
                    pipeline.counters["holds"] = pipeline.counters["holds"] + 1
                    continue
                try:
                    pipeline.persist_pre_risk(context, proposals, record, decision)
                except Exception:
                    continue
                await queues["decisions"].put(
                    {"context": context, "decision": decision, "record": record}
                )

        return run()

    def risk_worker():
        async def run() -> None:
            while stop.is_set() is False:
                health.heartbeat("risk_engine", now_ms())
                try:
                    item = await asyncio.wait_for(queues["decisions"].get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                context = item["context"]
                decision = item["decision"]
                account = pipeline._account_state(str(context.symbol))
                try:
                    risk = pipeline.risk_engine.evaluate(
                        decision,
                        context,
                        equity=account["equity"],
                        peak_equity=account["peak"],
                        daily_realized_pnl=account["daily"],
                        open_notional=account["open_notional"],
                        symbol_exposure=account["symbol_exposure"],
                        open_positions=account["open_positions"],
                        now_ms=now_ms(),
                    )
                except Exception:
                    continue
                try:
                    pipeline.persist_risk_decision(risk, str(decision.decision_id))
                except Exception:
                    continue
                if risk.status != "APPROVED":
                    continue
                pipeline.counters["approved"] = pipeline.counters["approved"] + 1
                try:
                    request = build_request(
                        risk, symbol=str(context.symbol), side=decision.action, now=moment()
                    )
                except Exception:
                    continue
                await queues["risks"].put({"decision": decision, "risk": risk, "request": request})

        return run()

    def execution_worker():
        # Why injectable submit: outage injection and venue doubles replace
        # transport without touching pipeline logic; default is the real path.
        submit = submit_fn if submit_fn is not None else pipeline.submit

        async def run() -> None:
            while stop.is_set() is False:
                health.heartbeat("n8n_client", now_ms())
                try:
                    item = await asyncio.wait_for(queues["risks"].get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                try:
                    outcome = submit(item["request"], item["risk"], now_ms=now_ms())
                except Exception:
                    continue
                await queues["executions"].put(
                    {"request": item["request"], "risk": item["risk"], "outcome": outcome}
                )

        return run()

    def trade_monitor_worker():
        async def run() -> None:
            while stop.is_set() is False:
                health.heartbeat("trade_monitor", now_ms())
                try:
                    item = await asyncio.wait_for(queues["executions"].get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                try:
                    result = pipeline.on_venue_fills(item["request"], timestamp_ms=now_ms())
                except Exception:
                    continue
                if result.get("closed_trade_id") is not None:
                    await queues["closed_trades"].put(result["closed_trade_id"])
                if exchange_truth_fn is not None:
                    try:
                        orders, fills = exchange_truth_fn()
                        pipeline.tracker.reconcile_from_exchange(orders, fills)
                    except Exception:
                        continue
                await asyncio.sleep(0.1)

        return run()

    def learning_worker():
        async def run() -> None:
            while stop.is_set() is False:
                health.heartbeat("learning_worker", now_ms())
                try:
                    trade_id = await asyncio.wait_for(queues["closed_trades"].get(), timeout=0.3)
                except asyncio.TimeoutError:
                    continue
                try:
                    pipeline.learn_from_trade(str(trade_id))
                except Exception:
                    continue

        return run()

    workers: dict[str, Callable[[], Any]] = {}
    workers["market_observer"] = market_worker
    workers["context_builder"] = context_worker
    workers["strategy_engine"] = strategy_worker
    workers["decision_engine"] = decision_worker
    workers["risk_engine"] = risk_worker
    workers["n8n_client"] = execution_worker
    workers["trade_monitor"] = trade_monitor_worker
    workers["learning_worker"] = learning_worker
    return workers
