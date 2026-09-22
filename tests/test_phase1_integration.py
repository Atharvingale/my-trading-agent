from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings
from binance_data_layer.storage import MarketStore


def test_phase1_all_market_streams_are_configurable():
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",), enable_market_breadth=True))
    assert "!miniTicker@arr" in collector.spot_streams()
    assert "!miniTicker@arr" in collector.futures_streams()
    collector.store.close()


def test_store_persists_breadth_snapshot(tmp_path):
    store = MarketStore(tmp_path / "market.sqlite3")
    store.save_breadth({"eligible_count": 3, "advancing_count": 2, "declining_count": 1})
    row = store.connection.execute("SELECT payload_json FROM breadth_snapshots").fetchone()
    assert row is not None
    assert '"eligible_count":3' in row[0]
    store.close()
