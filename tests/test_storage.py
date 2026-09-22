from pathlib import Path

from binance_data_layer.storage import MarketStore


def test_market_store_creates_tables_and_persists_records(tmp_path: Path):
    store = MarketStore(tmp_path / "market.sqlite3")
    store.save_event(
        stream="test",
        symbol="BTCUSDT",
        event_type="trade",
        event_time_ms=1,
        received_time_ms=2,
        payload={"price": 100.0},
    )
    store.save_features(
        {"symbol": "BTCUSDT", "event_time": "2026-01-01T00:00:00+00:00", "last_price": 100.0},
        3,
    )
    store.save_health(
        component="test",
        symbol="BTCUSDT",
        status="ok",
        observed_time_ms=4,
        details={"fresh": True},
    )

    assert store.counts() == {
        "market_events": 1,
        "feature_snapshots": 1,
        "data_health": 1,
    }
    store.close()
