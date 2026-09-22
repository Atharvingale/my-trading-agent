from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


def test_cross_exchange_streams_are_enabled_by_config():
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",), enable_cross_exchange=True))
    assert collector.cross_exchange_sources() == ("coinbase", "kraken", "okx")
    assert "coinbase" in collector.cross_exchange_urls()
    collector.store.close()


def test_cross_exchange_can_be_disabled():
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",), enable_cross_exchange=False))
    assert collector.cross_exchange_sources() == ()
    collector.store.close()
