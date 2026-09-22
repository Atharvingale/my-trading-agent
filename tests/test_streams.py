from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


def test_spot_and_futures_streams_are_separate():
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",)))

    assert collector.spot_streams() == [
        "btcusdt@aggTrade",
        "btcusdt@bookTicker",
        "btcusdt@depth20@100ms",
        "btcusdt@kline_1m",
        "btcusdt@kline_5m",
        "btcusdt@kline_15m",
        "btcusdt@kline_1h",
        "btcusdt@kline_4h",
    ]
    assert collector.futures_streams() == [
        "btcusdt@markPrice@1s",
        "!forceOrder@arr",
    ]
    assert "fstream.binance.com" in collector.futures_stream_url()
    assert "stream.binance.com" in collector.spot_stream_url()
    collector.store.close()
