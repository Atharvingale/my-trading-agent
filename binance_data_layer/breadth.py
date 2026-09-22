"""Pure Binance market-wide ticker breadth and dynamic-universe ranking."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from time import time
from typing import Any
import re


def _items(message: Any) -> list[Mapping[str, Any]]:
    if isinstance(message, Mapping):
        data = message.get("data", message)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, Mapping)]
        if isinstance(data, Mapping):
            return [data]
    if isinstance(message, list):
        return [item for item in message if isinstance(item, Mapping)]
    return []


def normalize_ticker_array(message: Any, *, quote_assets: set[str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _items(message):
        symbol = str(item.get("s", "")).upper()
        if not symbol:
            continue
        if quote_assets and not any(symbol.endswith(quote) for quote in quote_assets):
            continue
        try:
            price = float(item["c"])
            open_price = float(item["o"])
            rows.append({
                "symbol": symbol,
                "price": price,
                "open": open_price,
                "change_pct": (price / open_price - 1.0) * 100.0 if open_price else None,
                "quote_volume": float(item.get("q", item.get("Q", 0.0))),
                "event_time_ms": int(item.get("E", item.get("O", int(time() * 1000)))),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return rows


def rank_trending_symbols(
    rows: Iterable[Mapping[str, Any]],
    *,
    pinned: Iterable[str] = (),
    top_n: int = 10,
    min_quote_volume: float = 0.0,
    excluded_symbols: Iterable[str] = (),
    symbol_pattern: str = r"^[A-Z0-9]{5,20}$",
) -> tuple[str, ...]:
    pattern = re.compile(symbol_pattern)
    pinned_set = tuple(dict.fromkeys(str(symbol).upper() for symbol in pinned))
    excluded = {str(symbol).upper() for symbol in excluded_symbols}
    eligible = []
    for row in rows:
        symbol = str(row.get("symbol", "")).upper()
        volume = float(row.get("quote_volume", 0.0) or 0.0)
        change = abs(float(row.get("change_pct", 0.0) or 0.0))
        if symbol and pattern.fullmatch(symbol) and symbol not in excluded and volume >= min_quote_volume:
            eligible.append((symbol, change, volume))
    eligible.sort(key=lambda item: (item[1], item[2]), reverse=True)
    selected = list(pinned_set)
    for symbol, _, _ in eligible:
        if symbol not in selected:
            selected.append(symbol)
        if len(selected) >= max(1, top_n):
            break
    return tuple(selected[:max(1, top_n)])


def calculate_breadth(rows: Iterable[Mapping[str, Any]], *, top_n: int = 10, timestamp_ms: int | None = None) -> dict[str, Any]:
    clean = [row for row in rows if float(row.get("price", 0)) > 0 and float(row.get("open", 0)) > 0]
    advancing = sum(float(row["price"]) > float(row["open"]) for row in clean)
    declining = sum(float(row["price"]) < float(row["open"]) for row in clean)
    unchanged = len(clean) - advancing - declining
    volumes = sorted((max(0.0, float(row.get("quote_volume", 0.0))) for row in clean), reverse=True)
    total_volume = sum(volumes)
    top_volume = sum(volumes[:max(0, top_n)])
    return {
        "eligible_count": len(clean),
        "advancing_count": advancing,
        "declining_count": declining,
        "unchanged_count": unchanged,
        "advance_decline_ratio": advancing / declining if declining else (None if advancing == 0 else float("inf")),
        "advancing_pct": advancing / len(clean) if clean else None,
        "aggregate_quote_volume": total_volume,
        "top_volume_concentration": top_volume / total_volume if total_volume else None,
        "timestamp_ms": int(timestamp_ms if timestamp_ms is not None else time() * 1000),
    }
