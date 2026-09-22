import time

from binance_data_layer.collector import BinanceCollector, MarketState
from binance_data_layer.config import Settings


def test_feature_snapshot_contains_multi_timeframe_alignment():
    state = MarketState("BTCUSDT")
    now = int(time.time() * 1000)
    for interval in ("1m", "5m", "15m", "1h", "4h"):
        state.candles.setdefault(interval, __import__('collections').deque(maxlen=500)).extend({
            "open_time_ms": now + i * 60_000,
            "open": 100 + i,
            "high": 101 + i,
            "low": 99 + i,
            "close": 100 + i,
            "volume": 10,
            "closed": True,
        } for i in range(30))
    state.last_event_time_ms = now
    snapshot = state.features()
    assert snapshot["multi_timeframe_alignment"]["state"] == "BULLISH"
    assert snapshot["multi_timeframe_alignment"]["confirmed_timeframes"] == 5


def test_cross_exchange_confirmation_includes_binance_reference():
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",), enable_cross_exchange=True))
    now = int(time.time() * 1000)
    state = collector.states["BTCUSDT"]
    state.last_price = 100.0
    state.last_event_time_ms = now
    collector._record_cross_exchange_snapshot({"source": "coinbase", "symbol": "BTCUSDT", "mid_price": 100.01, "received_time_ms": now})
    collector._record_cross_exchange_snapshot({"source": "kraken", "symbol": "BTCUSDT", "mid_price": 99.99, "received_time_ms": now})
    collector._record_cross_exchange_snapshot({"source": "okx", "symbol": "BTCUSDT", "mid_price": 100.00, "received_time_ms": now})
    row = collector.store.connection.execute(
        "SELECT payload_json FROM market_events WHERE event_type = 'crossExchangeConfirmation' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert '"binance"' in row[0]
    collector.store.close()
