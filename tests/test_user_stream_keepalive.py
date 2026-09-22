import asyncio

from binance_data_layer.binance_client import BinancePublicClient


def test_private_keepalive_uses_correct_spot_and_futures_paths():
    client = BinancePublicClient(
        spot_base_url="https://spot.example",
        futures_base_url="https://futures.example",
        api_key="test-key",
    )
    calls = []

    async def fake_put(base_url, path, params=None, headers=None):
        calls.append((base_url, path, params, headers))
        return {"listenKey": "same-key"}

    client._put = fake_put

    async def run():
        await client.spot_user_stream_keepalive("spot-key")
        await client.futures_user_stream_keepalive("futures-key")

    asyncio.run(run())
    assert calls == [
        ("https://spot.example", "/api/v3/userDataStream", {"listenKey": "spot-key"}, {"X-MBX-APIKEY": "test-key"}),
        ("https://futures.example", "/fapi/v1/listenKey", {"listenKey": "futures-key"}, {"X-MBX-APIKEY": "test-key"}),
    ]
