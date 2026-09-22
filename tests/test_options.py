import asyncio

from binance_data_layer.binance_client import BinancePublicClient
from binance_data_layer.collector import normalize_event


def test_normalize_options_mark_event():
    event = normalize_event(
        "BTC-260925-100000-C@markPrice",
        {
            "e": "markPrice",
            "E": 1700000000123,
            "s": "BTC-260925-100000-C",
            "mp": "1200.5",
            "b": "0.75",
            "a": "0.80",
            "bo": "1100.0",
            "ao": "1300.0",
            "i": "100500.0",
            "P": "100500.0",
            "d": "0.55",
            "t": "-20.0",
            "g": "0.0001",
            "v": "150.0",
        },
    )
    assert event["event_type"] == "optionMarkPrice"
    assert event["symbol"] == "BTC-260925-100000-C"
    assert event["payload"]["mark_iv"] == 0.75
    assert event["payload"]["delta"] == 0.55


def test_normalize_options_open_interest_event():
    event = normalize_event(
        "BTC-260925-100000-C@openInterest",
        {
            "e": "openInterest",
            "E": 1700000000123,
            "s": "BTC-260925-100000-C",
            "o": "12.5",
            "h": "1250000.0",
        },
    )
    assert event["event_type"] == "optionOpenInterest"
    assert event["payload"]["open_interest_contracts"] == 12.5
    assert event["payload"]["open_interest_usd"] == 1250000.0


def test_options_client_uses_options_base_url():
    client = BinancePublicClient(
        spot_base_url="https://spot.example",
        futures_base_url="https://futures.example",
        options_base_url="https://options.example",
    )
    assert client.options_base_url == "https://options.example"


def test_options_urls_are_public_market_data():
    client = BinancePublicClient(
        spot_base_url="https://spot.example",
        futures_base_url="https://futures.example",
        options_base_url="https://options.example",
    )
    calls = []

    async def fake_get(base_url, path, params=None):
        calls.append((base_url, path, params))
        return []

    client._get = fake_get

    async def run():
        await client.options_mark_price("BTC-260925-100000-C")
        await client.options_open_interest("BTC", "260925")
        await client.options_block_trades("BTC-260925-100000-C")

    asyncio.run(run())
    assert calls == [
        ("https://options.example", "/eapi/v1/mark", {"symbol": "BTC-260925-100000-C"}),
        ("https://options.example", "/eapi/v1/openInterest", {"underlyingAsset": "BTC", "expiration": "260925"}),
        ("https://options.example", "/eapi/v1/blockTrades", {"symbol": "BTC-260925-100000-C"}),
    ]
