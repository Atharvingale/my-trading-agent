import asyncio

from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


class FakeAnalyticsClient:
    async def futures_long_short_account_ratio(self, symbol, period="5m", limit=100):
        return [{"symbol": symbol, "longShortRatio": "1.25", "longAccount": "0.56", "shortAccount": "0.44", "timestamp": 1700000000000}]

    async def futures_taker_volume(self, symbol, period="5m", limit=100):
        return [{"symbol": symbol, "buySellRatio": "1.10", "buyVol": "110", "sellVol": "100", "timestamp": 1700000000000}]

    async def futures_basis(self, pair, contract_type="PERPETUAL", period="5m", limit=100):
        return [{"pair": pair, "contractType": contract_type, "basis": "0.5", "basisRate": "0.0001", "timestamp": 1700000000000}]

    async def futures_open_interest_history(self, symbol, period="5m", limit=100):
        return [{"symbol": symbol, "sumOpenInterest": "1000", "sumOpenInterestValue": "50000000", "timestamp": 1700000000000}]

    async def futures_funding_history(self, symbol, limit=100):
        return [{"symbol": symbol, "fundingRate": "0.0001", "fundingTime": 1700000000000, "markPrice": "50000"}]

    async def spot_24hr_ticker(self, symbol=None):
        return {"symbol": symbol, "lastPrice": "50000", "priceChangePercent": "1.5", "quoteVolume": "1000000"}

    async def exchange_info(self):
        return {"timezone": "UTC", "symbols": [{"symbol": "BTCUSDT", "status": "TRADING"}]}

    async def futures_mark_price(self, symbol=None):
        return {"symbol": symbol or "BTCUSDT", "markPrice": "50000", "indexPrice": "49990", "lastFundingRate": "0.0001", "nextFundingTime": 1700003600000, "time": 1700000000000}

    async def futures_open_interest(self, symbol):
        return {"symbol": symbol, "openInterest": "1000", "time": 1700000000000}

    async def options_mark_price(self, symbol=None):
        return [{"symbol": "BTC-260925-100000-C", "markPrice": "1200", "bidIV": "0.75", "askIV": "0.80", "markIV": "0.77", "delta": "0.55", "theta": "-20", "gamma": "0.0001", "vega": "150", "timestamp": 1700000000000}]

    async def options_open_interest(self, underlying_asset, expiration=None):
        return [{"symbol": "BTC-260925-100000-C", "sumOpenInterest": "12.5", "sumOpenInterestUsd": "1250000", "timestamp": 1700000000000}]

    async def options_block_trades(self, symbol=None):
        return [{"id": "block-1", "symbol": symbol or "BTC-260925-100000-C", "price": "1200", "quantity": "2", "side": "BUY", "timestamp": 1700000000000}]


class RecordingStore:
    def __init__(self):
        self.events = []
        self.health = []

    def save_event(self, **kwargs):
        self.events.append(kwargs)

    def save_health(self, **kwargs):
        self.health.append(kwargs)


def test_collect_binance_analytics_persists_public_metrics():
    store = RecordingStore()
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",)), store=store)
    asyncio.run(collector.collect_binance_analytics_once(FakeAnalyticsClient()))

    event_types = {event["event_type"] for event in store.events}
    assert {
        "exchangeInfo",
        "spot24hrTicker",
        "futuresLongShortRatio",
        "futuresTakerVolume",
        "futuresBasis",
        "futuresOpenInterestHistory",
        "futuresFundingRate",
        "optionMarkPrice",
        "optionOpenInterest",
        "optionBlockTrade",
    } <= event_types
