import asyncio

from binance_data_layer.binance_client import BinancePublicClient
from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


def test_missing_credentials_report_na_without_private_calls():
    class FailIfCalled:
        async def spot_account(self):
            raise AssertionError("private endpoint must not be called")

    class Store:
        def __init__(self):
            self.events = []

        def save_event(self, **kwargs):
            self.events.append(kwargs)

    store = Store()
    collector = BinanceCollector(Settings(symbols=("BTCUSDT",)), store=store)
    result = asyncio.run(collector.collect_private_account_once(FailIfCalled()))

    assert result["status"] == "N/A"
    assert result["reason"] == "BINANCE_API_CREDENTIALS_NOT_PROVIDED"
    assert len(store.events) == 1
    assert store.events[0]["payload"] == {
        "status": "N/A",
        "reason": "BINANCE_API_CREDENTIALS_NOT_PROVIDED",
    }


def test_private_client_credentials_are_optional():
    client = BinancePublicClient(
        spot_base_url="https://spot.example",
        futures_base_url="https://futures.example",
    )
    assert client.credentials_available is False

    authenticated = BinancePublicClient(
        spot_base_url="https://spot.example",
        futures_base_url="https://futures.example",
        api_key="test-key",
        api_secret="test-secret",
    )
    assert authenticated.credentials_available is True


def test_private_signature_does_not_include_secret_in_query():
    client = BinancePublicClient(
        spot_base_url="https://spot.example",
        futures_base_url="https://futures.example",
        api_key="test-key",
        api_secret="test-secret",
    )
    signed = client.build_signature({"timestamp": 1700000000000, "recvWindow": 5000})
    assert "signature" in signed
    assert "test-secret" not in signed["signature"]
    assert signed["timestamp"] == 1700000000000
