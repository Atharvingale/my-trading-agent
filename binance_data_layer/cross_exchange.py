"""Pure parsers and confirmation calculations for public exchange data."""
from __future__ import annotations

from statistics import median
from time import time
from typing import Any, Mapping, Sequence


def _result(symbol: str, bid: Any, ask: Any, volume: Any = None, *, source: str = "unknown") -> dict[str, Any]:
    bid_f, ask_f = float(bid), float(ask)
    return {"source": source, "symbol": symbol, "bid": bid_f, "ask": ask_f, "mid_price": (bid_f + ask_f) / 2, "volume": float(volume) if volume is not None else None, "received_time_ms": int(time() * 1000)}


def coinbase_subscription() -> dict[str, Any]:
    return {"type": "subscribe", "product_ids": ["BTC-USD", "ETH-USD"], "channel": "ticker"}


def kraken_subscription() -> dict[str, Any]:
    return {"method": "subscribe", "params": {"channel": "ticker", "symbol": ["BTC/USD", "ETH/USD"]}}


def okx_subscription() -> dict[str, Any]:
    return {"op": "subscribe", "args": [{"channel": "tickers", "instId": "BTC-USDT"}, {"channel": "tickers", "instId": "ETH-USDT"}]}


def normalize_coinbase_ticker(payload: Mapping[str, Any]) -> dict[str, Any]:
    if "events" not in payload:
        return _result(str(payload["product_id"]), payload["best_bid"], payload["best_ask"], payload.get("volume_24_h"), source="coinbase")
    event = payload.get("events", [{}])[0]
    ticker = event.get("tickers", [{}])[0]
    return _result(str(ticker["product_id"]), ticker["best_bid"], ticker["best_ask"], ticker.get("volume_24_h"), source="coinbase")


def normalize_kraken_ticker(payload: Mapping[str, Any] | list[Any]) -> dict[str, Any]:
    if isinstance(payload, list):
        ticker = payload[1]
        symbol = str(payload[2]) if len(payload) > 2 else "UNKNOWN"
        volume = ticker.get("v", [None])[1] if ticker.get("v") else None
        return _result(symbol, ticker["b"][0], ticker["a"][0], volume, source="kraken")
    ticker = payload["data"][0]
    return _result(str(ticker["symbol"]), ticker["bid"], ticker["ask"], ticker.get("volume"), source="kraken")


def normalize_okx_ticker(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = payload["data"][0]
    return _result(str(data["instId"]), data["bidPx"], data["askPx"], data.get("vol24h"), source="okx")


PUBLIC_WS_URLS = {
    "coinbase": "wss://advanced-trade-ws.coinbase.com",
    "kraken": "wss://ws.kraken.com/v2",
    "okx": "wss://ws.okx.com:8443/ws/v5/public",
}


def canonical_symbol(source: str, symbol: str) -> str:
    value = symbol.upper().replace("-", "").replace("/", "")
    if source == "kraken" and value.startswith("XBT"):
        value = "BTC" + value[3:]
    if value.endswith("USD"):
        value = value[:-3] + "USDT"
    return value


def subscription_for(source: str) -> dict[str, Any]:
    if source == "coinbase":
        return coinbase_subscription()
    if source == "kraken":
        return kraken_subscription()
    if source == "okx":
        return okx_subscription()
    raise ValueError(f"unsupported public source: {source}")


def normalize_message(source: str, payload: Any) -> list[dict[str, Any]]:
    if source == "coinbase":
        events = payload.get("events", []) if isinstance(payload, Mapping) else []
        return [normalize_coinbase_ticker({"events": [event]}) for event in events if event.get("tickers")]
    if source == "kraken":
        if isinstance(payload, Mapping) and payload.get("channel") == "ticker" and payload.get("data"):
            return [normalize_kraken_ticker(payload)]
        return []
    if source == "okx":
        if isinstance(payload, Mapping) and payload.get("arg", {}).get("channel") == "tickers" and payload.get("data"):
            return [normalize_okx_ticker(payload)]
        return []
    return []


def build_confirmation(snapshots: Sequence[Mapping[str, Any]], *, now_ms: int | None = None, max_age_ms: int = 5_000) -> dict[str, Any]:
    now = int(now_ms if now_ms is not None else time() * 1000)
    fresh = [row for row in snapshots if float(row.get("mid_price", 0)) > 0 and now - int(row.get("received_time_ms", 0)) <= max_age_ms]
    prices = [float(row["mid_price"]) for row in fresh]
    reference = median(prices) if prices else None
    disagreement_bps = (max(prices) - min(prices)) / reference * 10000 if reference and len(prices) > 1 else None
    required_sources = {"binance", "coinbase", "kraken", "okx"}
    fresh_sources = {str(row.get("source")) for row in fresh}
    return {
        "source_count": len(fresh),
        "reference_price": reference,
        "disagreement_bps": disagreement_bps,
        "confirmation_status": "CONFIRMED" if required_sources.issubset(fresh_sources) and (disagreement_bps is None or disagreement_bps <= 20) else "UNAVAILABLE",
        "sources": sorted(fresh_sources),
        "timestamp_ms": now,
    }
