from binance_data_layer.breadth import normalize_ticker_array, rank_trending_symbols
from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings


def test_rank_trending_symbols_prefers_liquid_movers_and_keeps_pinned():
    rows = normalize_ticker_array({"data": [
        {"s": "BTCUSDT", "c": "101", "o": "100", "q": "100000000"},
        {"s": "SOLUSDT", "c": "120", "o": "100", "q": "10000000"},
        {"s": "XRPUSDT", "c": "105", "o": "100", "q": "50000000"},
        {"s": "TINYUSDT", "c": "150", "o": "100", "q": "1000"},
    ]}, quote_assets={"USDT"})
    selected = rank_trending_symbols(rows, pinned=("BTCUSDT",), top_n=2, min_quote_volume=100000)
    assert selected[0] == "BTCUSDT"
    assert "SOLUSDT" in selected
    assert "TINYUSDT" not in selected


def test_dynamic_universe_updates_detailed_streams():
    collector = BinanceCollector(Settings(
        symbols=("BTCUSDT",), dynamic_universe_enabled=True,
        dynamic_universe_size=3, dynamic_min_quote_volume=1000,
    ))
    collector._update_dynamic_universe([
        {"symbol": "BTCUSDT", "price": 101, "open": 100, "change_pct": 1, "quote_volume": 100000},
        {"symbol": "SOLUSDT", "price": 120, "open": 100, "change_pct": 20, "quote_volume": 10000},
        {"symbol": "XRPUSDT", "price": 110, "open": 100, "change_pct": 10, "quote_volume": 9000},
    ])
    assert "SOLUSDT" in collector.active_symbols
    assert "solusdt@aggTrade" in collector.spot_streams()
    assert "solusdt@markPrice@1s" in collector.futures_streams()
    collector.store.close()


def test_top_coins_endpoint_returns_ranked_universe(tmp_path):
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from binance_data_layer.api import create_app

    async def scenario():
        collector = BinanceCollector(Settings(
            database_path=str(tmp_path / "top.sqlite3"), symbols=("BTCUSDT",),
            dynamic_min_quote_volume=1000,
        ))
        collector._update_dynamic_universe([
            {"symbol": "BTCUSDT", "price": 101, "open": 100, "change_pct": 1, "quote_volume": 100000},
            {"symbol": "SOLUSDT", "price": 120, "open": 100, "change_pct": 20, "quote_volume": 10000},
        ])
        async with TestServer(create_app(collector)) as server:
            async with TestClient(server) as client:
                response = await client.get("/market/top-coins")
                assert response.status == 200
                payload = await response.json()
                assert payload["symbols"][0] == "BTCUSDT"
                assert payload["symbols"][1] == "SOLUSDT"
        collector.store.close()

    asyncio.run(scenario())
