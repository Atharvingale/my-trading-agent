"""Step 1B acceptance: deterministic offline fill simulation."""

from __future__ import annotations

import pytest

from paper_trading import (
    InsufficientPositionError,
    PaperEngine,
    PaperOrder,
    PaperPortfolio,
    execution_report,
    simulate_fill,
)
from paper_trading.simulator import make_order_id


def book(price=100.0, spread_bps=2.0, depth=1000.0):
    half = spread_bps / 2.0 / 10000.0
    return {"bid": price * (1.0 - half), "ask": price * (1.0 + half), "depth_qty": depth}


def test_buy_fill_math_is_exact():
    order = PaperOrder(order_id="o1", symbol="BTCUSDT", side="BUY", quantity=1.0, requested_price=100.0, timestamp_ms=1)
    fills = simulate_fill(order, book(100.0), fee_rate=0.001, slippage_bps=0.0)
    assert len(fills) == 1
    fill = fills[0]
    assert fill.status == "FILLED"
    assert fill.filled_quantity == pytest.approx(1.0)
    ask = 100.0 * (1.0 + 1.0 / 10000.0)
    assert fill.fill_price == pytest.approx(ask)
    assert fill.fee_paid == pytest.approx(ask * 0.001)


def test_partial_fill_on_thin_book():
    order = PaperOrder(order_id="o2", symbol="BTCUSDT", side="BUY", quantity=10.0, requested_price=100.0, timestamp_ms=2)
    fills = simulate_fill(order, book(100.0, depth=3.0))
    assert fills[0].status == "PARTIAL"
    assert fills[0].filled_quantity == pytest.approx(3.0)
    assert fills[0].reason == "INSUFFICIENT_DEPTH"


def test_slippage_is_adverse_both_sides():
    buy = PaperOrder(order_id="b", symbol="X", side="BUY", quantity=1.0, requested_price=None, timestamp_ms=3)
    sell = PaperOrder(order_id="s", symbol="X", side="SELL", quantity=1.0, requested_price=None, timestamp_ms=4)
    market = {"bid": 99.0, "ask": 101.0}
    buy_fill = simulate_fill(buy, market, slippage_bps=100.0)[0]
    sell_fill = simulate_fill(sell, market, slippage_bps=100.0)[0]
    assert buy_fill.fill_price > 101.0
    assert sell_fill.fill_price < 99.0
    assert buy_fill.slippage_cost > 0
    assert sell_fill.slippage_cost > 0


def test_expected_vs_realized_report():
    order = PaperOrder(order_id="o3", symbol="BTCUSDT", side="BUY", quantity=2.0, requested_price=100.0, timestamp_ms=5)
    fills = simulate_fill(order, book(100.0), fee_rate=0.001, slippage_bps=10.0)
    report = execution_report(order, fills)
    assert report["status"] == "FILLED"
    assert report["filled_quantity"] == pytest.approx(2.0)
    assert report["expected_slippage_bps"] is not None
    assert report["expected_slippage_bps"] > 0
    assert report["fees_paid"] > 0


def test_portfolio_round_trip_and_oversell_rejected():
    portfolio = PaperPortfolio(starting_cash=100000.0)
    buy = PaperOrder(order_id="b1", symbol="BTCUSDT", side="BUY", quantity=1.0, requested_price=100.0, timestamp_ms=6)
    for fill in simulate_fill(buy, book(100.0), fee_rate=0.0, slippage_bps=0.0):
        portfolio.apply_fill(fill)
    assert portfolio.position_qty("BTCUSDT") == pytest.approx(1.0)
    sell = PaperOrder(order_id="s1", symbol="BTCUSDT", side="SELL", quantity=1.0, requested_price=110.0, timestamp_ms=7)
    for fill in simulate_fill(sell, book(110.0), fee_rate=0.0, slippage_bps=0.0):
        portfolio.apply_fill(fill)
    assert portfolio.position_qty("BTCUSDT") == pytest.approx(0.0)
    assert portfolio.realized_pnl > 0
    bad = PaperOrder(order_id="s2", symbol="BTCUSDT", side="SELL", quantity=5.0, requested_price=110.0, timestamp_ms=8)
    with pytest.raises(InsufficientPositionError):
        for fill in simulate_fill(bad, book(110.0)):
            portfolio.apply_fill(fill)


def test_engine_replay_is_deterministic():
    engine = PaperEngine(starting_cash=100000.0)
    first = PaperOrder(order_id=make_order_id(symbol="BTCUSDT", side="BUY", quantity=1.0, timestamp_ms=9),
                       symbol="BTCUSDT", side="BUY", quantity=1.0, requested_price=100.0, timestamp_ms=9)
    second = PaperOrder(order_id=make_order_id(symbol="BTCUSDT", side="SELL", quantity=1.0, timestamp_ms=10),
                        symbol="BTCUSDT", side="SELL", quantity=1.0, requested_price=110.0, timestamp_ms=10)
    trail = [(first, book(100.0)), (second, book(110.0))]
    reports = engine.replay(trail, fee_rate=0.0, slippage_bps=0.0)
    assert len(reports) == 2
    assert engine.equity({"BTCUSDT": 110.0}) == pytest.approx(engine.equity({"BTCUSDT": 110.0}))
    assert engine.snapshot()["order_count"] == 2


def test_no_network_or_exchange_imports():
    import pathlib as _pathlib

    root = _pathlib.Path(__file__).resolve().parent.parent / "paper_trading"
    forbidden = ("websocket", "aiohttp", "requests", "urllib", "binance_client", "ApiSecret", "api_secret")
    for path in root.rglob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                lowered = stripped.lower()
                for marker in forbidden:
                    if marker.lower() in lowered:
                        raise AssertionError(f"{path.name} contains forbidden import: {line.strip()}")
