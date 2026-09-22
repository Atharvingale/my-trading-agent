"""Persistent Binance spot/futures market-data collector."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

import websockets

from .binance_client import BinancePublicClient
from .breadth import calculate_breadth, normalize_ticker_array, rank_trending_symbols
from .config import Settings
from .cross_exchange import PUBLIC_WS_URLS, build_confirmation, canonical_symbol, normalize_message, subscription_for
from .features import build_feature_snapshot
from .quality import QualityTracker
from .storage import MarketStore
from .technical import Candle, calculate_indicators, multi_timeframe_alignment

logger = logging.getLogger(__name__)


def _number(value: Any) -> float:
    return float(value)


def normalize_event(stream: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize supported Binance WebSocket payloads into stable records."""
    event_type = str(payload.get("e", "unknown"))
    if event_type == "unknown" and "@bookTicker" in stream:
        event_type = "bookTicker"
    elif event_type == "unknown" and "@depth" in stream:
        event_type = "depthUpdate"
    symbol = str(payload.get("s", "")).upper()
    if not symbol and "@" in stream:
        symbol = stream.split("@", 1)[0].upper()
    event_time_ms = int(payload.get("E", payload.get("T", int(time.time() * 1000))))

    if event_type == "markPrice" and "mp" in payload:
        event_type = "optionMarkPrice"
        normalized = {
            "mark_price": _number(payload["mp"]),
            "bid_iv": _number(payload["b"]),
            "ask_iv": _number(payload["a"]),
            "mark_iv": _number(payload.get("vo", payload.get("markIV", payload["b"]))),
            "bid_price": _number(payload["bo"]),
            "ask_price": _number(payload["ao"]),
            "index_price": _number(payload["i"]),
            "delta": _number(payload["d"]),
            "theta": _number(payload["t"]),
            "gamma": _number(payload["g"]),
            "vega": _number(payload["v"]),
            "risk_free_interest": _number(payload.get("rf", payload.get("riskFreeInterest", 0.0))),
        }
    elif event_type == "openInterest" and "o" in payload and "h" in payload:
        event_type = "optionOpenInterest"
        normalized = {
            "open_interest_contracts": _number(payload["o"]),
            "open_interest_usd": _number(payload["h"]),
        }
    elif event_type in {"aggTrade", "trade"}:
        normalized = {
            "price": _number(payload["p"]),
            "qty": _number(payload["q"]),
            "is_buyer_maker": bool(payload["m"]),
            "trade_id": payload.get("a", payload.get("t")),
        }
    elif event_type == "kline":
        kline = payload["k"]
        normalized = {
            "open_time_ms": kline["t"],
            "close_time_ms": kline["T"],
            "interval": kline["i"],
            "open": _number(kline["o"]),
            "close": _number(kline["c"]),
            "high": _number(kline["h"]),
            "low": _number(kline["l"]),
            "volume": _number(kline["v"]),
            "quote_volume": _number(kline["q"]),
            "trade_count": int(kline["n"]),
            "taker_buy_volume": _number(kline["V"]),
            "taker_buy_quote_volume": _number(kline["Q"]),
            "closed": bool(kline["x"]),
        }
    elif event_type == "bookTicker":
        normalized = {
            "bid_price": _number(payload["b"]),
            "bid_qty": _number(payload["B"]),
            "ask_price": _number(payload["a"]),
            "ask_qty": _number(payload["A"]),
        }
    elif event_type == "depthUpdate":
        normalized = {
            "first_update_id": payload.get("U"),
            "final_update_id": payload.get("u", payload.get("lastUpdateId")),
            "bids": [(_number(price), _number(qty)) for price, qty in payload.get("b", payload.get("bids", []))],
            "asks": [(_number(price), _number(qty)) for price, qty in payload.get("a", payload.get("asks", []))],
        }
    elif event_type == "markPriceUpdate":
        normalized = {
            "mark_price": _number(payload["p"]),
            "index_price": _number(payload["i"]),
            "funding_rate": _number(payload["r"]),
            "next_funding_time_ms": payload.get("T"),
        }
    elif event_type == "forceOrder":
        order = payload.get("o", {})
        normalized = {
            "side": order.get("S"),
            "order_type": order.get("o"),
            "price": _number(order["p"]),
            "average_price": _number(order["ap"]),
            "orig_qty": _number(order["q"]),
            "executed_qty": _number(order["z"]),
            "trade_time_ms": order.get("T"),
        }
        symbol = str(order.get("s", symbol)).upper()
    else:
        normalized = dict(payload)

    return {
        "stream": stream,
        "event_type": event_type,
        "symbol": symbol,
        "event_time_ms": event_time_ms,
        "payload": normalized,
        "raw": dict(payload),
    }


