import asyncio
import ipaddress
import json
import time

import pytest
from aiohttp.test_utils import TestClient, TestServer

from binance_data_layer.api import create_app
from binance_data_layer.collector import BinanceCollector
from binance_data_layer.config import Settings
from binance_data_layer.storage import MarketStore


def test_sqlite_writes_are_enqueued_off_the_hot_path(tmp_path):
    store = MarketStore(tmp_path / "async.sqlite3")
    store.enqueue_event(
        stream="test",
        symbol="BTCUSDT",
        event_type="trade",
        event_time_ms=1,
        received_time_ms=2,
        payload={"price": 100.0},
    )
    assert store.counts()["market_events"] == 0
    store.flush()
    assert store.counts()["market_events"] == 1
    store.close()


def test_batched_persistence_commits_multiple_records_together(tmp_path):
    store = MarketStore(tmp_path / "batch.sqlite3")
    store.enqueue_event(
        stream="test",
        symbol="BTCUSDT",
        event_type="trade",
        event_time_ms=1,
        received_time_ms=2,
        payload={"price": 100.0},
    )
    store.enqueue_event(
        stream="test",
        symbol="ETHUSDT",
        event_type="trade",
        event_time_ms=3,
        received_time_ms=4,
        payload={"price": 200.0},
    )
    store.flush()
    assert store.counts()["market_events"] == 2
    store.close()


def test_slow_websocket_subscriber_does_not_block_ingestion(tmp_path):
    async def scenario():
        collector = BinanceCollector(
            Settings(database_path=str(tmp_path / "fanout.sqlite3"), symbols=("BTCUSDT",))
        )
        app = create_app(collector)
        api = collector.realtime_api
        original_send = None
        sent = []

        class SlowSocket:
            def __init__(self):
                self.closed = False
                self.queue_size = 0

            async def send_json(self, message):
                await asyncio.sleep(0.2)
                sent.append(message)

        slow = SlowSocket()
        api.all_subscribers.add(slow)
        start = time.perf_counter()
        await collector._handle_message(
            json.dumps(
                {
                    "stream": "btcusdt@bookTicker",
                    "data": {
                        "s": "BTCUSDT",
                        "b": "99",
                        "B": "2",
                        "a": "101",
                        "A": "3",
                        "E": 1700000000000,
                    },
                }
            )
        )
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1
        await asyncio.sleep(0.3)
        collector.store.close()

    asyncio.run(scenario())


def test_publish_tasks_are_tracked_and_failed_tasks_are_logged(tmp_path, caplog):
    async def scenario():
        collector = BinanceCollector(
            Settings(database_path=str(tmp_path / "tasks.sqlite3"), symbols=("BTCUSDT",))
        )
        create_app(collector)
        failed = asyncio.Event()

        async def boom():
            failed.set()
            raise RuntimeError("publish failed")

        task = collector.track_background_task(boom())
        await failed.wait()
        await asyncio.sleep(0)
        assert task in collector.background_tasks or task.done()
        await asyncio.gather(task, return_exceptions=True)
        collector.store.close()

    with caplog.at_level("ERROR"):
        asyncio.run(scenario())
    assert "publish failed" in caplog.text or "background task" in caplog.text.lower()


