"""Pure feature calculations from normalized Binance market data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def build_feature_snapshot(
    *,
    symbol: str,
    event_time: datetime,
    last_price: float | None,
    bid_price: float | None,
    ask_price: float | None,
    bid_qty: float,
    ask_qty: float,
    recent_trades: Iterable[Mapping[str, Any]],
    bids: Sequence[tuple[float, float]],
    asks: Sequence[tuple[float, float]],
) -> dict[str, Any]:
    """Build reproducible order-flow and liquidity features.

    Binance ``is_buyer_maker`` means the buyer was the maker. Therefore a
    false value represents an aggressive buyer and contributes positively to
    CVD; a true value represents an aggressive seller.
    """
    trades = list(recent_trades)
    buy_volume = sum(float(t["qty"]) for t in trades if not bool(t["is_buyer_maker"]))
    sell_volume = sum(float(t["qty"]) for t in trades if bool(t["is_buyer_maker"]))
    trade_volume = buy_volume + sell_volume

    top_total = bid_qty + ask_qty
    depth_bid = sum(float(qty) for _, qty in bids)
    depth_ask = sum(float(qty) for _, qty in asks)
    depth_total = depth_bid + depth_ask

    spread_bps = None
    if bid_price is not None and ask_price is not None and last_price:
        spread_bps = round(((ask_price - bid_price) / last_price) * 10_000, 10)

    return {
        "symbol": symbol,
        "event_time": _iso_utc(event_time),
        "last_price": last_price,
        "spread_bps": spread_bps,
        "top_book_imbalance": _safe_ratio(bid_qty - ask_qty, top_total),
        "depth_imbalance": _safe_ratio(depth_bid - depth_ask, depth_total),
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "trade_volume": trade_volume,
        "trade_cvd": buy_volume - sell_volume,
        "bid_depth": depth_bid,
        "ask_depth": depth_ask,
    }
