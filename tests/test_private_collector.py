import asyncio

from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


class PrivateClient:
    async def spot_account(self):
        return {"makerCommission": 10, "balances": [{"asset": "USDT", "free": "100", "locked": "0"}]}

    async def spot_open_orders(self, symbol=None):
        return [{"symbol": symbol or "BTCUSDT", "status": "NEW", "orderId": 1}]

    async def futures_account(self):
        return {"totalWalletBalance": "100", "positions": [{"symbol": "BTCUSDT", "positionAmt": "0"}]}

    async def futures_open_orders(self, symbol=None):
        return [{"symbol": symbol or "BTCUSDT", "status": "NEW", "orderId": 2}]


def test_private_snapshot_persists_account_orders_positions():
    class Store:
        def __init__(self):
            self.events = []

        def save_event(self, **kwargs):
            self.events.append(kwargs)

    store = Store()
    collector = BinanceCollector(
        Settings(symbols=("BTCUSDT",), api_key="key", api_secret="secret"),
        store=store,
    )
    result = asyncio.run(collector.collect_private_account_once(PrivateClient()))

    assert result["status"] == "ok"
    assert {event["event_type"] for event in store.events} == {
        "privateSpotAccount",
        "privateSpotOpenOrders",
        "privateFuturesAccount",
        "privateFuturesOpenOrders",
    }


def test_private_snapshot_is_na_when_only_one_credential_exists():
    class Store:
        def __init__(self):
            self.events = []

        def save_event(self, **kwargs):
            self.events.append(kwargs)

    store = Store()
    collector = BinanceCollector(Settings(api_key="key"), store=store)
    result = asyncio.run(collector.collect_private_account_once(PrivateClient()))

    assert result["status"] == "N/A"
    assert store.events[0]["payload"]["status"] == "N/A"
