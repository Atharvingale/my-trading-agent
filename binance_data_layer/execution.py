"""Deterministic order-book execution estimates."""
from __future__ import annotations

from typing import Sequence


def estimate_execution(*, side: str, quantity: float, bids: Sequence[tuple[float, float]], asks: Sequence[tuple[float, float]], fee_rate: float = 0.001) -> dict:
    side = side.upper()
    levels = sorted((float(p), float(q)) for p, q in (asks if side == "BUY" else bids) if float(p) > 0 and float(q) > 0)
    if side == "SELL":
        levels.reverse()
    if not levels or quantity <= 0:
        return {"status": "BAD", "reason": "EMPTY_BOOK", "filled_quantity": 0.0, "depth_within_bps": {5: 0.0, 10: 0.0, 25: 0.0}}
    best = levels[0][0]
    filled = 0.0
    notional = 0.0
    remaining = float(quantity)
    for price, available in levels:
        take = min(remaining, available)
        filled += take
        notional += take * price
        remaining -= take
        if remaining <= 0:
            break
    mid = best
    depth_bands = {}
    for bps in (5, 10, 25):
        limit = mid * (1 + bps / 10000) if side == "BUY" else mid * (1 - bps / 10000)
        depth_bands[bps] = sum(q for price, q in levels if price <= limit) if side == "BUY" else sum(q for price, q in levels if price >= limit)
    avg = notional / filled if filled else None
    impact = ((avg - mid) / mid) if avg is not None and side == "BUY" else ((mid - avg) / mid if avg is not None else None)
    slippage_rate = max(0.0, impact or 0.0)
    return {
        "status": "OK" if remaining <= 0 else "INSUFFICIENT_DEPTH",
        "reason": None if remaining <= 0 else "INSUFFICIENT_DEPTH",
        "filled_quantity": filled,
        "average_price": avg,
        "price_impact_rate": impact,
        "depth_within_bps": depth_bands,
        "round_trip_cost_rate": 2 * fee_rate + 2 * slippage_rate,
    }
