from datetime import datetime, timezone

from binance_data_layer.features import build_feature_snapshot


def test_feature_snapshot_adds_rolling_order_flow_and_depth_bands():
    trades = [
        {"price": 100.0, "qty": 5.0, "is_buyer_maker": False},
        {"price": 100.0, "qty": 1.0, "is_buyer_maker": True},
        {"price": 100.0, "qty": 20.0, "is_buyer_maker": False},
    ]
    snapshot = build_feature_snapshot(
        symbol="BTCUSDT", event_time=datetime.now(timezone.utc), last_price=100.0,
        bid_price=99.99, ask_price=100.01, bid_qty=10.0, ask_qty=8.0,
        recent_trades=trades,
        bids=[(99.99, 10.0), (99.98, 5.0)],
        asks=[(100.01, 8.0), (100.02, 4.0)],
    )
    assert snapshot["aggressive_buy_pct"] == 25 / 26
    assert snapshot["large_trade_concentration"] == 20 / 26
    assert set(snapshot["depth_within_bps"]) == {5, 10, 25}
    assert snapshot["depth_within_bps"][5]["bid_qty"] == 15.0
    assert snapshot["spread_stability_bps"] is not None


def test_feature_snapshot_returns_null_for_missing_execution_book():
    snapshot = build_feature_snapshot(
        symbol="ETHUSDT", event_time=datetime.now(timezone.utc), last_price=2000.0,
        bid_price=None, ask_price=None, bid_qty=0.0, ask_qty=0.0,
        recent_trades=[], bids=[], asks=[],
    )
    assert snapshot["depth_within_bps"][5]["bid_qty"] is None
    assert snapshot["spread_stability_bps"] is None
