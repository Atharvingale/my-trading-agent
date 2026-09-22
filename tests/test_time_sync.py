import asyncio

from binance_data_layer.binance_client import BinancePublicClient


def test_signed_requests_include_recv_window_and_synced_timestamp():
    client = BinancePublicClient(
        spot_base_url="https://spot.example",
        futures_base_url="https://futures.example",
        api_key="key",
        api_secret="secret",
    )
    client.time_offset_ms = 1234
    signed = client.build_signed_params({"recvWindow": 5000})
    assert signed["recvWindow"] == 5000
    assert signed["timestamp"] > 0
    assert "signature" in signed


def test_sync_time_uses_server_time():
    client = BinancePublicClient(
        spot_base_url="https://spot.example",
        futures_base_url="https://futures.example",
    )

    async def fake_get(base_url, path, params=None, headers=None):
        assert path == "/api/v3/time"
        return {"serverTime": 1700000000000}

    client._get = fake_get
    asyncio.run(client.sync_time())
    assert client.time_offset_ms != 0
