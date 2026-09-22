import asyncio

from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


class Client:
    def __init__(self):
        self.option_mark_calls = 0
        self.option_oi_calls = 0

    async def exchange_info(self): return {}
    async def spot_24hr_ticker(self, symbol): return {}
    async def futures_long_short_account_ratio(self, symbol): return []
    async def futures_taker_volume(self, symbol): return []
    async def futures_open_interest_history(self, symbol): return []
    async def futures_funding_history(self, symbol): return []
    async def futures_basis(self, symbol): return []
    async def options_mark_price(self):
        self.option_mark_calls += 1
        return [{"symbol": "BTC-260925-100000-C"}]
    async def options_open_interest(self, underlying, expiration):
        self.option_oi_calls += 1
        return []
    async def options_block_trades(self): return []


class Store:
    def __init__(self): self.events = []
    def save_event(self, **kwargs): self.events.append(kwargs)


def test_options_are_fetched_once_for_multiple_configured_symbols():
    client = Client()
    collector = BinanceCollector(Settings(symbols=("BTCUSDT", "ETHUSDT")), store=Store())
    asyncio.run(collector.collect_binance_analytics_once(client))
    assert client.option_mark_calls == 1
    assert client.option_oi_calls == 1
