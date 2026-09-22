from binance_data_layer.collector import BinanceCollector, normalize_event
from binance_data_layer.config import Settings


def test_spot_streams_include_analysis_timeframes():
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",)))
    streams = collector.spot_streams()
    assert "btcusdt@kline_1m" in streams
    assert "btcusdt@kline_5m" in streams
    assert "btcusdt@kline_15m" in streams
    assert "btcusdt@kline_1h" in streams
    assert "btcusdt@kline_4h" in streams
    collector.store.close()


def test_normalize_kline_event():
    event = normalize_event(
        "btcusdt@kline_1m",
        {
            "e": "kline",
            "E": 1700000000123,
            "s": "BTCUSDT",
            "k": {
                "t": 1700000000000,
                "T": 1700000059999,
                "i": "1m",
                "o": "100.0",
                "c": "101.0",
                "h": "102.0",
                "l": "99.0",
                "v": "50.0",
                "x": True,
                "q": "5050.0",
                "n": 100,
                "V": "25.0",
                "Q": "2525.0",
            },
        },
    )
    assert event["event_type"] == "kline"
    assert event["payload"]["interval"] == "1m"
    assert event["payload"]["close"] == 101.0
    assert event["payload"]["closed"] is True
