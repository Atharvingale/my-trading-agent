"""Pure feature calculations from normalized Binance market data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from .execution import estimate_execution


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
    technical: Mapping[str, Any] | None = None,
    execution_quantity: float | None = None,
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
    aggressive_buy_pct = _safe_ratio(buy_volume, trade_volume)
    large_trade = max((float(t["qty"]) for t in trades), default=0.0)
    large_trade_concentration = _safe_ratio(large_trade, trade_volume)
    depth_within_bps: dict[int, dict[str, float | None]] = {}
    if last_price and last_price > 0:
        for bps in (5, 10, 25):
            bid_limit = last_price * (1 - bps / 10000)
            ask_limit = last_price * (1 + bps / 10000)
            depth_within_bps[bps] = {
                "bid_qty": sum(qty for price, qty in bids if price >= bid_limit),
                "ask_qty": sum(qty for price, qty in asks if price <= ask_limit),
            }
    else:
        depth_within_bps = {bps: {"bid_qty": None, "ask_qty": None} for bps in (5, 10, 25)}
    spread_bps = None
    if bid_price is not None and ask_price is not None and last_price:
        spread_bps = round(((ask_price - bid_price) / last_price) * 10_000, 10)
    if not bids and not asks:
        depth_within_bps = {bps: {"bid_qty": None, "ask_qty": None} for bps in (5, 10, 25)}
    spread_stability_bps = spread_bps
    quantity = float(execution_quantity) if execution_quantity is not None else 1.0
    execution_quality = {
        "BUY": estimate_execution(side="BUY", quantity=quantity, bids=bids, asks=asks),
        "SELL": estimate_execution(side="SELL", quantity=quantity, bids=bids, asks=asks),
    }
    return {
        "symbol": symbol,
        "event_time": _iso_utc(event_time),
        "last_price": last_price,
        "spread_bps": spread_bps,
        "spread_stability_bps": spread_stability_bps,
        "top_book_imbalance": _safe_ratio(bid_qty - ask_qty, top_total),
        "depth_imbalance": _safe_ratio(depth_bid - depth_ask, depth_total),
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "trade_volume": trade_volume,
        "trade_cvd": buy_volume - sell_volume,
        "rolling_cvd": buy_volume - sell_volume,
        "aggressive_buy_pct": aggressive_buy_pct,
        "large_trade_concentration": large_trade_concentration,
        "bid_depth": depth_bid,
        "ask_depth": depth_ask,
        "depth_within_bps": depth_within_bps,
        "execution_quality": execution_quality,
        "technical": dict(technical or {}),
    }
