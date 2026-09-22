import time

from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


def test_cross_exchange_confirmation_is_persisted_when_tickers_arrive():
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",), enable_cross_exchange=True))
    now = int(time.time() * 1000)
    state = collector.states["BTCUSDT"]
    state.last_price = 100.0
    state.last_event_time_ms = now
    collector._record_cross_exchange_snapshot({"source": "coinbase", "symbol": "BTCUSDT", "mid_price": 100.0, "received_time_ms": now})
    collector._record_cross_exchange_snapshot({"source": "kraken", "symbol": "BTCUSDT", "mid_price": 100.01, "received_time_ms": now})
    collector._record_cross_exchange_snapshot({"source": "okx", "symbol": "BTCUSDT", "mid_price": 99.99, "received_time_ms": now})
    row = collector.store.connection.execute(
        "SELECT event_type, payload_json FROM market_events WHERE event_type = 'crossExchangeConfirmation' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row[0] == "crossExchangeConfirmation"
    assert "CONFIRMED" in row[1]
    collector.store.close()
