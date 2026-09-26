"""Module 11 acceptance: isolation, stale HOLD, restart rebuild, failure table."""

from __future__ import annotations

import asyncio

import pytest

from hermes.context import ContextBuilder
from hermes.decision import decide
from monitoring.health import (
    HealthMonitor,
    evaluate_conditions,
    hold_for_stale_symbols,
    required_response,
)
from supervisor import Supervisor, default_worker_names


NOW_MS = 1_700_000_000_000


def fresh_snapshot(symbol="BTCUSDT"):
    return {
        "symbol": symbol,
        "event_time": "2024-01-01T00:00:00+00:00",
        "last_price": 100.0,
        "spread_bps": 2.0,
        "bid_depth": 5.0,
        "ask_depth": 5.0,
        "depth_within_bps": {25: {"bid_qty": 4.0, "ask_qty": 4.0}},
        "execution_quality": {"BUY": {"price_impact_rate": 0.0001, "status": "OK"}},
        "technical": {
            "1h": {
                "ema_fast": 101.0,
                "ema_slow": 100.0,
                "rsi": 55.0,
                "atr": 1.0,
                "vwap": 99.5,
                "bollinger_bandwidth": 0.04,
                "returns": 0.001,
            }
        },
        "multi_timeframe_alignment": {"state": "BULLISH", "confirmed_timeframes": 2},
        "trade_cvd": 10.0,
        "aggressive_buy_pct": 0.55,
        "large_trade_concentration": 0.1,
        "top_book_imbalance": 0.05,
        "depth_imbalance": 0.02,
        "trade_volume": 100.0,
    }


def good_health():
    return [
        {
            "component": "spot_websocket",
            "symbol": None,
            "status": "connected",
            "observed_time_ms": NOW_MS,
            "details": {},
        }
    ]


# -- acceptance 1: one worker dies, restarts, others unaffected --
def test_crashed_worker_restarts_while_sibling_continues():
    async def scenario():
        supervisor = Supervisor(backoff_initial=0.01, backoff_max=0.05)
        attempts: list[str] = []
        ticks: list[int] = []

        def flaky_factory():
            async def flaky():
                attempts.append("try")
                if len(attempts) == 1:
                    raise RuntimeError("simulated worker crash")
                while True:
                    await asyncio.sleep(0.05)

            return flaky()

        def steady_factory():
            async def steady():
                while True:
                    ticks.append(1)
                    await asyncio.sleep(0.05)

            return steady()

        supervisor.register_worker("flaky", flaky_factory)
        supervisor.register_worker("steady", steady_factory)
        await supervisor.run_once(timeout_seconds=1.5)
        return supervisor, attempts, ticks

    supervisor, attempts, ticks = asyncio.run(scenario())
    assert supervisor.total_restarts.get("flaky", 0) >= 1
    assert len(attempts) >= 2
    assert len(ticks) > 1
    kinds: list[str] = []
    for event in supervisor.events:
        kinds.append(event["event"])
    assert "crashed" in kinds


def test_backoff_grows_then_caps():
    supervisor = Supervisor(backoff_initial=1.0, backoff_factor=2.0, backoff_max=60.0)
    assert supervisor.backoff_for("w") == 0.0
    supervisor.crash_counts["w"] = 1
    assert supervisor.backoff_for("w") == pytest.approx(1.0)
    supervisor.crash_counts["w"] = 2
    assert supervisor.backoff_for("w") == pytest.approx(2.0)
    supervisor.crash_counts["w"] = 3
    assert supervisor.backoff_for("w") == pytest.approx(4.0)
    supervisor.crash_counts["w"] = 100
    assert supervisor.backoff_for("w") == pytest.approx(60.0)


# -- acceptance 2: stale data holds system-wide for the symbol --
def test_stale_data_holds_symbol_system_wide():
    builder = ContextBuilder(stale_after_seconds=30.0)
    stale = builder.build(
        symbol="BTCUSDT",
        feature_snapshot=fresh_snapshot(),
        event_time_ms=NOW_MS - 300_000,
        breadth=None,
        cross_exchange=None,
        health_entries=good_health(),
        now_ms=NOW_MS,
    )
    assert stale.valid is False
    decision, _record = decide("BTCUSDT", stale, [])
    assert decision.action == "HOLD"
    directive = hold_for_stale_symbols(["BTCUSDT"], "market data stale")
    assert directive.holds("BTCUSDT") is True
    assert directive.holds("ETHUSDT") is False
    response = required_response("market_data_stale", {"symbol": "BTCUSDT"})
    assert response["action"] == "HOLD"
    monitor = HealthMonitor()
    monitor.note_failure("market_observer", "stale feed")
    monitor.note_failure("market_observer", "stale feed")
    monitor.note_failure("market_observer", "stale feed")
    assert monitor.evaluate("market_observer", NOW_MS) == "DOWN"


