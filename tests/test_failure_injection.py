"""Failure-injection level: every outage fails closed, never into a trade."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from execution.n8n_client import ExecutionConfig, N8nUnavailableError, build_request
from execution.order_manager import ExecutionOrderManager
from hermes.context import ContextBuilder
from hermes.decision import decide
from hermes.models.decision import Decision
from monitoring.positions import LifecycleTracker
from risk.engine import RiskEngine


NOW_MS = 1_700_000_000_000


def moment(ms=NOW_MS):
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def fresh_snapshot(symbol="BTCUSDT"):
    return {
        "symbol": symbol,
        "event_time": "2024-01-01T00:00:00+00:00",
        "last_price": 100.0,
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


def live_context(symbol="BTCUSDT", now_ms=NOW_MS):
    builder = ContextBuilder(stale_after_seconds=30.0)
    return builder.build(
        symbol=symbol,
        feature_snapshot=fresh_snapshot(symbol),
        event_time_ms=now_ms,
        breadth={"advancing_pct": 0.7},
        cross_exchange=None,
        health_entries=good_health(),
        now_ms=now_ms,
    )


def buy_decision(decision_id="dec-fail-1", now_ms=NOW_MS):
    return Decision(
        decision_id=decision_id,
        timestamp=moment(now_ms),
        symbol="BTCUSDT",
        action="BUY",
        confidence=0.9,
        entry={"symbol": "BTCUSDT", "side": "BUY", "reference_price": 100.0},
        position={"position_qty": 0.0, "exposure_notional": 0.0, "unrealized_pnl": 0.0, "realized_pnl": 0.0},
        risk={"stop_loss": 98.0, "take_profit": 103.0, "risk_amount": 0.0},
        time_horizon="15m",
        thesis=["injected thesis"],
        strategy_version_id="v1",
        expiry_seconds=120,
    )


def base_account(**overrides):
    account = {
        "equity": 10000.0,
        "peak_equity": 10000.0,
        "daily_realized_pnl": 0.0,
        "open_notional": 0.0,
        "symbol_exposure": 0.0,
        "open_positions": 0,
        "now_ms": NOW_MS + 1000,
    }
    for key in overrides:
        account[key] = overrides[key]
    return account


def paper_config():
    return ExecutionConfig(
        webhook_url="https://n8n.local/webhook/fail", webhook_secret="fail-secret", environment="paper"
    )


def test_ws_disconnect_yields_hold_and_risk_reject():
    builder = ContextBuilder(stale_after_seconds=30.0)
    stale = builder.build(
        symbol="BTCUSDT",
        feature_snapshot=fresh_snapshot(),
        event_time_ms=NOW_MS - 600_000,
        breadth=None,
        cross_exchange=None,
        health_entries=good_health(),
        now_ms=NOW_MS,
    )
    assert stale.valid is False
    decision, _record = decide("BTCUSDT", stale, [])
    assert decision.action == "HOLD"
    engine = RiskEngine()
    risk = engine.evaluate(buy_decision(), stale, **base_account())
    assert risk.status == "REJECTED"
    assert risk.approved_quantity == 0.0


def test_n8n_outage_leaves_no_position(tmp_path):
    engine = RiskEngine()
    risk = engine.evaluate(buy_decision(), live_context(), **base_account())
    assert risk.status == "APPROVED"
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    manager = ExecutionOrderManager(tmp_path / "fail_outage.sqlite3")

    def dead_sender(url, payload, headers, timeout):
        raise OSError("websocket to n8n severed")

    with pytest.raises(N8nUnavailableError):
        manager.submit_once(request, config=paper_config(), sender=dead_sender, now=moment())
    assert manager.get(request.execution_id)["state"] == "EXPIRED"
    tracker = LifecycleTracker(tmp_path / "fail_life.sqlite3")
    assert tracker.open_position("BTCUSDT") is None
    assert tracker.may_enter("BTCUSDT") is True
    manager.close()
    tracker.close()


def test_binance_rejection_never_becomes_a_fill(tmp_path):
    engine = RiskEngine()
    risk = engine.evaluate(buy_decision("dec-fail-rej"), live_context(), **base_account())
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    manager = ExecutionOrderManager(tmp_path / "fail_rej.sqlite3")

    def rejecting_sender(url, payload, headers, timeout):
        return {"status": "REJECTED", "reason": "BINANCE_REJECT_INSUFFICIENT_BALANCE"}

    outcome = manager.submit_once(request, config=paper_config(), sender=rejecting_sender, now=moment())
    assert outcome["state"] == "SUBMITTED"
    assert manager.get(request.execution_id)["state"] != "ACKED"
    tracker = LifecycleTracker(tmp_path / "fail_rej_life.sqlite3")
    assert tracker.open_position("BTCUSDT") is None
    manager.close()
    tracker.close()


def test_kill_switch_refuses_while_decision_layer_hung():
    engine = RiskEngine()
    engine.activate_kill_switch("injected daily loss")
    risk = engine.evaluate(buy_decision("dec-fail-kill"), live_context(), **base_account())
    assert risk.status == "REJECTED"
    assert "kill switch" in str(risk.rejection_reason).lower()
    # Even a pre-built healthy request cannot pass with the switch active.
    healthy = RiskEngine()
    good = healthy.evaluate(buy_decision("dec-fail-kill2"), live_context(), **base_account())
    assert good.status == "APPROVED"
    request = build_request(good, symbol="BTCUSDT", side="BUY", now=moment())
    calls: list[dict] = []

    def sender(url, payload, headers, timeout):
        calls.append(payload)
        return {"order_id": "ord-never"}

    from execution.n8n_client import InvalidRequestError, submit_request

    with pytest.raises(InvalidRequestError, match="kill switch"):
        submit_request(request, config=paper_config(), sender=sender, now=moment(), kill_switch_active=True)
    assert calls == []


def test_corrupted_decision_in_flight_is_refused():
    engine = RiskEngine()
    risk = engine.evaluate(buy_decision("dec-fail-tamper"), live_context(), **base_account())
    tampered = dataclasses.replace(risk, approved_quantity=risk.approved_quantity * 2.0)
    from execution.n8n_client import InvalidRequestError

    with pytest.raises(InvalidRequestError, match="integrity"):
        build_request(tampered, symbol="BTCUSDT", side="BUY", now=moment())
