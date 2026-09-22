import asyncio

from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


class FakeFuturesClient:
    async def futures_open_interest(self, symbol: str):
        return {"symbol": symbol, "openInterest": "123.45", "time": 1700000000123}

    async def futures_mark_price(self, symbol: str):
        return {
            "symbol": symbol,
            "markPrice": "100.0",
            "indexPrice": "99.9",
            "lastFundingRate": "0.0001",
            "nextFundingTime": 1700003600000,
            "time": 1700000000123,
        }


class RecordingStore:
    def __init__(self):
        self.events = []

    def save_event(self, **kwargs):
        self.events.append(kwargs)


def test_futures_metric_snapshot_persists_open_interest_and_mark_data():
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",)), store=RecordingStore())
    asyncio.run(collector.collect_futures_metrics_once(FakeFuturesClient()))

    event_types = {event["event_type"] for event in collector.store.events}
    assert event_types == {"openInterest", "markPriceUpdate"}
    oi = next(event for event in collector.store.events if event["event_type"] == "openInterest")
    assert oi["payload"]["open_interest"] == 123.45
