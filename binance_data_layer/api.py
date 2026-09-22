"""Read-only realtime API for the local market-data collector."""
from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from typing import Any

from aiohttp import web

from .collector import BinanceCollector

REALTIME_API_KEY = web.AppKey("realtime_api", "RealtimeApi")


class RealtimeApi:
    def __init__(self, collector: BinanceCollector) -> None:
        self.collector = collector
        self.subscribers: dict[str, set[web.WebSocketResponse]] = defaultdict(set)
        self.all_subscribers: set[web.WebSocketResponse] = set()
        self._lock = asyncio.Lock()

    def app(self) -> web.Application:
        app = web.Application()
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
        return web.json_response({"status": "ok", "service": "crypto-market-data", "timestamp_ms": int(time.time() * 1000)})

    def _state_payload(self, symbol: str) -> dict[str, Any] | None:
        state = self.collector.states.get(symbol.upper())
        if state is None:
            return None
        payload = state.features()
        payload["health"] = state.health(stale_after_seconds=self.collector.settings.stale_after_seconds)
        return payload

    async def snapshot(self, request: web.Request) -> web.Response:
        symbol = request.match_info["symbol"].upper()
        payload = self._state_payload(symbol)
        if payload is None:
            raise web.HTTPNotFound(text=json.dumps({"error": "unknown_symbol", "symbol": symbol}), content_type="application/json")
        return web.json_response(payload)

    async def features(self, request: web.Request) -> web.Response:
        return await self.snapshot(request)

    async def breadth(self, _: web.Request) -> web.Response:
        row = self.collector.store.connection.execute("SELECT payload_json FROM breadth_snapshots ORDER BY id DESC LIMIT 1").fetchone()
        return web.json_response(json.loads(row[0]) if row else {"status": "N/A", "reason": "NO_BREADTH_DATA"})

    async def top_coins(self, _: web.Request) -> web.Response:
        return web.json_response({
            "symbols": list(self.collector.active_symbols),
            "generation": self.collector.universe_generation,
            "ranked_rows": self.collector.universe_rows,
            "timestamp_ms": int(time.time() * 1000),
            "method": "absolute_24h_change_then_quote_volume_with_pinned_symbols",
        })

    async def cross_exchange(self, request: web.Request) -> web.Response:
        symbol = request.match_info["symbol"].upper()
        row = self.collector.store.connection.execute(
            "SELECT payload_json FROM market_events WHERE event_type = 'crossExchangeConfirmation' AND symbol = ? ORDER BY id DESC LIMIT 1", (symbol,)
        ).fetchone()
        return web.json_response(json.loads(row[0]) if row else {"status": "N/A", "reason": "NO_CROSS_EXCHANGE_DATA", "symbol": symbol})

    async def data_health(self, _: web.Request) -> web.Response:
        rows = self.collector.store.connection.execute(
            "SELECT component, symbol, status, observed_time_ms, details_json FROM data_health ORDER BY id DESC LIMIT 100"
        ).fetchall()
        return web.json_response([{"component": r[0], "symbol": r[1], "status": r[2], "observed_time_ms": r[3], "details": json.loads(r[4])} for r in rows])

    async def events(self, request: web.Request) -> web.Response:
        symbol = request.query.get("symbol")
        limit = min(500, max(1, int(request.query.get("limit", "100"))))
        if symbol:
            rows = self.collector.store.connection.execute(
                "SELECT stream, symbol, event_type, event_time_ms, received_time_ms, payload_json FROM market_events WHERE symbol = ? ORDER BY id DESC LIMIT ?", (symbol.upper(), limit)
            ).fetchall()
        else:
            rows = self.collector.store.connection.execute(
                "SELECT stream, symbol, event_type, event_time_ms, received_time_ms, payload_json FROM market_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return web.json_response([{"stream": r[0], "symbol": r[1], "event_type": r[2], "event_time_ms": r[3], "received_time_ms": r[4], "payload": json.loads(r[5])} for r in rows])

    async def websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        symbol = request.query.get("symbol", "").upper()
        if symbol:
            self.subscribers[symbol].add(ws)
        else:
            self.all_subscribers.add(ws)
        await ws.send_json({"type": "connected", "symbol": symbol or None, "timestamp_ms": int(time.time() * 1000)})
        try:
            async for _ in ws:
                pass
        finally:
            self.subscribers.get(symbol, set()).discard(ws)
            self.all_subscribers.discard(ws)
        return ws

    async def publish(self, message: dict[str, Any]) -> None:
        symbol = str(message.get("symbol", "")).upper()
        targets = set(self.all_subscribers) | set(self.subscribers.get(symbol, set()))
        if not targets:
            return
        dead: list[web.WebSocketResponse] = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except (ConnectionError, RuntimeError):
                dead.append(ws)
        for ws in dead:
            self.all_subscribers.discard(ws)
            self.subscribers.get(symbol, set()).discard(ws)


def create_app(collector: BinanceCollector) -> web.Application:
    api = RealtimeApi(collector)
    collector.realtime_api = api
    return api.app()
