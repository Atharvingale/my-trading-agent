from datetime import datetime, timezone

from binance_data_layer.collector import MarketState
from binance_data_layer.features import build_feature_snapshot
from binance_data_layer.quality import QualityTracker


def test_market_state_keeps_only_closed_candles_and_adds_technical_features():
    state = MarketState("BTCUSDT", 50)
    for i in range(30):
        state.apply({
            "event_type": "kline",
            "event_time_ms": i * 60_000,
            "payload": {
                "interval": "1m", "open_time_ms": i * 60_000,
                "open": 100 + i, "high": 101 + i, "low": 99 + i,
                "close": 100 + i, "volume": 10, "closed": True,
            },
        })
    state.apply({
        "event_type": "kline", "event_time_ms": 30 * 60_000,
        "payload": {
            "interval": "1m", "open_time_ms": 30 * 60_000,
            "open": 130, "high": 131, "low": 129,
            "close": 130, "volume": 10, "closed": False,
        },
    })
    assert len(state.candles["1m"]) == 30
    assert state.features()["technical"]["1m"]["ema"] is not None


def test_quality_tracker_detects_duplicates_order_and_sequence_gaps():
    tracker = QualityTracker()
    assert tracker.observe("spot", "BTCUSDT", "aggTrade", 1000, 1100, event_id="a").status == "GOOD"
    duplicate = tracker.observe("spot", "BTCUSDT", "aggTrade", 1000, 1101, event_id="a")
    assert duplicate.status == "DEGRADED"
    out_of_order = tracker.observe("spot", "BTCUSDT", "aggTrade", 900, 1102, event_id="b")
    assert "OUT_OF_ORDER" in out_of_order.reasons
    gap = tracker.observe("spot", "BTCUSDT", "depthUpdate", 1200, 1201, first_update_id=10, final_update_id=12)
    gap = tracker.observe("spot", "BTCUSDT", "depthUpdate", 1300, 1301, first_update_id=15, final_update_id=16)
    assert "SEQUENCE_GAP" in gap.reasons
