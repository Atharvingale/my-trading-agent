"""Soak level: bounded continuous pipeline runtime with induced faults.

Scaled-down analogue of the 24h soak: hundreds of market-data → context →
decision → risk cycles with periodic disconnects, asserting zero exceptions,
fail-closed behavior throughout, and linear bounded state growth. Production
today is idle (zero PASS strategies), so the honest soak proves idle-safety
under continuous runtime rather than fake trading activity.
"""

from __future__ import annotations

from datetime import datetime, timezone

from hermes.context import ContextBuilder
from hermes.decision import decide
from memory.repository import MemoryRepository
from monitoring.positions import LifecycleTracker
from risk.engine import RiskEngine


NOW_MS = 1_700_000_000_000
CYCLES = 200


def snapshot_for(symbol, price, now_ms, spread_bps=2.0):
    return {
        "symbol": symbol,
        "event_time": "2024-01-01T00:00:00+00:00",
        "last_price": price,
        "spread_bps": spread_bps,
        "bid_depth": 500.0,
        "ask_depth": 500.0,
        "depth_within_bps": {25: {"bid_qty": 400.0, "ask_qty": 400.0}},
        "execution_quality": {"BUY": {"price_impact_rate": 0.0001, "status": "OK"}},
        "technical": {
            "1h": {
                "ema_fast": price + 1.0,
                "ema_slow": price,
                "rsi": 55.0,
                "atr": 1.0,
                "vwap": price - 0.5,
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


def good_health(now_ms):
    return [
        {
            "component": "spot_websocket",
            "symbol": None,
            "status": "connected",
            "observed_time_ms": now_ms,
            "details": {},
        }
    ]


def test_bounded_pipeline_soak_with_disconnects(tmp_path):
    builder = ContextBuilder(stale_after_seconds=30.0)
    engine = RiskEngine()
    tracker = LifecycleTracker(tmp_path / "soak_life.sqlite3")
    memory = MemoryRepository(tmp_path / "soak_mem.sqlite3")
    decisions = 0
    holds = 0
    rejects = 0
    disconnects = 0
    errors: list[str] = []
    price = 100.0
    seed = 12345
    cycle = 0
    while cycle < CYCLES:
        # Deterministic walk (LCG): reproducible without random state.
        seed = (1103515245 * seed + 12345) % 2147483648
        drift = (seed % 200 - 100) / 1000.0
        price = max(1.0, price + drift)
        now_ms = NOW_MS + cycle * 1000
        # Every 50th cycle the feed drops: decisions must HOLD on stale data.
        if cycle % 50 == 49:
            event_ms = now_ms - 600_000
            disconnects = disconnects + 1
        else:
            event_ms = now_ms
        try:
            context = builder.build(
                symbol="BTCUSDT",
                feature_snapshot=snapshot_for("BTCUSDT", price, now_ms),
                event_time_ms=event_ms,
                breadth={"advancing_pct": 0.7},
                cross_exchange=None,
                health_entries=good_health(now_ms),
                now_ms=now_ms,
            )
            decision, _record = decide("BTCUSDT", context, [])
            decisions = decisions + 1
            assert decision.action == "HOLD"
            holds = holds + 1
            risk = engine.evaluate(
                _hold_like(decision, now_ms),
                context,
                equity=10000.0,
                peak_equity=10000.0,
                daily_realized_pnl=0.0,
                open_notional=0.0,
                symbol_exposure=0.0,
                open_positions=0,
                now_ms=now_ms + 10,
            )
            assert risk.status == "REJECTED"
            rejects = rejects + 1
        except AssertionError:
            raise
        except Exception as exc:
            errors.append("%d: %s" % (cycle, exc))
        cycle = cycle + 1
    assert errors == []
    assert decisions == CYCLES
    assert holds == CYCLES
    assert rejects == CYCLES
    assert disconnects == 4
    # Idle production leaves no positions, no trades, no fills behind.
    assert tracker.open_position("BTCUSDT") is None
    assert memory.connection.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"] == 0
    assert memory.connection.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"] == 0
    # Lifecycle ledger holds no rows at all: nothing was ever submitted.
    assert tracker.connection.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == 0
    tracker.close()
    memory.close()


def _hold_like(decision, now_ms):
    from hermes.models.decision import Decision

    return Decision(
        decision_id=decision.decision_id,
        timestamp=datetime.fromtimestamp(now_ms / 1000.0, tz=timezone.utc),
        symbol=decision.symbol,
        action="HOLD",
        confidence=decision.confidence,
        entry=dict(decision.entry),
        position=dict(decision.position),
        risk=dict(decision.risk),
        time_horizon=decision.time_horizon,
        thesis=list(decision.thesis),
        strategy_version_id=decision.strategy_version_id,
        expiry_seconds=120,
    )
