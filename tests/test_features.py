from datetime import datetime, timezone

from binance_data_layer.features import build_feature_snapshot


def test_build_feature_snapshot_calculates_order_flow_and_spread():
    snapshot = build_feature_snapshot(
        symbol="BTCUSDT",
        event_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_price=100.0,
        bid_price=99.9,
        ask_price=100.1,
        bid_qty=30.0,
        ask_qty=10.0,
        recent_trades=[
            {"price": 100.0, "qty": 2.0, "is_buyer_maker": False},
            {"price": 99.9, "qty": 1.0, "is_buyer_maker": True},
        ],
        bids=[(99.9, 30.0), (99.8, 20.0)],
        asks=[(100.1, 10.0), (100.2, 10.0)],
    )

    assert snapshot["spread_bps"] == 20.0
    assert snapshot["top_book_imbalance"] == 0.5
    assert snapshot["trade_cvd"] == 1.0
    assert snapshot["trade_volume"] == 3.0


def test_build_feature_snapshot_handles_empty_book():
    snapshot = build_feature_snapshot(
        symbol="ETHUSDT",
        event_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_price=2000.0,
        bid_price=None,
        ask_price=None,
        bid_qty=0.0,
        ask_qty=0.0,
        recent_trades=[],
        bids=[],
        asks=[],
    )

    assert snapshot["spread_bps"] is None
    assert snapshot["top_book_imbalance"] is None
    assert snapshot["trade_cvd"] == 0.0


def test_feature_snapshot_uses_utc_iso_timestamp():
    snapshot = build_feature_snapshot(
        symbol="BTCUSDT",
        event_time=datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc),
        last_price=100.0,
        bid_price=99.0,
        ask_price=101.0,
        bid_qty=1.0,
        ask_qty=1.0,
        recent_trades=[],
        bids=[],
        asks=[],
    )

    assert snapshot["event_time"] == "2026-01-01T12:30:00+00:00"