# -- acceptance 3: restart rebuilds portfolio before any new decision --
def test_restart_rebuilds_before_decisions_resume():
    async def scenario():
        supervisor = Supervisor()
        assert supervisor.allow_decisions() is False
        known = {"BTCUSDT": {"position_qty": 2.0, "exposure_notional": 200.0}}
        calls: list[int] = []

        async def rebuild_hook():
            calls.append(1)
            merged: dict[str, object] = {}
            for symbol in known:
                merged[symbol] = dict(known[symbol])
            return merged

        supervisor.set_rebuild_hook(rebuild_hook)
        rebuilt = await supervisor.rebuild()
        assert supervisor.allow_decisions() is True
        assert rebuilt == known
        assert supervisor.portfolio_state == known
        assert len(calls) == 1
        return supervisor

    asyncio.run(scenario())


def test_failed_rebuild_keeps_gate_closed():
    async def scenario():
        supervisor = Supervisor()

        async def bad_hook():
            raise OSError("exchange unreachable")

        supervisor.set_rebuild_hook(bad_hook)
        with pytest.raises(OSError):
            await supervisor.rebuild()
        assert supervisor.allow_decisions() is False

    asyncio.run(scenario())


# -- failure table: every binding row --
def test_failure_table_binding_defaults():
    assert required_response("market_data_stale")["action"] == "HOLD"
    assert required_response("cross_exchange_contradiction")["action"] == "HOLD_OR_REDUCE_CONFIDENCE"
    assert required_response("risk_unavailable")["action"] == "NO_EXECUTION"
    assert required_response("n8n_unavailable")["action"] == "EXPIRE_PENDING"
    assert required_response("execution_unreconcilable")["action"] == "FREEZE_NEW_ENTRIES"
    assert required_response("persistence_failing")["action"] == "STOP_TRADING"
    assert required_response("hermes_unhealthy")["action"] == "RESTART_WORKER"
    assert required_response("daily_limit_reached")["action"] == "KILL_SWITCH"
    assert required_response("version_validation_fails")["action"] == "KEEP_EXISTING_VERSION"
    assert required_response("edge_reference_drift")["action"] == "HALT_STRATEGY"
    assert required_response("restart")["action"] == "REBUILD_THEN_RESUME"
    assert required_response("something_unknown")["action"] == "HOLD"
    batch = evaluate_conditions(["risk_unavailable", "n8n_unavailable"])
    assert len(batch) == 2
    assert batch[0]["action"] == "NO_EXECUTION"
    assert batch[1]["action"] == "EXPIRE_PENDING"


# -- health thresholds and hung-worker restart --
def test_health_thresholds_and_hung_restart():
    monitor = HealthMonitor(healthy_within_ms=1000, down_after_ms=3000, max_failures=3)
    monitor.heartbeat("risk_engine", NOW_MS)
    assert monitor.evaluate("risk_engine", NOW_MS) == "HEALTHY"
    assert monitor.evaluate("risk_engine", NOW_MS + 2000) == "DEGRADED"
    assert monitor.evaluate("risk_engine", NOW_MS + 5000) == "DOWN"
    supervisor = Supervisor()
    supervisor.register_worker("risk_engine", _never_factory)
    supervisor.health = monitor
    assert supervisor.restart_down_workers(NOW_MS + 5000) == ["risk_engine"]
    assert supervisor.restart_down_workers(NOW_MS) == []
    with pytest.raises(ValueError):
        HealthMonitor(healthy_within_ms=5000, down_after_ms=1000)


def _never_factory():
    async def never():
        await asyncio.sleep(3600)

    return never()


def test_kill_hook_independent_of_workers():
    supervisor = Supervisor()
    with pytest.raises(ValueError, match="no kill hook"):
        supervisor.trip_kill_switch("test")
    trips: list[str] = []
    supervisor.set_kill_hook(trips.append)
    supervisor.trip_kill_switch("daily loss")
    assert trips == ["daily loss"]


def test_default_workers_match_spec():
    assert default_worker_names() == [
        "market_observer",
        "context_builder",
        "strategy_engine",
        "decision_engine",
        "risk_engine",
        "n8n_client",
        "trade_monitor",
        "learning_worker",
    ]


def test_no_banned_constructs_in_module_11():
    import pathlib as _pathlib

    paths = [
        _pathlib.Path(__file__).resolve().parent.parent / "supervisor.py",
        _pathlib.Path(__file__).resolve().parent.parent / "monitoring" / "health.py",
    ]
    for path in paths:
        assert path.exists(), f"Module 11 file missing: {path}"
        text = path.read_text(encoding="utf-8")
        assert "__main__" not in text, str(path)
        assert "sorted(" not in text, str(path)
        assert "import llm" not in text.lower(), str(path)
        assert "from strategies" not in text.lower(), str(path)
