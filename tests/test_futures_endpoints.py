from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


def test_futures_market_stream_uses_market_endpoint():
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",)))
    url = collector.futures_stream_url()
    assert url.startswith("wss://fstream.binance.com/market/stream?")
    assert "btcusdt@markPrice@1s" in url
    assert "!forceOrder@arr" in url
    collector.store.close()


def test_futures_private_stream_uses_private_endpoint():
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",)))
    assert collector.futures_private_stream_url("listen-key") == (
        "wss://fstream.binance.com/private/ws?listenKey=listen-key"
    )
    collector.store.close()
