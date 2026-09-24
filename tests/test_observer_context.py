"""Module 3 acceptance: normal, stale, regime-change, restart recovery."""

from __future__ import annotations

import pathlib

from hermes.context import ContextBuilder
from hermes.models.market import MarketContext
from hermes.observer import HermesObserver


NOW_MS = 1_700_000_000_000


def fresh_snapshot(symbol="BTCUSDT", alignment="BULLISH", fast=101.0, slow=100.0):
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
                "ema_fast": fast,
                "ema_slow": slow,
                "rsi": 55.0,
                "atr": 1.0,
                "vwap": 99.5,
                "bollinger_bandwidth": 0.04,
                "returns": 0.001,
            }
        },
        "multi_timeframe_alignment": {"state": alignment, "confirmed_timeframes": 2},
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


def test_normal_update_produces_valid_context():
    builder = ContextBuilder(stale_after_seconds=30.0)
    context = builder.build(
        symbol="BTCUSDT",
        feature_snapshot=fresh_snapshot(),
        event_time_ms=NOW_MS,
        breadth={"advancing_pct": 0.7},
        cross_exchange={
            "confirmation_status": "CONFIRMED",
            "reference_price": 100.0,
            "disagreement_bps": 5.0,
            "source_count": 4,
        },
        health_entries=good_health(),
        now_ms=NOW_MS,
    )
    assert isinstance(context, MarketContext)
    assert context.valid is True
    assert context.invalid_reasons == ()
    assert context.regime is not None
    assert context.regime.regime == "TREND_UP"
    assert context.trend is not None
    assert context.trend.last_price == 100.0
    assert context.order_flow is not None
    assert context.order_flow.cvd == 10.0
    assert context.liquidity is not None
    assert context.liquidity.spread_state == "TIGHT"
    assert context.cross_exchange is not None
    assert context.cross_exchange.status == "CONFIRMED"
    assert context.data_quality is not None
    assert context.data_quality.freshness == "FRESH"
    # Deferred sections report availability explicitly.
    assert context.derivatives is not None
    assert context.derivatives.available is False
    assert context.options is not None
    assert context.options.available is False


def test_stale_upstream_produces_invalid_not_guess():
    builder = ContextBuilder(stale_after_seconds=30.0)
    context = builder.build(
        symbol="BTCUSDT",
        feature_snapshot=fresh_snapshot(),
        event_time_ms=NOW_MS - 120_000,
        breadth={"advancing_pct": 0.7},
        cross_exchange=None,
        health_entries=good_health(),
        now_ms=NOW_MS,
    )
    assert context.valid is False
    found = False
    for reason in context.invalid_reasons:
        if reason == "STALE":
            found = True
    assert found is True


def test_contradictory_health_produces_invalid():
    builder = ContextBuilder()
    bad_health = [
        {
            "component": "spot_websocket",
            "symbol": None,
            "status": "disconnected",
            "observed_time_ms": NOW_MS,
            "details": {"error": "boom"},
        }
    ]
    context = builder.build(
        symbol="BTCUSDT",
        feature_snapshot=fresh_snapshot(),
        event_time_ms=NOW_MS,
        breadth=None,
        cross_exchange=None,
        health_entries=bad_health,
        now_ms=NOW_MS,
    )
    assert context.valid is False
    found = False
    for reason in context.invalid_reasons:
        if reason == "UPSTREAM_UNHEALTHY":
            found = True
    assert found is True


def test_regime_change_detection_and_emit():
    builder = ContextBuilder(emit_interval_ms=60_000)
    prior = builder.build(
        symbol="BTCUSDT",
        feature_snapshot=fresh_snapshot(alignment="BULLISH", fast=101.0, slow=100.0),
        event_time_ms=NOW_MS,
        breadth={"advancing_pct": 0.7},
        cross_exchange=None,
        health_entries=good_health(),
        now_ms=NOW_MS,
    )
    current = builder.build(
        symbol="BTCUSDT",
        feature_snapshot=fresh_snapshot(alignment="BEARISH", fast=99.0, slow=100.0),
        event_time_ms=NOW_MS + 1000,
        breadth={"advancing_pct": 0.3},
        cross_exchange=None,
        health_entries=good_health(),
        prior=prior,
        now_ms=NOW_MS + 1000,
    )
    assert prior.regime.regime == "TREND_UP"
    assert current.regime.regime == "TREND_DOWN"
    assert builder.detect_regime_change(prior, current) is True
    decision, reason = builder.should_emit(prior, current, NOW_MS)
    assert decision is True
    assert reason == "REGIME_CHANGE"
    # Same regime within interval does not re-emit.
    steady = builder.build(
        symbol="BTCUSDT",
        feature_snapshot=fresh_snapshot(alignment="BEARISH", fast=99.0, slow=100.0),
        event_time_ms=NOW_MS + 2000,
        breadth={"advancing_pct": 0.3},
        cross_exchange=None,
        health_entries=good_health(),
        prior=current,
        now_ms=NOW_MS + 2000,
    )
    decision2, _ = builder.should_emit(current, steady, NOW_MS + 1000)
    assert decision2 is False


