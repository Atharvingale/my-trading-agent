import asyncio

from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


def test_private_user_stream_is_disabled_without_credentials():
    class Store:
        def __init__(self):
            self.events = []

        def save_event(self, **kwargs):
            self.events.append(kwargs)

    store = Store()
    collector = BinanceCollector(Settings(), store=store)
    asyncio.run(collector.collect_private_user_event_once('{"e":"outboundAccountPosition"}'))

    assert store.events[0]["event_type"] == "privateUserEvent"
    assert store.events[0]["payload"]["status"] == "N/A"


def test_private_user_event_is_persisted_when_credentials_exist():
    class Store:
        def __init__(self):
            self.events = []

        def save_event(self, **kwargs):
            self.events.append(kwargs)

    store = Store()
    collector = BinanceCollector(Settings(api_key="key", api_secret="secret"), store=store)
    asyncio.run(
        collector.collect_private_user_event_once(
            '{"e":"executionReport","E":1700000000000,"s":"BTCUSDT","X":"FILLED"}'
        )
    )

    assert store.events[0]["event_type"] == "executionReport"
    assert store.events[0]["symbol"] == "BTCUSDT"
    assert store.events[0]["payload"]["X"] == "FILLED"
