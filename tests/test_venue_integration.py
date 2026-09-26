"""Execution-integration level: n8n boundary into the paper venue."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from execution.n8n_client import ExecutionConfig, build_request
from execution.order_manager import ExecutionOrderManager
from paper_trading.engine import PaperEngine
from paper_trading.simulator import PaperOrder
from hermes.context import ContextBuilder
from hermes.models.decision import Decision
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


def approved_flow(decision_id="dec-venue-1"):
    builder = ContextBuilder(stale_after_seconds=30.0)
    context = builder.build(
        symbol="BTCUSDT",
        feature_snapshot=fresh_snapshot(),
        event_time_ms=NOW_MS,
        breadth={"advancing_pct": 0.7},
        cross_exchange=None,
        health_entries=good_health(),
        now_ms=NOW_MS,
    )
    assert context.valid is True
    decision = Decision(
        decision_id=decision_id,
        timestamp=moment(),
        symbol="BTCUSDT",
        action="BUY",
        confidence=0.7,
        entry={"symbol": "BTCUSDT", "side": "BUY", "reference_price": 100.0},
        position={"position_qty": 0.0, "exposure_notional": 0.0, "unrealized_pnl": 0.0, "realized_pnl": 0.0},
        risk={"stop_loss": 98.0, "take_profit": 103.0, "risk_amount": 0.0},
        time_horizon="15m",
        thesis=["venue thesis"],
        strategy_version_id="v1",
        expiry_seconds=120,
    )
    engine = RiskEngine()
    risk = engine.evaluate(
        decision, context, equity=10000.0, peak_equity=10000.0, daily_realized_pnl=0.0,
        open_notional=0.0, symbol_exposure=0.0, open_positions=0, now_ms=NOW_MS + 1000,
    )
    assert risk.status == "APPROVED"
    return risk


def paper_sender(paper: PaperEngine, market):
    from paper_trading.simulator import execution_report, simulate_fill

    def send(url, payload, headers, timeout):
        order = PaperOrder(
            order_id=str(payload["execution_id"]),
            symbol=str(payload["symbol"]),
            side=str(payload["side"]),
            quantity=float(payload["quantity"]),
            requested_price=None,
            timestamp_ms=int(payload["timestamp_ms"]),
        )
        produced = simulate_fill(order, market)
        for fill in produced:
            paper.portfolio.apply_fill(fill)
            paper.fills.append(fill)
        paper.orders.append(order)
        report = execution_report(order, produced)
        return {"order_id": order.order_id, "status": "ACKED", "filled": report["filled_quantity"]}

    return send


def test_n8n_request_fills_exactly_at_paper_venue(tmp_path):
    risk = approved_flow()
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    paper = PaperEngine(starting_cash=10000.0)
    market = {"bid": 99.9, "ask": 100.1, "depth_qty": 1000.0}
    manager = ExecutionOrderManager(tmp_path / "venue.sqlite3")
    config = ExecutionConfig(
        webhook_url="https://n8n.local/webhook/paper", webhook_secret="venue-secret", environment="paper"
    )
    outcome = manager.submit_once(
        request, config=config, sender=paper_sender(paper, market), now=moment(), risk_decision=risk
    )
    assert outcome["state"] == "ACKED"
    assert len(paper.fills) == 1
    assert paper.fills[0].filled_quantity == pytest.approx(risk.approved_quantity)
    assert paper.fills[0].filled_quantity == pytest.approx(request.quantity)
    assert paper.snapshot()["cash"] < 10000.0
    manager.close()


def test_thin_venue_book_partials_without_overfill(tmp_path):
    risk = approved_flow("dec-venue-2")
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    paper = PaperEngine(starting_cash=10000.0)
    market = {"bid": 99.9, "ask": 100.1, "depth_qty": 0.05}
    manager = ExecutionOrderManager(tmp_path / "venue_thin.sqlite3")
    config = ExecutionConfig(
        webhook_url="https://n8n.local/webhook/paper", webhook_secret="venue-secret", environment="paper"
    )
    outcome = manager.submit_once(
        request, config=config, sender=paper_sender(paper, market), now=moment(), risk_decision=risk
    )
    assert outcome["state"] == "ACKED"
    assert paper.fills[0].filled_quantity <= risk.approved_quantity + 1e-9
    assert paper.fills[0].status == "PARTIAL"
    manager.close()