def test_recovery_after_market_data_restart():
    observer = HermesObserver(symbols=("BTCUSDT",))
    snapshots = {"BTCUSDT": fresh_snapshot()}
    # Fresh -> valid.
    emitted = observer.refresh_once(
        snapshots,
        {"BTCUSDT": NOW_MS},
        breadth={"advancing_pct": 0.6},
        health_entries=good_health(),
        now_ms=NOW_MS,
    )
    assert len(emitted) == 1
    assert observer.latest_context("BTCUSDT").valid is True
    # Restart gap: stale event clock -> invalid and emits validity change.
    emitted2 = observer.refresh_once(
        snapshots,
        {"BTCUSDT": NOW_MS - 300_000},
        breadth={"advancing_pct": 0.6},
        health_entries=good_health(),
        now_ms=NOW_MS + 60_000,
    )
    assert observer.latest_context("BTCUSDT").valid is False
    # Service recovers: fresh again -> valid.
    emitted3 = observer.refresh_once(
        snapshots,
        {"BTCUSDT": NOW_MS + 61_000},
        breadth={"advancing_pct": 0.6},
        health_entries=good_health(),
        now_ms=NOW_MS + 61_000,
    )
    assert observer.latest_context("BTCUSDT").valid is True
    assert len(emitted2) + len(emitted3) >= 1


def test_observer_handles_ws_messages_and_subscriber_hook():
    observer = HermesObserver(symbols=("BTCUSDT",))
    received = []

    def hook(context):
        received.append(context)

    observer.subscribe(hook)
    observer.handle_market_event(
        {"type": "market_event", "symbol": "BTCUSDT", "event_time_ms": NOW_MS}
    )
    observer.handle_breadth({"type": "breadth", "payload": {"advancing_pct": 0.65}})
    observer.handle_cross_exchange(
        {
            "type": "cross_exchange_confirmation",
            "symbol": "BTCUSDT",
            "payload": {
                "confirmation_status": "CONFIRMED",
                "reference_price": 100.0,
                "disagreement_bps": 4.0,
                "source_count": 4,
            },
        }
    )
    emitted = observer.refresh_once(
        {"BTCUSDT": fresh_snapshot()},
        {"BTCUSDT": NOW_MS},
        health_entries=good_health(),
        now_ms=NOW_MS,
    )
    assert len(emitted) == 1
    assert len(received) == 1
    assert received[0].symbol == "BTCUSDT"


def test_no_trading_imports_in_module_3():
    # Scoped to Module 3's own files (observer, context, market model): the
    # acceptance bar is that the observer/context producer never calls trading
    # code. Module 5's decision.py legitimately consumes the proposal contract
    # type and lives in the same package, so it is excluded here by design.
    root = pathlib.Path(__file__).resolve().parent.parent / "hermes"
    files = [
        root / "observer.py",
        root / "context.py",
        root / "models" / "market.py",
    ]
    for path in files:
        assert path.exists(), f"Module 3 file missing: {path}"
    forbidden = ("from strategies", "import strategies", "from risk", "import risk",
                 "from execution", "import execution", "from decision", "import decision")
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                for marker in forbidden:
                    if marker in stripped:
                        raise AssertionError(f"{path.name} contains forbidden import: {line.strip()}")


def test_deterministic_same_inputs_same_context():
    builder = ContextBuilder()
    kwargs = {
        "symbol": "BTCUSDT",
        "feature_snapshot": fresh_snapshot(),
        "event_time_ms": NOW_MS,
        "breadth": {"advancing_pct": 0.55},
        "cross_exchange": None,
        "health_entries": good_health(),
        "now_ms": NOW_MS,
    }
    first = builder.build(**kwargs)
    second = builder.build(**kwargs)
    assert first.to_dict() == second.to_dict()
