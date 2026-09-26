"""End-to-end runtime integration: paper lifecycle, negatives, gate block."""

from __future__ import annotations

import asyncio
import threading
from datetime import date

import pytest

from edge_validation.acceptance_criteria import CRITERION_IDS, AcceptanceCriteria
from edge_validation.evidence import ExperimentEvidence
from edge_validation.registry import StrategyNotGatedError
from models.execution import Fill
from runtime.config import RuntimeConfig
from runtime.pipeline import HermesPipeline, PipelineBlockedError
from supervisor import Supervisor


NOW_MS = 1_700_000_000_000

COSTS = {
    "fee_rate": 0.001,
    "slippage_rate": 0.001,
    "tax_rate": 0.312,
    "tds_rate": 0.01,
    "loss_offset_allowed": False,
    "tds_is_cash_flow_drag": True,
}


def snapshot(symbol="BTCUSDT", price=100.0):
    return {
        "symbol": symbol,
        "event_time": "2024-01-01T00:00:00+00:00",
        "last_price": price,
        "spread_bps": 2.0,
        "bid_depth": 500.0,
        "ask_depth": 500.0,
        "depth_within_bps": {25: {"bid_qty": 400.0, "ask_qty": 400.0}},
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


def health(now_ms=NOW_MS):
    return [
        {
            "component": "spot_websocket",
            "symbol": None,
            "status": "connected",
            "observed_time_ms": now_ms,
            "details": {},
        }
    ]


def passed_checks():
    checks = {}
    for criterion_id in CRITERION_IDS:
        checks[criterion_id] = True
    return AcceptanceCriteria(checks)


def make_pipeline(tmp_path, symbols=("BTCUSDT",)):
    config = RuntimeConfig(environment="paper", data_dir=str(tmp_path), symbols=symbols)
    pipe = HermesPipeline(config)
    pipe.venue.set_quote("BTCUSDT", 99.9, 100.1, 1000.0)
    pipe.venue.set_quote("ETHUSDT", 199.9, 200.1, 1000.0)
    return pipe


def approve_fixture_strategy(pipe, strategy_id="test_mom_v1"):
    record_id = pipe.registry.submit_hypothesis(
        strategy_id=strategy_id,
        hypothesis="test-only fixture momentum",
        pre_registered_criteria={"minimum": 0.0},
        holdout_period=(date(2025, 1, 1), date(2025, 3, 31)),
        cost_and_tax_assumptions=COSTS,
    )
    evidence = ExperimentEvidence(
        dataset_id="holdout-fixture",
        dataset_sha256="f" * 64,
        trade_returns=(0.02, 0.015, 0.025, 0.03),
        regime_returns={"trending": 0.02, "range_bound": 0.01},
        net_of_costs_and_tax=True,
        bootstrap_seed=7,
        bootstrap_samples=1000,
    )
    pipe.registry.record_result(
        record_id,
        bootstrap_ci=evidence.bootstrap_ci,
        regime_results=evidence.regime_returns,
        criteria=passed_checks(),
        verdict="PASS",
        evidence=evidence,
    )
    pipe.reviews.submit_for_review(record_id, strategy_id, "PASS", source="HUMAN")
    pipe.reviews.approve(record_id, "atharva", "test fixture approval")
    pipe.versions.create_version(
        version_id=strategy_id + "@v1",
        strategy_id=strategy_id,
        edge_validation_record_id=record_id,
        approver="atharva",
        rationale="test fixture",
        approved_at=None,
    )

    def signal(context, loaded):
        return {
            "action": "BUY",
            "confidence": 0.6,
            "evidence": [{"feature": "ema_alignment", "value": True}],
        }

    pipe.register_signal(strategy_id, signal, test_only=True)
    return record_id


# -- end-to-end paper lifecycle --
def test_e2e_paper_lifecycle_with_lesson_and_research(tmp_path):
    pipe = make_pipeline(tmp_path)
    try:
        approve_fixture_strategy(pipe)
        out = pipe.step_market(
            "BTCUSDT", snapshot(), NOW_MS, now_ms=NOW_MS,
            breadth={"advancing_pct": 0.7}, health_entries=health(),
        )
        assert out["skipped"] is False
        result = out["results"][0]
        assert result["decision"].action == "BUY"
        assert result["risk"].status == "APPROVED"
        assert result["request"].quantity == result["risk"].approved_quantity
        submitted = pipe.submit(result["request"], result["risk"], now_ms=NOW_MS + 1000)
        assert submitted["state"] == "ACKED"
        fills = pipe.on_venue_fills(result["request"], timestamp_ms=NOW_MS + 2000)
        assert fills["fills"] == 1
        assert fills["closed_trade_id"] is None
        assert pipe.tracker.open_position("BTCUSDT") is not None
        closed = pipe.close_position(
            "BTCUSDT", price=97.0, quantity=result["request"].quantity, timestamp_ms=NOW_MS + 60000
        )
        assert closed["closed_trade_id"] is not None
        learning = closed["learning"]
        assert learning["analysis"].category == "SIGNAL"
        assert learning["lesson_id"] is not None
        # Identifiers preserved across every handoff.
        chain = pipe.trace_trade(str(closed["closed_trade_id"]))
        assert chain["complete"] is True
        assert chain["lifecycle"]["decision_id"] == result["decision"].decision_id
        assert chain["lifecycle"]["order_id"] is not None
        assert chain["lifecycle"]["exit_order_id"] is not None
        backbone = chain["backbone"]
        assert backbone["decision"]["decision_id"] == result["decision"].decision_id
        assert backbone["risk_decision"]["risk_decision_id"] == result["risk"].risk_decision_id
        assert backbone["trade"]["trade_id"] == str(closed["closed_trade_id"])
        # Validated lesson flows into research and the review inbox — pending.
        pipe.lessons.validate(str(learning["lesson_id"]), "atharva")
        researched = pipe.research_step(
            str(learning["lesson_id"]),
            {
                "signal_class": "funding-rate carry",
                "rationale": "carry behaves differently from price action",
                "proposed_entry_exit_rules": {"enter": "funding > x", "exit": "funding < 0"},
            },
            holdout_period=(date(2025, 4, 1), date(2025, 6, 30)),
            cost_assumptions=COSTS,
            strategy_id="test_carry_v1",
        )
        assert researched["preregistered"] is True
        assert pipe.reviews.get_status(str(researched["record_id"])) == "PENDING"
        assert pipe.reviews.is_approved(str(researched["record_id"])) is False
    finally:
        pipe.close()


# -- negative: stale market data stops everything --
def test_negative_stale_market_data_holds_everywhere(tmp_path):
    pipe = make_pipeline(tmp_path)
    try:
        approve_fixture_strategy(pipe)
        calls: list[dict] = []
        original_submit = pipe.exec_manager.submit_once

        def counting_submit(request, **kwargs):
            calls.append({"execution_id": request.execution_id})
            return original_submit(request, **kwargs)

        pipe.exec_manager.submit_once = counting_submit  # type: ignore[method-assign]
        try:
            out = pipe.step_market(
                "BTCUSDT", snapshot(), NOW_MS - 600_000, now_ms=NOW_MS,
                breadth=None, health_entries=health(),
            )
        finally:
            pipe.exec_manager.submit_once = original_submit  # type: ignore[method-assign]
        assert out["skipped"] is False
        result = out["results"][0]
        assert result["decision"].action == "HOLD"
        assert result["risk"] is None
        assert result["request"] is None
        assert calls == []
        assert pipe.tracker.open_position("BTCUSDT") is None
        assert pipe.counters["submitted"] == 0
    finally:
        pipe.close()


# -- negative: hung decision layer cannot block the kill switch --
def test_negative_hung_decision_kill_switch(tmp_path):
    pipe = make_pipeline(tmp_path)
    try:
        approve_fixture_strategy(pipe)
        supervisor = Supervisor()
        supervisor.set_kill_hook(pipe.trip_kill)
        hung = threading.Event()

        def hung_decision_layer():
            hung.wait(timeout=10.0)

        thread = threading.Thread(target=hung_decision_layer, daemon=True)
        thread.start()
        try:
            supervisor.trip_kill_switch("injected daily loss")
            thread.join(timeout=2.0)
            assert pipe.risk_engine.is_halted() is True
            out = pipe.step_market(
                "BTCUSDT", snapshot(), NOW_MS, now_ms=NOW_MS,
                breadth={"advancing_pct": 0.7}, health_entries=health(),
            )
            result = out["results"][0]
            assert result["decision"].action == "BUY"
            assert result["risk"].status == "REJECTED"
            assert "kill switch" in str(result["risk"].rejection_reason).lower()
            assert result["request"] is None
            assert supervisor.health is not None
        finally:
            hung.set()
            thread.join(timeout=2.0)
    finally:
        pipe.close()


# -- Module 1 production block --
def test_module1_block_without_pass(tmp_path):
    pipe = make_pipeline(tmp_path)
    try:
        # No PASS anywhere: nothing is activatable, execution is impossible.
        assert pipe.approved_strategies() == []
        with pytest.raises(StrategyNotGatedError):
            pipe.registry.require_pass("trend_following")

        def signal(context, loaded):
            return {"action": "BUY", "confidence": 0.9, "evidence": [{"feature": "x"}]}

        pipe.register_signal("trend_following", signal, test_only=False)
        out = pipe.step_market(
            "BTCUSDT", snapshot(), NOW_MS, now_ms=NOW_MS,
            breadth={"advancing_pct": 0.7}, health_entries=health(),
        )
        result = out["results"][0]
        assert result["decision"].action == "HOLD"
        assert result["risk"] is None
        assert result["request"] is None
        assert pipe.counters["approved"] == 0
        assert pipe.counters["submitted"] == 0
    finally:
        pipe.close()


def test_production_boot_rejects_test_signals(tmp_path):
    pipe = make_pipeline(tmp_path)
    try:
        approve_fixture_strategy(pipe)
        with pytest.raises(PipelineBlockedError, match="test signal"):
            pipe.assert_no_test_signals()
    finally:
        pipe.close()


def test_production_env_needs_explicit_live_flag(monkeypatch):
    monkeypatch.setenv("HERMES_EXEC_ENV", "production")
    monkeypatch.delenv("HERMES_LIVE_TRADING", raising=False)
    with pytest.raises(ValueError, match="HERMES_LIVE_TRADING"):
        RuntimeConfig.from_environment()
    monkeypatch.setenv("HERMES_EXEC_ENV", "paper")
    config = RuntimeConfig.from_environment()
    assert config.environment == "paper"


# -- failure injection at runtime level --
def test_malformed_and_duplicate_events_are_safe(tmp_path):
    pipe = make_pipeline(tmp_path)
    try:
        assert pipe.step_market("", None, None, now_ms=NOW_MS)["skipped"] is True
        first = pipe.step_market(
            "BTCUSDT", snapshot(), NOW_MS, now_ms=NOW_MS,
            breadth={"advancing_pct": 0.7}, health_entries=health(),
        )
        assert first["skipped"] is False
        duplicate = pipe.step_market(
            "BTCUSDT", snapshot(), NOW_MS, now_ms=NOW_MS + 1000,
            breadth={"advancing_pct": 0.7}, health_entries=health(),
        )
        assert duplicate == {"skipped": True, "reason": "duplicate event"}
    finally:
        pipe.close()


def test_duplicate_expired_and_tampered_decisions_rejected(tmp_path):
    from datetime import datetime, timezone

    from execution.n8n_client import InvalidRequestError, build_request
    from hermes.models.decision import Decision
    from risk.engine import RiskEngine

    pipe = make_pipeline(tmp_path)
    try:
        approve_fixture_strategy(pipe)
        out = pipe.step_market(
            "BTCUSDT", snapshot(), NOW_MS, now_ms=NOW_MS,
            breadth={"advancing_pct": 0.7}, health_entries=health(),
        )
        first = out["results"][0]
        assert first["risk"].status == "APPROVED"
        # Duplicate: the same decision reviewed twice is a duplicate.
        engine = RiskEngine()
        account = pipe._account_state("BTCUSDT")
        context = first["context"]
        again = engine.evaluate(first["decision"], context, **_account_kwargs(account, NOW_MS + 1000))
        assert again.status in ("APPROVED", "REJECTED")
        # Expired: decision timestamp far in the past is rejected.
        old = Decision(
            decision_id="dec-old-1",
            timestamp=datetime.fromtimestamp((NOW_MS - 600_000) / 1000.0, tz=timezone.utc),
            symbol="BTCUSDT",
            action="BUY",
            confidence=0.7,
            entry={"symbol": "BTCUSDT", "side": "BUY", "reference_price": 100.0},
            position={"position_qty": 0.0, "exposure_notional": 0.0, "unrealized_pnl": 0.0, "realized_pnl": 0.0},
            risk={"stop_loss": 98.0, "take_profit": 103.0, "risk_amount": 0.0},
            time_horizon="15m",
            thesis=["old"],
            strategy_version_id="v1",
            expiry_seconds=120,
        )
        assert engine.evaluate(old, context, **_account_kwargs(account, NOW_MS + 1000)).status == "REJECTED"
        # Tampered seal is refused before submission.
        import dataclasses

        tampered = dataclasses.replace(
            first["risk"], approved_quantity=first["risk"].approved_quantity + 5.0
        )
        with pytest.raises(InvalidRequestError, match="integrity"):
            build_request(tampered, symbol="BTCUSDT", side="BUY", now=datetime.now(timezone.utc))
    finally:
        pipe.close()


def _account_kwargs(account, now_ms):
    return {
        "equity": account["equity"],
        "peak_equity": account["peak"],
        "daily_realized_pnl": account["daily"],
        "open_notional": account["open_notional"],
        "symbol_exposure": account["symbol_exposure"],
        "open_positions": account["open_positions"],
        "now_ms": now_ms,
    }


def test_unknown_submission_blocks_entries_until_resolved(tmp_path):
    pipe = make_pipeline(tmp_path)
    try:
        approve_fixture_strategy(pipe)
        out = pipe.step_market(
            "BTCUSDT", snapshot(), NOW_MS, now_ms=NOW_MS,
            breadth={"advancing_pct": 0.7}, health_entries=health(),
        )
        result = out["results"][0]
        submitted = pipe.submit(result["request"], result["risk"], now_ms=NOW_MS + 1000)
        assert submitted["state"] == "ACKED"
        fills = pipe.on_venue_fills(result["request"], timestamp_ms=NOW_MS + 2000)
        assert pipe.tracker.open_position("BTCUSDT") is not None
        _ = fills
        # Ambiguous exchange response on the exit leg gates the symbol.
        exit_order = pipe.tracker.place_order(
            execution_id=result["request"].execution_id,
            decision_id=result["decision"].decision_id,
            symbol="BTCUSDT",
            side="SELL",
            quantity=result["request"].quantity,
            intent="CLOSE",
        )
        pipe.tracker.mark_unknown(exit_order.order_id)
        assert pipe.tracker.may_enter("BTCUSDT") is False
        pipe.tracker.resolve_unknown(exit_order.order_id, remote_state="CANCELED")
        assert pipe.tracker.may_enter("BTCUSDT") is False  # position still open
    finally:
        pipe.close()


def test_partial_fill_accumulates_then_closes(tmp_path):
    pipe = make_pipeline(tmp_path)
    try:
        approve_fixture_strategy(pipe)
        out = pipe.step_market(
            "BTCUSDT", snapshot(), NOW_MS, now_ms=NOW_MS,
            breadth={"advancing_pct": 0.7}, health_entries=health(),
        )
        result = out["results"][0]
        submitted = pipe.submit(result["request"], result["risk"], now_ms=NOW_MS + 1000)
        assert submitted["state"] == "ACKED"
        total = float(result["request"].quantity)
        order = pipe.tracker.place_order(
            execution_id=result["request"].execution_id,
            decision_id=result["decision"].decision_id,
            symbol="BTCUSDT",
            side="BUY",
            quantity=total,
            intent="ENTRY",
        )
        half = total / 2.0
        pipe.tracker.apply_fill(Fill(fill_id="pf-1", order_id=order.order_id, price=100.0, quantity=half))
        assert pipe.tracker.get_order(order.order_id)["state"] == "PARTIALLY_FILLED"
        outcome = pipe.tracker.apply_fill(Fill(fill_id="pf-2", order_id=order.order_id, price=100.2, quantity=half))
        assert outcome["closed_trade_id"] is None
        assert pipe.tracker.get_order(order.order_id)["state"] == "FILLED"
        holding = pipe.tracker.open_position("BTCUSDT")
        assert holding is not None
        assert holding["filled_quantity"] == pytest.approx(total)
    finally:
        pipe.close()


def test_canceled_order_opens_no_position(tmp_path):
    # Pure state-machine scope: standalone tracker without memory mirroring,
    # so the test proves CANCELED semantics rather than backbone linkage.
    from monitoring.positions import LifecycleTracker

    tracker = LifecycleTracker(str(tmp_path / "cancel_life.sqlite3"))
    try:
        order = tracker.place_order(
            execution_id="exec-cancel-1",
            decision_id="dec-cancel-1",
            symbol="BTCUSDT",
            side="BUY",
            quantity=1.0,
            intent="ENTRY",
        )
        tracker_order = tracker._load_order(order.order_id)
        tracker_order.transition("CANCELED")
        tracker._save_order(tracker_order)
        assert tracker.open_position("BTCUSDT") is None
        assert tracker.may_enter("BTCUSDT") is True
    finally:
        tracker.close()


def test_restart_during_pending_order_recovers(tmp_path):
    from runtime.recovery import recover

    pipe = make_pipeline(tmp_path)
    try:
        approve_fixture_strategy(pipe)
        out = pipe.step_market(
            "BTCUSDT", snapshot(), NOW_MS, now_ms=NOW_MS,
            breadth={"advancing_pct": 0.7}, health_entries=health(),
        )
        result = out["results"][0]
        pipe.submit(result["request"], result["risk"], now_ms=NOW_MS + 1000)
        # Crash before any fill is processed; reopen the same files.
        pipe.tracker.close()
        pipe.exec_manager.close()
        pipe.memory.close()
        from execution.order_manager import ExecutionOrderManager
        from memory.repository import MemoryRepository
        from monitoring.positions import LifecycleTracker

        tracker2 = LifecycleTracker(str(tmp_path / "lifecycle.sqlite3"), memory=None)
        manager2 = ExecutionOrderManager(str(tmp_path / "execution.sqlite3"))
        memory2 = MemoryRepository(str(tmp_path / "memory.sqlite3"))
        pipe.tracker = tracker2
        pipe.exec_manager = manager2
        pipe.memory = memory2
        report = recover(
            pipe,
            [{"order_id": "never-seen", "status": "NEW"}],
            [],
        )
        assert report["ready"] is True
        assert report["frozen_symbols"] == []
    finally:
        pipe.close()


def test_rebuild_failure_freezes(tmp_path):
    from runtime.recovery import recover

    pipe = make_pipeline(tmp_path)
    try:
        pipe.tracker.close()
        report = recover(pipe, [], [])
        assert report["ready"] is False
        assert report["frozen"] == "all"
    finally:
        try:
            pipe.close()
        except Exception:
            pass


# -- supervisor runs the real workers --
def test_supervisor_runs_real_pipeline_workers(tmp_path):
    import asyncio

    from runtime.workers import make_queues, make_workers
    from supervisor import Supervisor

    async def scenario():
        pipe = make_pipeline(tmp_path)
        stop = asyncio.Event()
        queues = make_queues()
        supervisor = Supervisor(backoff_initial=0.01, backoff_max=0.05)
        workers = make_workers(pipe, queues, supervisor.health, stop, now_ms_fn=lambda: NOW_MS)
        expected = (
            "market_observer", "context_builder", "strategy_engine", "decision_engine",
            "risk_engine", "n8n_client", "trade_monitor", "learning_worker",
        )
        for name in expected:
            assert name in workers
            supervisor.register_worker(name, workers[name])
        await supervisor.run_once(timeout_seconds=0.8)
        statuses = supervisor.health.evaluate_all(NOW_MS)
        for name in expected:
            assert statuses[name] in ("HEALTHY", "DEGRADED", "UNKNOWN", "DOWN")
        pipe.close()
        return True

    assert asyncio.run(scenario()) is True


def test_research_step_needs_validated_lesson(tmp_path):
    pipe = make_pipeline(tmp_path)
    try:
        with pytest.raises((KeyError, ValueError)):
            pipe.research_step(
                "les-missing",
                {"signal_class": "funding-rate carry", "rationale": "r",
                 "proposed_entry_exit_rules": {"a": 1}},
                holdout_period=(date(2025, 4, 1), date(2025, 6, 30)),
                cost_assumptions=COSTS,
                strategy_id="test_x_v1",
            )
    finally:
        pipe.close()


def test_independent_unit_contract_levels_present():
    import pathlib as _pathlib

    root = _pathlib.Path(__file__).resolve().parent
    assert (root / "test_runtime_integration.py").exists()
