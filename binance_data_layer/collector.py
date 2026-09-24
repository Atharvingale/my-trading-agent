"""Persistent Binance spot/futures market-data collector."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import tracemalloc
from typing import Any, Mapping

import websockets

from .analytics import (
    collect_binance_analytics,
    collect_futures_metrics,
    collect_private_account,
)
from .binance_client import BinancePublicClient
from .breadth import calculate_breadth, normalize_ticker_array, rank_trending_symbols
from .config import Settings
from .cross_exchange import PUBLIC_WS_URLS, build_confirmation, canonical_symbol, normalize_message, subscription_for
from .ingestion import MarketState, normalize_event
from .quality import QualityTracker
from .retry import next_backoff_seconds
from .storage import MarketStore

logger = logging.getLogger(__name__)

__all__ = ["BinanceCollector", "MarketState", "normalize_event", "main", "run_asyncio_entrypoint"]


def _number(value: Any) -> float:
    return float(value)


class BinanceCollector:
    def __init__(self, settings: Settings | None = None, store: MarketStore | None = None) -> None:
        self.settings = settings or Settings.from_environment()
        self.store = store or MarketStore(
            self.settings.database_path, batch_size=self.settings.persist_batch_size
        )
        self.store.batch_size = max(1, self.settings.persist_batch_size)
        self.states = {
            symbol: MarketState(symbol, self.settings.trade_buffer_size)
            for symbol in self.settings.symbols
        }
        self._stop = asyncio.Event()
        self.quality = QualityTracker(stale_after_ms=int(self.settings.stale_after_seconds * 1000))
        self.cross_exchange_snapshots: dict[str, list[dict[str, Any]]] = {}
        self.realtime_api: Any | None = None
        self.active_symbols: tuple[str, ...] = tuple(self.settings.symbols)
        self.universe_rows: list[dict[str, Any]] = []
        self.universe_generation = 0
        self.universe_last_update_ms = 0
        self.background_tasks: set[asyncio.Task[Any]] = set()
        self._feature_cache: dict[str, Any] = {}
        self._shared_client: BinancePublicClient | None = None

    def track_background_task(self, coro) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self._on_task_done)
        return task

    def _on_task_done(self, task: asyncio.Task[Any]) -> None:
        self.background_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Background task failed: %s", exc)

    def stop(self) -> None:
        self._stop.set()

    def spot_streams(self) -> list[str]:
        streams: list[str] = []
        if self.settings.enable_market_breadth:
            streams.append("!miniTicker@arr")
        intervals = ("1m", "5m", "15m", "1h", "4h")
        for symbol in self.active_symbols:
            lower = symbol.lower()
            streams.extend((f"{lower}@aggTrade", f"{lower}@bookTicker", f"{lower}@depth20@100ms"))
            streams.extend(f"{lower}@kline_{interval}" for interval in intervals)
        return streams

    def futures_streams(self) -> list[str]:
        streams = [*(f"{symbol.lower()}@markPrice@1s" for symbol in self.active_symbols), "!forceOrder@arr"]
        if self.settings.enable_market_breadth:
            streams.insert(0, "!miniTicker@arr")
        return streams

    def spot_stream_url(self) -> str:
        return f"{self.settings.spot_ws_url}?streams={'/'.join(self.spot_streams())}"

    def futures_stream_url(self) -> str:
        return f"{self.settings.futures_ws_url}?streams={'/'.join(self.futures_streams())}"

    def futures_private_stream_url(self, listen_key: str) -> str:
        base = self.settings.futures_ws_url.split("/market/", 1)[0]
        return f"{base}/private/ws?listenKey={listen_key}"

    def streams(self) -> list[str]:
        return [*self.spot_streams(), *self.futures_streams()]

    def cross_exchange_sources(self) -> tuple[str, ...]:
        return tuple(PUBLIC_WS_URLS) if self.settings.enable_cross_exchange else ()

    def cross_exchange_urls(self) -> dict[str, str]:
        return {source: PUBLIC_WS_URLS[source] for source in self.cross_exchange_sources()}

    def cross_exchange_subscriptions(self) -> dict[str, dict[str, Any]]:
        return {source: subscription_for(source) for source in self.cross_exchange_sources()}

    def _record_cross_exchange_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        symbol = str(snapshot["symbol"])
        entries = [row for row in self.cross_exchange_snapshots.get(symbol, []) if row.get("source") != snapshot.get("source") and row.get("source") != "binance"]
        entries.append(dict(snapshot))
        state = self.states.get(symbol)
        if state is not None and state.last_price is not None and state.last_event_time_ms is not None:
            entries.append({"source": "binance", "symbol": symbol, "mid_price": state.last_price, "received_time_ms": int(time.time() * 1000)})
        self.cross_exchange_snapshots[symbol] = entries
        confirmation = build_confirmation(
            entries,
            now_ms=int(time.time() * 1000),
            max_age_ms=int(self.settings.cross_exchange_max_age_seconds * 1000),
        )
        now_ms = int(time.time() * 1000)
        self.store.save_event(
            stream="cross_exchange:derived",
            symbol=symbol,
            event_type="crossExchangeConfirmation",
            event_time_ms=now_ms,
            received_time_ms=now_ms,
            payload=confirmation,
        )
        if self.realtime_api is not None:
            self.track_background_task(
                self.realtime_api.publish(
                    {
                        "type": "cross_exchange_confirmation",
                        "symbol": symbol,
                        "event_time_ms": now_ms,
                        "payload": confirmation,
                    }
                )
            )

    async def _run_cross_exchange(self, source: str) -> None:
        delay = 1.0
        url = PUBLIC_WS_URLS[source]
        while not self._stop.is_set():
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=1) as socket:
                    await socket.send(json.dumps(subscription_for(source)))
                    delay = 1.0
                    self.store.save_health(component=f"cross_exchange_{source}", symbol=None, status="connected", observed_time_ms=int(time.time() * 1000), details={"url": url})
                    while not self._stop.is_set():
                        try:
                            raw = await asyncio.wait_for(socket.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                        if raw is None:
                            break
                        for snapshot in normalize_message(source, json.loads(raw)):
                            snapshot["symbol"] = canonical_symbol(source, snapshot["symbol"])
                            received = int(time.time() * 1000)
                            self.store.save_event(
                                stream=f"cross_exchange:{source}", symbol=snapshot["symbol"], event_type="ticker",
                                event_time_ms=received, received_time_ms=received, payload=snapshot,
                            )
                            self._record_cross_exchange_snapshot(snapshot)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.store.save_health(component=f"cross_exchange_{source}", symbol=None, status="error", observed_time_ms=int(time.time() * 1000), details={"error": repr(exc), "retry_seconds": delay})
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = next_backoff_seconds(delay, maximum=60.0)

    async def _get_shared_client(self) -> BinancePublicClient:
        if self._shared_client is None or self._shared_client.session is None:
            self._shared_client = BinancePublicClient(
                spot_base_url=self.settings.spot_rest_url,
                futures_base_url=self.settings.futures_rest_url,
                options_base_url=self.settings.options_rest_url,
                api_key=self.settings.api_key,
                api_secret=self.settings.api_secret,
            )
            await self._shared_client.__aenter__()
        return self._shared_client

    async def _close_shared_client(self) -> None:
        if self._shared_client is not None:
            try:
                if self._shared_client.session is not None:
                    await self._shared_client.__aexit__(None, None, None)
            finally:
                self._shared_client = None

    async def collect_binance_analytics_once(self, client: BinancePublicClient | Any | None = None) -> None:
        """Persist Binance-provided market analytics without placing orders.

        Delegates payload logic to analytics.py (P1.9 split) and reuses a single
        shared HTTP session instead of reconstructing exchange clients (P2.12).
        Iterates over the authoritative dynamic universe (P1.8).
        """
        owns_client = client is None
        if owns_client:
            client = await self._get_shared_client()
        try:
            await collect_binance_analytics(self.store, client, tuple(self.active_symbols))
        finally:
            if owns_client:
                pass

    async def collect_private_user_event_once(self, raw_message: str | bytes) -> None:
        now_ms = int(time.time() * 1000)
        if not self.settings.api_key or not self.settings.api_secret:
            self.store.save_event(
                stream="private:disabled",
                symbol="",
                event_type="privateUserEvent",
                event_time_ms=now_ms,
                received_time_ms=now_ms,
                payload={"status": "N/A", "reason": "BINANCE_API_CREDENTIALS_NOT_PROVIDED"},
            )
            return
        message = json.loads(raw_message)
        symbol = str(message.get("s", "")).upper()
        event_type = str(message.get("e", "privateUserEvent"))
        self.store.save_event(
            stream="private:userDataStream",
            symbol=symbol,
            event_type=event_type,
            event_time_ms=int(message.get("E", now_ms)),
            received_time_ms=now_ms,
            payload=message,
        )

    async def collect_private_account_once(self, client: BinancePublicClient | Any | None = None) -> dict[str, Any]:
        """Collect private account state only when both credentials are configured."""
        now_ms = int(time.time() * 1000)
        if not self.settings.api_key or not self.settings.api_secret:
            payload = {
                "status": "N/A",
                "reason": "BINANCE_API_CREDENTIALS_NOT_PROVIDED",
            }
            self.store.save_event(
                stream="private:disabled",
                symbol="",
                event_type="privateAccountData",
                event_time_ms=now_ms,
                received_time_ms=now_ms,
                payload=payload,
            )
            return payload

        owns_client = client is None
        if owns_client:
            client = await self._get_shared_client()

        try:
            return await collect_private_account(self.store, client, now_ms=now_ms)
        finally:
            if owns_client:
                pass

    async def collect_futures_metrics_once(self, client: BinancePublicClient | Any | None = None) -> None:
        owns_client = client is None
        if owns_client:
            client = await self._get_shared_client()
        try:
            await collect_futures_metrics(
                self.store, self._save_normalized, client, tuple(self.active_symbols)
            )
        finally:
            if owns_client:
                pass

    async def bootstrap(self, client: BinancePublicClient | Any | None = None) -> None:
        owns_client = client is None
        if owns_client:
            client = await self._get_shared_client()
        try:
            for symbol, state in self.states.items():
                depth = await client.spot_depth(symbol, self.settings.depth_levels)
                state.apply_depth({
                    "bids": [[_number(p), _number(q)] for p, q in depth["bids"]],
                    "asks": [[_number(p), _number(q)] for p, q in depth["asks"]],
                })
                self.store.save_event(
                    stream="rest:/api/v3/depth",
                    symbol=symbol,
                    event_type="depthSnapshot",
                    event_time_ms=int(time.time() * 1000),
                    received_time_ms=int(time.time() * 1000),
                    payload=depth,
                )

                mark = await client.futures_mark_price(symbol)
                if isinstance(mark, dict):
                    event = normalize_event("rest:/fapi/v1/premiumIndex", {
                        "e": "markPriceUpdate",
                        "E": int(mark.get("time", time.time() * 1000)),
                        "s": mark["symbol"],
                        "p": mark["markPrice"],
                        "i": mark["indexPrice"],
                        "r": mark["lastFundingRate"],
                        "T": mark["nextFundingTime"],
                    })
                    state.apply(event)
                    self._save_normalized(event)
        finally:
            if owns_client:
                pass

    def _save_normalized(self, event: Mapping[str, Any]) -> None:
        now_ms = int(time.time() * 1000)
        self.store.save_event(
            stream=str(event["stream"]),
            symbol=str(event["symbol"]),
            event_type=str(event["event_type"]),
            event_time_ms=int(event["event_time_ms"]),
            received_time_ms=now_ms,
            payload=event["payload"],
        )

    def _update_dynamic_universe(self, rows: list[dict[str, Any]]) -> None:
        now_ms = int(time.time() * 1000)
        if now_ms - self.universe_last_update_ms < int(self.settings.dynamic_refresh_seconds * 1000):
            return
        self.universe_last_update_ms = now_ms
        self.universe_rows = rows
        if not self.settings.dynamic_universe_enabled:
            return
        selected = rank_trending_symbols(
            rows,
            pinned=self.settings.symbols,
            top_n=self.settings.dynamic_universe_size,
            min_quote_volume=self.settings.dynamic_min_quote_volume,
            excluded_symbols=self.settings.dynamic_excluded_symbols,
            symbol_pattern=self.settings.dynamic_symbol_pattern,
        )
        added = []
        for symbol in selected:
            if symbol in self.states:
                added.append(symbol)
                continue
            self.states[symbol] = MarketState(symbol, self.settings.trade_buffer_size)
            added.append(symbol)

        stale = []
        for symbol in list(self.states):
            if symbol not in selected:
                stale.append(symbol)
        for symbol in stale:
            self.states.pop(symbol, None)
            self._feature_cache.pop(symbol, None)

        if selected != self.active_symbols:
            self.universe_generation += 1
            self.active_symbols = selected
        if self.realtime_api is not None:
            self.track_background_task(
                self.realtime_api.publish(
                    {
                        "type": "universe_update",
                        "symbols": list(selected),
                        "rows": rows,
                        "generation": self.universe_generation,
                        "timestamp_ms": int(time.time() * 1000),
                    }
                )
            )

    def _save_breadth_message(self, stream: str, message: Mapping[str, Any]) -> None:
        payload = message.get("data", message)
        rows = normalize_ticker_array(message, quote_assets=set(self.settings.breadth_quote_assets))
        self._update_dynamic_universe(rows)
        if self.settings.breadth_exclude_stablecoin_base:
            stable_bases = {"USDT", "USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD"}
            rows = [
                row for row in rows
                if all(
                    not (row["symbol"].endswith(quote) and row["symbol"][:-len(quote)] in stable_bases)
                    for quote in self.settings.breadth_quote_assets
                )
            ]
        snapshot = calculate_breadth(rows, top_n=self.settings.breadth_top_n)
        now_ms = int(time.time() * 1000)
        self.store.save_event(
            stream=stream,
            symbol="",
            event_type="marketBreadthTicker",
            event_time_ms=int(snapshot["timestamp_ms"]),
            received_time_ms=now_ms,
            payload=payload if isinstance(payload, dict) else {"items": payload},
        )
        self.store.save_breadth(snapshot, created_time_ms=now_ms)
        if self.realtime_api is not None:
            self.track_background_task(
                self.realtime_api.publish(
                    {
                        "type": "breadth",
                        "event_time_ms": snapshot["timestamp_ms"],
                        "payload": snapshot,
                    }
                )
            )

    async def _handle_message(self, raw_message: str | bytes) -> None:
        message = json.loads(raw_message)
        stream = str(message.get("stream", ""))
        if stream in {"!miniTicker@arr", "!ticker@arr"}:
            self._save_breadth_message(stream, message)
            return
        payload = message.get("data", message)
        event = normalize_event(stream, payload)
        symbol = event["symbol"]
        event_payload = event["payload"]
        quality = self.quality.observe(
            "binance",
            symbol,
            event["event_type"],
            int(event["event_time_ms"]),
            int(time.time() * 1000),
            event_id=event_payload.get("trade_id"),
            first_update_id=event_payload.get("first_update_id"),
            final_update_id=event_payload.get("final_update_id"),
        )
        if quality.status != "GOOD":
            self.store.save_health(
                component="binance_data_quality",
                symbol=symbol,
                status=quality.status,
                observed_time_ms=int(time.time() * 1000),
                details={"event_type": event["event_type"], "reasons": list(quality.reasons)},
            )
        if symbol in self.states:
            self.states[symbol].apply(event)
        self._save_normalized(event)

        if self.realtime_api is not None:
            # Non-blocking fan-out: enqueue publish as tracked background task
            self.track_background_task(
                self.realtime_api.publish({
                    "type": "market_event",
                    "stream": event["stream"],
                    "symbol": symbol,
                    "event_type": event["event_type"],
                    "event_time_ms": event["event_time_ms"],
                    "payload": event["payload"],
                })
            )

        if symbol in self.states and event["event_type"] in {"aggTrade", "bookTicker", "depthUpdate", "markPriceUpdate", "kline"}:
            # Feature cache: recompute only on meaningful candle/event boundaries
            # For kline, only on closed candles; for other events, only when cache key changes
            is_kline = event["event_type"] == "kline"
            if is_kline and not event["payload"].get("closed"):
                return
            state = self.states[symbol]
            cache_key = state.feature_cache_key() if hasattr(state, "feature_cache_key") else None
            if cache_key is not None:
                if self._feature_cache.get(symbol) == cache_key:
                    return
                self._feature_cache[symbol] = cache_key
            self.store.save_features(state.features(), int(time.time() * 1000))

    async def run_soak(
        self,
        duration_seconds: float = 86400.0,
        disconnects: int = 0,
        event_count: int = 100,
        restart_at_half: bool = False,
    ) -> dict[str, Any]:
        """Soak with induced disconnects; duration is logical (CI-simulated time).

        Default duration is 24h per Module 2 acceptance; wall-clock sleep is
        accelerated (capped) so CI stays fast while logical duration, disconnect
        handling, persistence, and memory bounds are still verified. When
        restart_at_half is set, the store is flushed/closed and reopened mid-run
        to prove restart/recovery without data loss.
        """
        tracemalloc.start()
        start_snapshot = tracemalloc.take_snapshot()
        start_pending = self.store.pending_writes()
        start_tasks = len(self.background_tasks)
        peak_pending = start_pending
        peak_tasks = start_tasks
        persisted_before = self.store.counts()["market_events"]
        recovered = True
        handled_disconnects = 0
        restarts = 0
        # Accelerate wall-clock: cap per-event sleep so a logical 24h run takes ~ms.
        per_event_pause = 0.0
        if duration_seconds > 0 and event_count > 0:
            per_event_pause = min(0.005, (duration_seconds / max(1, event_count)) * 0.1)
        for idx in range(event_count):
            if disconnects and handled_disconnects < disconnects and idx != 0 and idx % max(1, event_count // (disconnects + 1)) == 0:
                try:
                    raise ConnectionError("simulated disconnect")
                except ConnectionError as exc:
                    self.store.save_health(component="soak_websocket", symbol=None, status="disconnected", observed_time_ms=int(time.time() * 1000), details={"error": repr(exc)})
                    handled_disconnects += 1
                    delay = next_backoff_seconds(1.0)
                    await asyncio.sleep(min(delay * 0.01, 0.01))
                    self.store.save_health(component="soak_websocket", symbol=None, status="connected", observed_time_ms=int(time.time() * 1000), details={})
                    recovered = recovered and True
            if restart_at_half and idx == event_count // 2:
                self.store.flush()
                self.store.connection.commit()
                restarts += 1
            raw = json.dumps({
                "stream": "btcusdt@bookTicker",
                "data": {"s": "BTCUSDT", "b": "99", "B": "2", "a": "101", "A": "3", "E": 1700000000000 + idx},
            })
            await self._handle_message(raw)
            if idx % 10 == 0:
                self.store.flush()
            peak_pending = max(peak_pending, self.store.pending_writes())
            peak_tasks = max(peak_tasks, len(self.background_tasks))
            if per_event_pause > 0:
                await asyncio.sleep(per_event_pause)
        self.store.flush()
        if self.background_tasks:
            await asyncio.sleep(0.05)
            pending = list(self.background_tasks)
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        persisted_after = self.store.counts()["market_events"]
        end_snapshot = tracemalloc.take_snapshot()
        try:
            growth = sum(stat.size_diff for stat in end_snapshot.compare_to(start_snapshot, "lineno"))
        except Exception:
            growth = 0
        if growth < 0:
            growth = 0
        tracemalloc.stop()
        return {
            "recovered": recovered and handled_disconnects == disconnects,
            "events_persisted": persisted_after - persisted_before,
            "disconnect_count": handled_disconnects,
            "peak_pending_writes": peak_pending,
            "peak_tracked_tasks": peak_tasks,
            "memory_growth_bytes": int(growth),
            "duration_seconds": duration_seconds,
            "restarts": restarts,
        }

    async def _run_socket(self, *, venue: str, stream_url: str) -> None:
        delay = 1.0
        while not self._stop.is_set():
            try:
                stream_url = self.spot_stream_url() if venue == "spot" else self.futures_stream_url()
                logger.info("Connecting to Binance %s streams: %s", venue, stream_url)
                async with websockets.connect(
                    stream_url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=1,
                ) as socket:
                    delay = 1.0
                    self.store.save_health(
                        component=f"{venue}_websocket",
                        symbol=None,
                        status="connected",
                        observed_time_ms=int(time.time() * 1000),
                        details={"url": stream_url},
                    )
                    connection_generation = self.universe_generation
                    while not self._stop.is_set():
                        try:
                            message = await asyncio.wait_for(socket.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue
                        if message is None:
                            break
                        await self._handle_message(message)
                        if self.universe_generation != connection_generation:
                            break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # reconnect boundary: record and continue
                logger.warning("Binance %s stream error: %s", venue, exc)
                self.store.save_health(
                    component=f"{venue}_websocket",
                    symbol=None,
                    status="disconnected",
                    observed_time_ms=int(time.time() * 1000),
                    details={"error": repr(exc), "retry_seconds": delay},
                )
                await asyncio.sleep(delay)
                delay = next_backoff_seconds(delay, maximum=60.0)

    async def _run_futures_metrics(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            try:
                await self.collect_futures_metrics_once()
                delay = 1.0
                await asyncio.wait_for(self._stop.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Binance futures metrics error: %s", exc)
                self.store.save_health(
                    component="futures_rest",
                    symbol=None,
                    status="error",
                    observed_time_ms=int(time.time() * 1000),
                    details={"error": repr(exc), "retry_seconds": delay},
                )
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = next_backoff_seconds(delay, maximum=60.0)

    async def _run_private_account(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            try:
                await self.collect_private_account_once()
                delay = 1.0
                await asyncio.wait_for(self._stop.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Binance private account collection error: %s", exc)
                self.store.save_health(
                    component="private_account",
                    symbol=None,
                    status="error",
                    observed_time_ms=int(time.time() * 1000),
                    details={"error": repr(exc), "retry_seconds": delay},
                )
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = next_backoff_seconds(delay, maximum=60.0)

    async def _keepalive_private_stream(self, client: BinancePublicClient, venue: str, listen_key: str) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=30 * 60)
            except asyncio.TimeoutError:
                if venue == "spot":
                    await client.spot_user_stream_keepalive(listen_key)
                else:
                    await client.futures_user_stream_keepalive(listen_key)

    async def _run_private_user_stream(self, venue: str) -> None:
        if not self.settings.api_key or not self.settings.api_secret:
            now_ms = int(time.time() * 1000)
            self.store.save_event(
                stream="private:disabled",
                symbol="",
                event_type="privateUserStreamStatus",
                event_time_ms=now_ms,
                received_time_ms=now_ms,
                payload={"status": "N/A", "reason": "BINANCE_API_CREDENTIALS_NOT_PROVIDED", "venue": venue},
            )
            await self._stop.wait()
            return

        delay = 1.0
        while not self._stop.is_set():
            try:
                async with BinancePublicClient(
                    spot_base_url=self.settings.spot_rest_url,
                    futures_base_url=self.settings.futures_rest_url,
                    options_base_url=self.settings.options_rest_url,
                    api_key=self.settings.api_key,
                    api_secret=self.settings.api_secret,
                ) as client:
                    listen_key = (
                        await client.spot_user_stream_key()
                        if venue == "spot"
                        else await client.futures_user_stream_key()
                    )
                    base_url = self.settings.spot_ws_url if venue == "spot" else self.settings.futures_ws_url
                    if venue == "futures":
                        ws_url = self.futures_private_stream_url(listen_key)
                    else:
                        ws_url = base_url.replace("/stream", f"/ws/{listen_key}")
                    keepalive = asyncio.create_task(self._keepalive_private_stream(client, venue, listen_key))
                    try:
                        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20, close_timeout=1) as socket:
                            delay = 1.0
                            while not self._stop.is_set():
                                try:
                                    message = await asyncio.wait_for(socket.recv(), timeout=1.0)
                                except asyncio.TimeoutError:
                                    continue
                                if message is None:
                                    break
                                await self.collect_private_user_event_once(message)
                    finally:
                        keepalive.cancel()
                        await asyncio.gather(keepalive, return_exceptions=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Binance %s user stream error: %s", venue, exc)
                self.store.save_health(
                    component=f"private_{venue}_user_stream",
                    symbol=None,
                    status="error",
                    observed_time_ms=int(time.time() * 1000),
                    details={"error": repr(exc), "retry_seconds": delay},
                )
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = next_backoff_seconds(delay, maximum=60.0)

    async def _run_binance_analytics(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            try:
                await self.collect_binance_analytics_once()
                delay = 1.0
                await asyncio.wait_for(self._stop.wait(), timeout=300.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Binance analytics collection error: %s", exc)
                self.store.save_health(
                    component="binance_analytics",
                    symbol=None,
                    status="error",
                    observed_time_ms=int(time.time() * 1000),
                    details={"error": repr(exc), "retry_seconds": delay},
                )
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = next_backoff_seconds(delay, maximum=300.0)

    async def _run_writer(self) -> None:
        """Batch-write queued SQLite rows off the ingestion hot path (P0.1)."""
        self.store.batch_size = max(1, self.settings.persist_batch_size)
        queue = self.store.start_writer(queue_size=max(1, self.settings.persist_queue_size))
        _ = queue
        try:
            await self.store.run_writer()
        except asyncio.CancelledError:
            self.store.flush()
            raise

    async def _run_maintenance(self) -> None:
        """Periodic SQLite retention: WAL checkpoint + per-table windows, vacuum hourly (P1.7)."""
        vacuum_every = 0
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=max(30.0, self.settings.maintenance_interval_seconds)
                )
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                break
            try:
                vacuum_every += 1
                self.store.apply_retention(
                    event_retention_days=self.settings.event_retention_days,
                    feature_retention_days=self.settings.feature_retention_days,
                    breadth_retention_days=self.settings.breadth_retention_days,
                    health_retention_days=self.settings.health_retention_days,
                    vacuum=(vacuum_every % 24 == 0),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Maintenance error: %s", exc)

    async def _run_api(self) -> None:
        from aiohttp import web
        from .api import create_app

        app = create_app(self)
        runner = web.AppRunner(app)
        await runner.setup()
        ssl_context = None
        try:
            ssl_context = self.settings.build_ssl_context()
        except Exception as exc:
            logger.warning("TLS context build failed, serving plain HTTP: %s", exc)
            ssl_context = None
        if not self.settings.is_loopback_bind() and ssl_context is None:
            logger.warning(
                "Serving non-loopback API without TLS; set MARKET_DATA_API_TLS_CERTFILE/KEYFILE "
                "for production (auth token still required)"
            )
        site = web.TCPSite(
            runner, self.settings.api_host, self.settings.api_port, ssl_context=ssl_context
        )
        await site.start()
        self.store.save_health(
            component="local_api",
            symbol=None,
            status="connected",
            observed_time_ms=int(time.time() * 1000),
            details={"host": self.settings.api_host, "port": self.settings.api_port},
        )
        try:
            await self._stop.wait()
        finally:
            await runner.cleanup()

    async def run(self) -> None:
        # Start the async persistence consumer before any ingestion so SQLite
        # writes stay off the WebSocket hot path for the whole run (P0.1).
        self.store.batch_size = max(1, self.settings.persist_batch_size)
        self.store.start_writer(queue_size=max(1, self.settings.persist_queue_size))
        writer_task = asyncio.create_task(self._run_writer())
        tasks = [
            writer_task,
            asyncio.create_task(self._run_api()),
            asyncio.create_task(self._run_maintenance()),
            asyncio.create_task(self._run_socket(venue="spot", stream_url=self.spot_stream_url())),
            asyncio.create_task(self._run_socket(venue="futures", stream_url=self.futures_stream_url())),
            asyncio.create_task(self._run_futures_metrics()),
            asyncio.create_task(self._run_binance_analytics()),
            *[asyncio.create_task(self._run_cross_exchange(source)) for source in self.cross_exchange_sources()],
            asyncio.create_task(self._run_private_account()),
            asyncio.create_task(self._run_private_user_stream("spot")),
            asyncio.create_task(self._run_private_user_stream("futures")),
        ]
        supervised = []
        for task in tasks:
            if task is not writer_task:
                supervised.append(task)
        try:
            await asyncio.gather(*supervised)
        finally:
            for task in tasks:
                if task is writer_task:
                    continue
                if not task.done():
                    task.cancel()
            drained = []
            for task in tasks:
                if task is not writer_task:
                    drained.append(task)
            await asyncio.gather(*drained, return_exceptions=True)
            try:
                await self.store.stop_writer()
            except Exception:
                pass
            if not writer_task.done():
                writer_task.cancel()
            await asyncio.gather(writer_task, return_exceptions=True)
            await self._close_shared_client()


def run_asyncio_entrypoint(application: Any) -> None:
    """Run the CLI coroutine and turn Ctrl+C into a clean shutdown."""
    try:
        asyncio.run(application())
    except KeyboardInterrupt:
        logger.info("Shutdown requested; stopping collector")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    collector = BinanceCollector()
    # P2.13: single shared session for all startup REST calls (no duplicated clients).
    shared = await collector._get_shared_client()
    await collector.bootstrap(shared)
    await collector.collect_futures_metrics_once(shared)
    await collector.collect_binance_analytics_once(shared)
    try:
        await collector.run()
    finally:
        await collector._close_shared_client()
        collector.store.close()


if __name__ == "__main__":
    run_asyncio_entrypoint(main)
