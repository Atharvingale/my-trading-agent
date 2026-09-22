from datetime import datetime, timezone

from binance_data_layer.features import build_feature_snapshot


def test_execution_quality_is_in_feature_snapshot():
    snapshot = build_feature_snapshot(
        symbol="BTCUSDT", event_time=datetime.now(timezone.utc), last_price=100.0,
        bid_price=99.99, ask_price=100.01, bid_qty=10.0, ask_qty=8.0,
        recent_trades=[], bids=[(99.99, 10.0)], asks=[(100.01, 8.0)],
        execution_quantity=1.0,
    )
    assert snapshot["execution_quality"]["BUY"]["status"] == "OK"
    assert snapshot["execution_quality"]["SELL"]["status"] == "OK"
    assert snapshot["execution_quality"]["BUY"]["round_trip_cost_rate"] > 0