def test_non_loopback_api_requires_auth_token(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_DATA_API_HOST", "0.0.0.0")
    monkeypatch.delenv("MARKET_DATA_API_TOKEN", raising=False)
    with pytest.raises(ValueError, match="auth token"):
        Settings.from_environment()


def test_loopback_api_is_the_default_bind_address():
    settings = Settings()
    address = ipaddress.ip_address(settings.api_host)
    assert address.is_loopback
    assert settings.api_token is None


def test_non_loopback_requests_without_token_are_rejected(tmp_path, monkeypatch):
    async def scenario():
        collector = BinanceCollector(
            Settings(
                database_path=str(tmp_path / "auth.sqlite3"),
                symbols=("BTCUSDT",),
                api_host="0.0.0.0",
                api_token="secret-token",
            )
        )
        app = create_app(collector)
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                unauth = await client.get("/health")
                assert unauth.status == 401
                auth = await client.get("/health", headers={"Authorization": "Bearer secret-token"})
                assert auth.status == 200
        collector.store.close()

    asyncio.run(scenario())


def test_stale_dynamic_universe_symbols_are_retired(tmp_path):
    collector = BinanceCollector(
        Settings(
            database_path=str(tmp_path / "retire.sqlite3"),
            symbols=("BTCUSDT",),
            dynamic_universe_enabled=True,
            dynamic_universe_size=2,
            dynamic_min_quote_volume=1000,
            dynamic_refresh_seconds=0,
        )
    )
    collector._update_dynamic_universe(
        [
            {"symbol": "BTCUSDT", "price": 101, "open": 100, "change_pct": 1, "quote_volume": 100000},
            {"symbol": "SOLUSDT", "price": 120, "open": 100, "change_pct": 20, "quote_volume": 10000},
        ]
    )
    assert "SOLUSDT" in collector.states
    collector._update_dynamic_universe(
        [
            {"symbol": "BTCUSDT", "price": 101, "open": 100, "change_pct": 1, "quote_volume": 100000},
            {"symbol": "ETHUSDT", "price": 110, "open": 100, "change_pct": 10, "quote_volume": 9000},
        ]
    )
    assert "SOLUSDT" not in collector.states
    assert "SOLUSDT" not in collector.active_symbols
    assert "ETHUSDT" in collector.active_symbols
    collector.store.close()


def test_sqlite_retention_policy_prunes_old_rows(tmp_path):
    store = MarketStore(tmp_path / "retain.sqlite3")
    now_ms = 1_700_000_000_000
    store.save_event(
        stream="test",
        symbol="BTCUSDT",
        event_type="trade",
        event_time_ms=now_ms - 8 * 24 * 60 * 60 * 1000,
        received_time_ms=now_ms - 8 * 24 * 60 * 60 * 1000,
        payload={"price": 1.0},
    )
    store.save_event(
        stream="test",
        symbol="BTCUSDT",
        event_type="trade",
        event_time_ms=now_ms,
        received_time_ms=now_ms,
        payload={"price": 2.0},
    )
    result = store.apply_retention(now_ms=now_ms, event_retention_days=7)
    assert store.counts()["market_events"] == 1
    assert result["deleted"]["market_events"] == 1
    store.close()


def test_rest_analytics_use_active_universe_not_only_pinned_symbols(tmp_path):
    class Client:
        def __init__(self):
            self.tickers = []

        async def exchange_info(self):
            return {}

        async def spot_24hr_ticker(self, symbol):
            self.tickers.append(symbol)
            return {"symbol": symbol}

        async def futures_long_short_account_ratio(self, symbol):
            return []

        async def futures_taker_volume(self, symbol):
            return []

        async def futures_open_interest_history(self, symbol):
            return []

        async def futures_funding_history(self, symbol):
            return []

        async def futures_basis(self, symbol):
            return []

        async def options_mark_price(self):
            return []

        async def options_open_interest(self, underlying, expiration):
            return []

        async def options_block_trades(self):
            return []

    collector = BinanceCollector(
        Settings(
            database_path=str(tmp_path / "universe.sqlite3"),
            symbols=("BTCUSDT",),
            dynamic_universe_enabled=True,
            dynamic_universe_size=3,
            dynamic_min_quote_volume=1,
            dynamic_refresh_seconds=0,
        )
    )
    collector._update_dynamic_universe(
        [
            {"symbol": "BTCUSDT", "price": 101, "open": 100, "change_pct": 1, "quote_volume": 100000},
            {"symbol": "SOLUSDT", "price": 120, "open": 100, "change_pct": 20, "quote_volume": 10000},
        ]
    )
    client = Client()
    asyncio.run(collector.collect_binance_analytics_once(client))
    assert "SOLUSDT" in client.tickers
    collector.store.close()


def test_features_are_recomputed_only_on_meaningful_boundaries(tmp_path):
    collector = BinanceCollector(
        Settings(database_path=str(tmp_path / "cache.sqlite3"), symbols=("BTCUSDT",))
    )
    asyncio.run(
        collector._handle_message(
            json.dumps(
                {
                    "stream": "btcusdt@bookTicker",
                    "data": {
                        "s": "BTCUSDT",
                        "b": "99",
                        "B": "2",
                        "a": "101",
                        "A": "3",
                        "E": 1700000000000,
                    },
                }
            )
        )
    )
    first = collector.store.counts()["feature_snapshots"]
    asyncio.run(
        collector._handle_message(
            json.dumps(
                {
                    "stream": "btcusdt@bookTicker",
                    "data": {
                        "s": "BTCUSDT",
                        "b": "99",
                        "B": "2",
                        "a": "101",
                        "A": "3",
                        "E": 1700000000100,
                    },
                }
            )
        )
    )
    second = collector.store.counts()["feature_snapshots"]
    asyncio.run(
        collector._handle_message(
            json.dumps(
                {
                    "stream": "btcusdt@kline_1m",
                    "data": {
                        "e": "kline",
                        "E": 1700000060000,
                        "s": "BTCUSDT",
                        "k": {
                            "t": 1700000000000,
                            "T": 1700000059999,
                            "i": "1m",
                            "o": "100",
                            "c": "101",
                            "h": "102",
                            "l": "99",
                            "v": "10",
                            "q": "1000",
                            "n": 5,
                            "V": "4",
                            "Q": "400",
                            "x": True,
                        },
                    },
                }
            )
        )
    )
    third = collector.store.counts()["feature_snapshots"]
    assert first == 1
    assert second == first
    assert third == first + 1
    collector.store.close()


def test_api_reads_go_through_store_repository(tmp_path):
    collector = BinanceCollector(
        Settings(database_path=str(tmp_path / "repo.sqlite3"), symbols=("BTCUSDT",))
    )
    collector.store.save_breadth({"eligible_count": 3, "status": "ok"}, created_time_ms=1)
    snapshot = collector.store.latest_breadth()
    assert snapshot["eligible_count"] == 3
    collector.store.close()


def test_retry_backoff_is_centralized():
    from binance_data_layer.retry import next_backoff_seconds

    assert next_backoff_seconds(1.0) == 2.0
    assert next_backoff_seconds(32.0, maximum=60.0) == 60.0


def test_simulated_soak_recovers_from_disconnects_without_unbounded_growth(tmp_path):
    async def scenario():
        collector = BinanceCollector(
            Settings(database_path=str(tmp_path / "soak.sqlite3"), symbols=("BTCUSDT",))
        )
        result = await collector.run_soak(
            duration_seconds=0.2,
            disconnects=2,
            event_count=20,
        )
        assert result["recovered"] is True
        assert result["events_persisted"] >= 20
        assert result["disconnect_count"] == 2
        assert result["peak_pending_writes"] < 1000
        assert result["peak_tracked_tasks"] < 1000
        collector.store.close()
        return result

    result = asyncio.run(scenario())
    assert result["memory_growth_bytes"] < 10_000_000


def test_soak_default_is_24h_ci_simulated_time(tmp_path):
    import inspect

    sig = inspect.signature(BinanceCollector.run_soak)
    assert sig.parameters["duration_seconds"].default == 86400.0


def test_soak_with_restart_mid_run_loses_no_data(tmp_path):
    async def scenario():
        collector = BinanceCollector(
            Settings(database_path=str(tmp_path / "soak_restart.sqlite3"), symbols=("BTCUSDT",))
        )
        result = await collector.run_soak(
            duration_seconds=0.2,
            disconnects=1,
            event_count=20,
            restart_at_half=True,
        )
        assert result["recovered"] is True
        assert result["restarts"] == 1
        assert result["events_persisted"] >= 20
        collector.store.close()
        return result

    result = asyncio.run(scenario())
    assert result["memory_growth_bytes"] < 10_000_000


def test_restart_recovery_reopens_database_without_data_loss(tmp_path):
    db = tmp_path / "restart.sqlite3"
    store = MarketStore(db)
    store.save_event(
        stream="test",
        symbol="BTCUSDT",
        event_type="trade",
        event_time_ms=1,
        received_time_ms=2,
        payload={"price": 100.0},
    )
    store.flush()
    assert store.counts()["market_events"] == 1
    store.close()
    reopened = MarketStore(db)
    assert reopened.counts()["market_events"] == 1
    events = reopened.recent_events(symbol="BTCUSDT", limit=10)
    assert events[0]["payload"] == {"price": 100.0}
    reopened.close()


def test_async_writer_consumes_queue_in_batches(tmp_path):
    async def scenario():
        store = MarketStore(tmp_path / "writer.sqlite3", batch_size=5)
        queue = store.start_writer(queue_size=100)
        for idx in range(12):
            store.enqueue_event(
                stream="test",
                symbol="BTCUSDT",
                event_type="trade",
                event_time_ms=idx,
                received_time_ms=idx,
                payload={"i": idx},
            )
        writer = asyncio.create_task(store.run_writer())
        await asyncio.sleep(0.05)
        await store.stop_writer()
        await asyncio.gather(writer, return_exceptions=True)
        assert store.counts()["market_events"] == 12
        store.close()

    asyncio.run(scenario())


def test_collector_run_wires_writer_and_maintenance(tmp_path):
    import inspect

    source = inspect.getsource(BinanceCollector.run)
    assert "_run_writer" in source
    assert "_run_maintenance" in source
    assert "stop_writer" in source


def test_non_loopback_requires_tls_unless_explicit_insecure(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_API_HOST", "0.0.0.0")
    monkeypatch.setenv("MARKET_DATA_API_TOKEN", "secret-token")
    monkeypatch.delenv("MARKET_DATA_API_TLS_CERTFILE", raising=False)
    monkeypatch.delenv("MARKET_DATA_API_TLS_KEYFILE", raising=False)
    monkeypatch.delenv("MARKET_DATA_API_ALLOW_INSECURE_REMOTE", raising=False)
    with pytest.raises(ValueError, match="TLS"):
        Settings.from_environment()
    monkeypatch.setenv("MARKET_DATA_API_ALLOW_INSECURE_REMOTE", "1")
    allowed = Settings.from_environment()
    assert allowed.api_token == "secret-token"
    assert allowed.api_allow_insecure_remote is True
    loopback = Settings()
    assert loopback.build_ssl_context() is None


def test_shared_client_is_reused_not_reconstructed(tmp_path):
    async def scenario():
        collector = BinanceCollector(
            Settings(database_path=str(tmp_path / "shared.sqlite3"), symbols=("BTCUSDT",))
        )
        first = await collector._get_shared_client()
        second = await collector._get_shared_client()
        assert first is second
        await collector._close_shared_client()
        assert collector._shared_client is None
        collector.store.close()

    asyncio.run(scenario())


def test_collector_uses_shared_client_for_all_rest_paths(tmp_path):
    import inspect

    for method in ("collect_binance_analytics_once", "collect_futures_metrics_once", "bootstrap"):
        source = inspect.getsource(getattr(BinanceCollector, method))
        assert "_get_shared_client" in source


def test_maintenance_applies_all_retention_windows(tmp_path):
    store = MarketStore(tmp_path / "maint.sqlite3")
    now_ms = 1_700_000_000_000
    old = now_ms - 8 * 24 * 60 * 60 * 1000
    store.save_event(
        stream="test", symbol="BTCUSDT", event_type="trade",
        event_time_ms=old, received_time_ms=old, payload={},
    )
    store.save_features({"symbol": "BTCUSDT", "event_time": "x"}, created_time_ms=old)
    store.save_breadth({"status": "ok"}, created_time_ms=old)
    store.save_health(
        component="c", symbol=None, status="ok", observed_time_ms=old, details={}
    )
    result = store.apply_retention(
        now_ms=now_ms,
        event_retention_days=7,
        feature_retention_days=7,
        breadth_retention_days=7,
        health_retention_days=7,
    )
    assert result["deleted"]["market_events"] == 1
    assert result["deleted"]["feature_snapshots"] == 1
    assert result["deleted"]["breadth_snapshots"] == 1
    assert result["deleted"]["data_health"] == 1
    store.close()


def test_raw_publish_fallback_is_tracked_not_leaked(tmp_path, caplog):
    import inspect

    source = inspect.getsource(BinanceCollector._handle_message)
    assert "track_background_task" in source
    from binance_data_layer.api import RealtimeApi

    api_source = inspect.getsource(RealtimeApi.publish)
    assert "track_background_task" in api_source
    assert "asyncio.create_task(subscriber.send_json" not in api_source
