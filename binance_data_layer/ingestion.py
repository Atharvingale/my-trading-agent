"""WebSocket payload normalization and in-memory market state."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from .features import build_feature_snapshot
from .technical import Candle, calculate_indicators, multi_timeframe_alignment


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
        bids = []
        for price, qty in payload.get("b", payload.get("bids", [])):
            bids.append((_number(price), _number(qty)))
        asks = []
        for price, qty in payload.get("a", payload.get("asks", [])):
            asks.append((_number(price), _number(qty)))
        normalized = {
            "first_update_id": payload.get("U"),
            "final_update_id": payload.get("u", payload.get("lastUpdateId")),
            "bids": bids,
            "asks": asks,
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
        bids = []
        for price, qty in payload["bids"]:
            bids.append((float(price), float(qty)))
        asks = []
        for price, qty in payload["asks"]:
            asks.append((float(price), float(qty)))
        self.bids = bids
        self.asks = asks

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
        technical = {}
        for interval, candles in self.candles.items():
            framed = []
            for item in candles:
                framed.append(
                    Candle(
                        int(item["open_time_ms"]),
                        float(item["open"]),
                        float(item["high"]),
                        float(item["low"]),
                        float(item["close"]),
                        float(item["volume"]),
                        True,
                    )
                )
            technical[interval] = calculate_indicators(framed)
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

    def feature_cache_key(self) -> tuple[Any, ...]:
        """Identity of the inputs that change computed features."""
        return (
            self.last_price,
            self.bid_price,
            self.bid_qty,
            self.ask_price,
            self.ask_qty,
            len(self.bids),
            len(self.asks),
            tuple((interval, len(candles)) for interval, candles in self.candles.items()),
        )
