"""Read-only realtime API with authentication and non-blocking fan-out."""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from typing import Any

from aiohttp import web

from .collector import BinanceCollector

REALTIME_API_KEY = web.AppKey("realtime_api", "RealtimeApi")


@web.middleware
async def auth_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
    collector = request.app[REALTIME_API_KEY].collector
    token = collector.settings.api_token
    if token:
        header = request.headers.get("Authorization", "")
        expected = f"Bearer {token}"
        query_token = request.query.get("token")
        if header != expected and query_token != token:
            raise web.HTTPUnauthorized(
                text=json.dumps({"error": "unauthorized", "reason": "invalid_api_token"}),
                content_type="application/json",
            )
    return await handler(request)


class Subscriber:
    def __init__(self, ws: web.WebSocketResponse, queue_size: int = 64) -> None:
        self.ws = ws
        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=queue_size)
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while True:
                item = await self.queue.get()
                if item is None:
                    break
                await self.ws.send_json(item)
        except (ConnectionError, RuntimeError, asyncio.CancelledError):
            pass

    def enqueue(self, message: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            pass

    async def close(self) -> None:
        try:
            self.queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        await asyncio.gather(self.task, return_exceptions=True)


class RealtimeApi:
    def __init__(self, collector: BinanceCollector) -> None:
        self.collector = collector
        self.subscribers: dict[str, set[Subscriber]] = defaultdict(set)
        self.all_subscribers: set[Subscriber] = set()

    def app(self) -> web.Application:
        app = web.Application(middlewares=[auth_middleware])
        app[REALTIME_API_KEY] = self
        app.router.add_get("/health", self.health)
        app.router.add_get("/market/{symbol}/snapshot", self.snapshot)
        app.router.add_get("/market/{symbol}/features", self.features)
        app.router.add_get("/breadth/latest", self.breadth)
        app.router.add_get("/cross-exchange/{symbol}", self.cross_exchange)
        app.router.add_get("/data-health", self.data_health)
        app.router.add_get("/events", self.events)
        app.router.add_get("/market/top-coins", self.top_coins)
        app.router.add_get("/ws", self.websocket)
        return app

    async def health(self, _: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "service": "crypto-market-data",
                "timestamp_ms": int(time.time() * 1000),
            }
        )

    def _state_payload(self, symbol: str) -> dict[str, Any] | None:
        state = self.collector.states.get(symbol.upper())
        if state is None:
            return None
        payload = state.features()
        payload["health"] = state.health(
            stale_after_seconds=self.collector.settings.stale_after_seconds
        )
        return payload

    async def snapshot(self, request: web.Request) -> web.Response:
        symbol = request.match_info["symbol"].upper()
        payload = self._state_payload(symbol)
        if payload is None:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "unknown_symbol", "symbol": symbol}),
                content_type="application/json",
            )
        return web.json_response(payload)

    async def features(self, request: web.Request) -> web.Response:
        return await self.snapshot(request)

    async def breadth(self, _: web.Request) -> web.Response:
        snapshot = self.collector.store.latest_breadth()
        return web.json_response(snapshot or {"status": "N/A", "reason": "NO_BREADTH_DATA"})

    async def top_coins(self, _: web.Request) -> web.Response:
        return web.json_response(
            {
                "symbols": list(self.collector.active_symbols),
                "generation": self.collector.universe_generation,
                "ranked_rows": self.collector.universe_rows,
                "timestamp_ms": int(time.time() * 1000),
                "method": "absolute_24h_change_then_quote_volume_with_pinned_symbols",
            }
        )

    async def cross_exchange(self, request: web.Request) -> web.Response:
        symbol = request.match_info["symbol"].upper()
        snapshot = self.collector.store.latest_cross_exchange(symbol)
        return web.json_response(
            snapshot or {"status": "N/A", "reason": "NO_CROSS_EXCHANGE_DATA", "symbol": symbol}
        )

    async def data_health(self, _: web.Request) -> web.Response:
        return web.json_response(self.collector.store.recent_health())

    async def events(self, request: web.Request) -> web.Response:
        symbol = request.query.get("symbol")
        limit = min(500, max(1, int(request.query.get("limit", "100"))))
        return web.json_response(self.collector.store.recent_events(symbol=symbol, limit=limit))

    async def websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        symbol = request.query.get("symbol", "").upper()
        subscriber = Subscriber(ws, queue_size=self.collector.settings.subscriber_queue_size)
        if symbol:
            self.subscribers[symbol].add(subscriber)
        else:
            self.all_subscribers.add(subscriber)
        subscriber.enqueue(
            {
                "type": "connected",
                "symbol": symbol or None,
                "timestamp_ms": int(time.time() * 1000),
            }
        )
        try:
            async for _ in ws:
                pass
        finally:
            if symbol:
                self.subscribers.get(symbol, set()).discard(subscriber)
            self.all_subscribers.discard(subscriber)
            await subscriber.close()
        return ws

    async def _deliver_to_raw(self, raw: Any, message: dict[str, Any]) -> None:
        # Awaited inside a tracked background task so slow sinks never block ingestion.
        await raw.send_json(message)

    async def publish(self, message: dict[str, Any]) -> None:
        symbol = str(message.get("symbol", "")).upper()
        targets = set(self.all_subscribers) | set(self.subscribers.get(symbol, set()))
        for subscriber in list(targets):
            if hasattr(subscriber, "enqueue"):
                subscriber.enqueue(message)
            elif hasattr(subscriber, "send_json"):
                # Fallback for raw websocket mocks (e.g., SlowSocket in tests).
                # Route through the collector's tracked-task registry so failures
                # are logged and no untracked asyncio.Task leaks.
                try:
                    tracker = getattr(self.collector, "track_background_task", None)
                    coro = self._deliver_to_raw(subscriber, message)
                    if callable(tracker):
                        tracker(coro)
                    else:
                        asyncio.create_task(coro)
                except Exception:
                    pass
            else:
                continue


def create_app(collector: BinanceCollector) -> web.Application:
    api = RealtimeApi(collector)
    collector.realtime_api = api
    return api.app()
