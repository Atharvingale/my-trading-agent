import asyncio
import json

from aiohttp.test_utils import TestClient, TestServer

from binance_data_layer.api import create_app
from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


def test_rest_snapshot_and_health_endpoints(tmp_path):
    async def scenario():
        collector = BinanceCollector(Settings(database_path=str(tmp_path / "api.sqlite3"), symbols=("BTCUSDT",)))
        state = collector.states["BTCUSDT"]
        state.last_price = 100.0
        state.last_event_time_ms = 1_700_000_000_000
        app = create_app(collector)
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                health = await client.get("/health")
                snapshot = await client.get("/market/BTCUSDT/snapshot")
                assert health.status == 200
                assert (await health.json())["status"] == "ok"
                assert (await snapshot.json())["symbol"] == "BTCUSDT"
                assert (await snapshot.json())["last_price"] == 100.0
        collector.store.close()
    asyncio.run(scenario())


def test_websocket_receives_live_event(tmp_path):
    async def scenario():
        collector = BinanceCollector(Settings(database_path=str(tmp_path / "ws.sqlite3"), symbols=("BTCUSDT",)))
        app = create_app(collector)
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                ws = await client.ws_connect("/ws?symbol=BTCUSDT")
                connected = await ws.receive_json(timeout=2)
                assert connected["type"] == "connected"
                await collector._handle_message(json.dumps({
                    "stream": "btcusdt@bookTicker",
                    "data": {"s": "BTCUSDT", "b": "99", "B": "2", "a": "101", "A": "3", "E": 1700000000000},
                }))
                message = await ws.receive_json(timeout=2)
                assert message["type"] == "market_event"
                assert message["symbol"] == "BTCUSDT"
                await ws.close()
        collector.store.close()
    asyncio.run(scenario())
