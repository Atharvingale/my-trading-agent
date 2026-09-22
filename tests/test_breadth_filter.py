from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


def test_breadth_message_filters_stablecoin_bases_and_persists():
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",), enable_market_breadth=True))
    collector._save_breadth_message("!ticker@arr", {"data": [
        {"s": "BTCUSDT", "c": "101", "o": "100", "q": "1000"},
        {"s": "USDTUSDT", "c": "1", "o": "1", "q": "9999"},
    ]})
    row = collector.store.connection.execute("SELECT payload_json FROM breadth_snapshots ORDER BY id DESC LIMIT 1").fetchone()
    assert row is not None
    assert '"eligible_count":1' in row[0]
    collector.store.close()
