from datetime import datetime, timezone

from binance_data_layer.collector import MarketState


def test_market_state_health_detects_stale_and_fresh_data():
    state = MarketState("BTCUSDT")
    state.last_event_time_ms = 1_000

    assert state.health(now_ms=5_000, stale_after_seconds=10.0)["status"] == "fresh"
    assert state.health(now_ms=20_000, stale_after_seconds=10.0)["status"] == "stale"


def test_market_state_health_detects_missing_data():
    state = MarketState("ETHUSDT")
    health = state.health(now_ms=1_000, stale_after_seconds=10.0)
    assert health["status"] == "missing"
    assert health["age_seconds"] is None