@dataclass
class MarketState:
    symbol: str
    trade_buffer_size: int = 500
    last_price: float | None = None
    bid_price: float | None = None
    bid_qty: float = 0.0
    ask_price: float | None = None
    ask_qty: float = 0.0
    bids: list[tuple[float, float]] = field(default_factory=list)
    asks: list[tuple[float, float]] = field(default_factory=list)
    recent_trades: deque[dict[str, Any]] = field(init=False)
    last_event_time_ms: int | None = None
    candles: dict[str, deque[dict[str, Any]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.recent_trades = deque(maxlen=self.trade_buffer_size)

    def apply(self, event: Mapping[str, Any]) -> None:
        self.last_event_time_ms = int(event["event_time_ms"])
        event_type = str(event["event_type"])
        payload = event["payload"]
        if event_type in {"aggTrade", "trade"}:
            self.apply_trade(payload)
        elif event_type == "bookTicker":
            self.apply_book_ticker(payload)
        elif event_type == "depthUpdate":
            self.apply_depth(payload)
        elif event_type == "markPriceUpdate":
            self.last_price = payload.get("mark_price", self.last_price)
        elif event_type == "kline" and payload.get("closed"):
            interval = str(payload.get("interval", ""))
            self.candles.setdefault(interval, deque(maxlen=500)).append(dict(payload))

    def apply_trade(self, payload: Mapping[str, Any]) -> None:
        self.last_price = float(payload["price"])
        self.recent_trades.append(dict(payload))

    def apply_book_ticker(self, payload: Mapping[str, Any]) -> None:
        self.bid_price = float(payload["bid_price"])
        self.bid_qty = float(payload["bid_qty"])
        self.ask_price = float(payload["ask_price"])
        self.ask_qty = float(payload["ask_qty"])

    def apply_depth(self, payload: Mapping[str, Any]) -> None:
        self.bids = [(float(price), float(qty)) for price, qty in payload["bids"]]
        self.asks = [(float(price), float(qty)) for price, qty in payload["asks"]]

    def health(self, *, now_ms: int | None = None, stale_after_seconds: float = 30.0) -> dict[str, Any]:
        observed_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        if self.last_event_time_ms is None:
            return {"symbol": self.symbol, "status": "missing", "age_seconds": None}
        age_seconds = max(0.0, (observed_ms - self.last_event_time_ms) / 1000)
        return {
            "symbol": self.symbol,
            "status": "fresh" if age_seconds <= stale_after_seconds else "stale",
            "age_seconds": age_seconds,
        }

    def features(self) -> dict[str, Any]:
        event_time = datetime.fromtimestamp(
            (self.last_event_time_ms or int(time.time() * 1000)) / 1000,
            tz=timezone.utc,
        )
        technical = {
            interval: calculate_indicators([
                Candle(
                    int(c["open_time_ms"]), float(c["open"]), float(c["high"]),
                    float(c["low"]), float(c["close"]), float(c["volume"]), True,
                ) for c in candles
            ]) for interval, candles in self.candles.items()
        }
        alignment = multi_timeframe_alignment(technical)
        snapshot = build_feature_snapshot(
            symbol=self.symbol,
            event_time=event_time,
            last_price=self.last_price,
            bid_price=self.bid_price,
            ask_price=self.ask_price,
            bid_qty=self.bid_qty,
            ask_qty=self.ask_qty,
            recent_trades=self.recent_trades,
            bids=self.bids,
            asks=self.asks,
            technical=technical,
        )
        snapshot["multi_timeframe_alignment"] = alignment
        return snapshot



class BinanceCollector:
    def __init__(self, settings: Settings | None = None, store: MarketStore | None = None) -> None:
        self.settings = settings or Settings.from_environment()
        self.store = store or MarketStore(self.settings.database_path)
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
            asyncio.create_task(self.realtime_api.publish({
                "type": "cross_exchange_confirmation",
                "symbol": symbol,
                "event_time_ms": now_ms,
                "payload": confirmation,
            }))

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
                delay = min(delay * 2, 60.0)

    async def collect_binance_analytics_once(self, client: BinancePublicClient | Any | None = None) -> None:
        """Persist Binance-provided market analytics without placing orders."""
        owns_client = client is None
        if owns_client:
            context = BinancePublicClient(
                spot_base_url=self.settings.spot_rest_url,
                futures_base_url=self.settings.futures_rest_url,
                options_base_url=self.settings.options_rest_url,
                api_key=self.settings.api_key,
                api_secret=self.settings.api_secret,
            )
            client = await context.__aenter__()
        now_ms = int(time.time() * 1000)

        def persist(symbol: str, event_type: str, payload: Any, event_time_ms: int | None = None, stream: str = "rest") -> None:
            event_payload = payload if isinstance(payload, dict) else {"items": payload}
            self.store.save_event(
                stream=stream,
                symbol=symbol,
                event_type=event_type,
                event_time_ms=int(event_time_ms or now_ms),
                received_time_ms=now_ms,
                payload=event_payload,
            )

        try:
            persist("", "exchangeInfo", await client.exchange_info(), stream="rest:/api/v3/exchangeInfo")
            option_marks = await client.options_mark_price()
            persist("", "optionMarkPrice", option_marks, stream="rest:/eapi/v1/mark")
            for symbol in self.settings.symbols:
                ticker = await client.spot_24hr_ticker(symbol)
                persist(symbol, "spot24hrTicker", ticker, stream="rest:/api/v3/ticker/24hr")

                for method, event_type in (
                    (client.futures_long_short_account_ratio, "futuresLongShortRatio"),
                    (client.futures_taker_volume, "futuresTakerVolume"),
                    (client.futures_open_interest_history, "futuresOpenInterestHistory"),
                    (client.futures_funding_history, "futuresFundingRate"),
                ):
                    items = await method(symbol)
                    persist(symbol, event_type, items, stream=f"rest:{event_type}")

                basis = await client.futures_basis(symbol)
                persist(symbol, "futuresBasis", basis, stream="rest:/futures/data/basis")

            option_bases = sorted({
                str(item["symbol"]).split("-")[0]
                for item in (option_marks if isinstance(option_marks, list) else [])
                if isinstance(item, dict) and "symbol" in item and len(str(item["symbol"]).split("-")) >= 4
            })
            expirations_by_base = {
                base: sorted({
                    str(item["symbol"]).split("-")[1]
                    for item in (option_marks if isinstance(option_marks, list) else [])
                    if isinstance(item, dict)
                    and str(item.get("symbol", "")).startswith(f"{base}-")
                    and len(str(item["symbol"]).split("-")) >= 4
                })
                for base in option_bases
            }
            for base in option_bases:
                for expiration in expirations_by_base[base]:
                    option_oi = await client.options_open_interest(base, expiration)
                    persist(
                        base,
                        "optionOpenInterest",
                        {"expiration": expiration, "items": option_oi},
                        stream="rest:/eapi/v1/openInterest",
                    )
                option_blocks = await client.options_block_trades()
                persist(base, "optionBlockTrade", option_blocks, stream="rest:/eapi/v1/blockTrades")
        finally:
            if owns_client:
                await context.__aexit__(None, None, None)

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
            context = BinancePublicClient(
                spot_base_url=self.settings.spot_rest_url,
                futures_base_url=self.settings.futures_rest_url,
                options_base_url=self.settings.options_rest_url,
                api_key=self.settings.api_key,
                api_secret=self.settings.api_secret,
            )
            client = await context.__aenter__()

        try:
            records = (
                ("privateSpotAccount", "", client.spot_account),
                ("privateSpotOpenOrders", "", client.spot_open_orders),
                ("privateFuturesAccount", "", client.futures_account),
                ("privateFuturesOpenOrders", "", client.futures_open_orders),
            )
            for event_type, symbol, method in records:
                payload = await method()
                self.store.save_event(
                    stream="private:binance",
                    symbol=symbol,
                    event_type=event_type,
                    event_time_ms=now_ms,
                    received_time_ms=int(time.time() * 1000),
                    payload=payload if isinstance(payload, dict) else {"items": payload},
                )
            return {"status": "ok"}
        finally:
            if owns_client:
                await context.__aexit__(None, None, None)

    async def collect_futures_metrics_once(self, client: BinancePublicClient | Any | None = None) -> None:
        owns_client = client is None
        if owns_client:
            context = BinancePublicClient(
                spot_base_url=self.settings.spot_rest_url,
                futures_base_url=self.settings.futures_rest_url,
                options_base_url=self.settings.options_rest_url,
                api_key=self.settings.api_key,
                api_secret=self.settings.api_secret,
            )
            client = await context.__aenter__()
        try:
            for symbol in self.settings.symbols:
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
                    self._save_normalized(event)
                interest = await client.futures_open_interest(symbol)
                self.store.save_event(
                    stream="rest:/fapi/v1/openInterest",
                    symbol=symbol,
                    event_type="openInterest",
                    event_time_ms=int(interest.get("time", time.time() * 1000)),
                    received_time_ms=int(time.time() * 1000),
                    payload={"open_interest": _number(interest["openInterest"])},
                )
        finally:
            if owns_client:
                await context.__aexit__(None, None, None)

    async def bootstrap(self) -> None:
        async with BinancePublicClient(
            spot_base_url=self.settings.spot_rest_url,
            futures_base_url=self.settings.futures_rest_url,
        ) as client:
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
        added = [symbol for symbol in selected if symbol not in self.states]
        for symbol in added:
            self.states[symbol] = MarketState(symbol, self.settings.trade_buffer_size)
        if selected != self.active_symbols:
            self.universe_generation += 1
            self.active_symbols = selected
        if self.realtime_api is not None:
            asyncio.create_task(self.realtime_api.publish({
                "type": "universe_update",
                "symbols": list(selected),
                "rows": rows,
                "generation": self.universe_generation,
                "timestamp_ms": int(time.time() * 1000),
            }))

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
            asyncio.create_task(self.realtime_api.publish({
                "type": "breadth",
                "event_time_ms": snapshot["timestamp_ms"],
                "payload": snapshot,
            }))

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
            await self.realtime_api.publish({
                "type": "market_event",
                "stream": event["stream"],
                "symbol": symbol,
                "event_type": event["event_type"],
                "event_time_ms": event["event_time_ms"],
                "payload": event["payload"],
            })

        if symbol in self.states and event["event_type"] in {"aggTrade", "bookTicker", "depthUpdate", "markPriceUpdate", "kline"}:
            self.store.save_features(self.states[symbol].features(), int(time.time() * 1000))

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
                delay = min(delay * 2, 60.0)

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
                delay = min(delay * 2, 60.0)

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
                delay = min(delay * 2, 60.0)

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
                delay = min(delay * 2, 60.0)

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
                delay = min(delay * 2, 300.0)

    async def _run_api(self) -> None:
        from aiohttp import web
        from .api import create_app

        app = create_app(self)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.settings.api_host, self.settings.api_port)
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
        tasks = [
            asyncio.create_task(self._run_api()),
            asyncio.create_task(self._run_socket(venue="spot", stream_url=self.spot_stream_url())),
            asyncio.create_task(self._run_socket(venue="futures", stream_url=self.futures_stream_url())),
            asyncio.create_task(self._run_futures_metrics()),
            asyncio.create_task(self._run_binance_analytics()),
            *[asyncio.create_task(self._run_cross_exchange(source)) for source in self.cross_exchange_sources()],
            asyncio.create_task(self._run_private_account()),
            asyncio.create_task(self._run_private_user_stream("spot")),
            asyncio.create_task(self._run_private_user_stream("futures")),
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    collector = BinanceCollector()
    await collector.bootstrap()
    await collector.collect_futures_metrics_once()
    await collector.collect_binance_analytics_once()
    try:
        await collector.run()
    finally:
        collector.store.close()


if __name__ == "__main__":
    asyncio.run(main())
