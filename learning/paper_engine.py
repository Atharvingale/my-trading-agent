"""Paper-simulation leg reusing the proven paper engine (Module 9).

Why a thin adapter: fill simulation with fee, slippage, and depth behavior
already exists in paper_trading and is tested. This module stages one
candidate evaluation through it and summarizes fill quality — expected vs
realized, slippage totals — without duplicating any simulation math.
"""

from __future__ import annotations

from typing import Any, Mapping

from paper_trading.engine import PaperEngine
from paper_trading.simulator import PaperOrder


def run_paper_leg(
    orders: list[dict[str, Any]],
    markets: list[Mapping[str, Any]],
    *,
    starting_cash: float = 10000.0,
    fee_rate: float = 0.001,
    slippage_bps: float = 10.0,
) -> dict[str, Any]:
    """Simulate one ordered leg of candidate orders offline, deterministically.

    Each order dict needs order_id, symbol, side, quantity, requested_price
    (or None), and timestamp_ms. Returns fills, per-order reports, slippage
    totals, and ending cash. No network, no credentials.
    """
    if len(orders) != len(markets):
        raise ValueError("orders and markets must be paired one-to-one")
    if len(orders) == 0:
        raise ValueError("paper leg needs at least one order")
    engine = PaperEngine(starting_cash=starting_cash)
    trail: list[tuple[PaperOrder, Mapping[str, Any]]] = []
    for index in range(len(orders)):
        spec = orders[index]
        order = PaperOrder(
            order_id=str(spec["order_id"]),
            symbol=str(spec["symbol"]),
            side=str(spec["side"]),
            quantity=float(spec["quantity"]),
            requested_price=spec.get("requested_price"),
            timestamp_ms=int(spec.get("timestamp_ms", 0)),
        )
        trail.append((order, markets[index]))
    reports = engine.replay(
        trail, fee_rate=fee_rate, slippage_bps=slippage_bps
    )
    slippage_total = 0.0
    filled_total = 0.0
    for fill in engine.fills:
        slippage_total = slippage_total + float(fill.slippage_cost)
        filled_total = filled_total + float(fill.filled_quantity)
    summary: dict[str, Any] = {}
    summary["reports"] = reports
    summary["fill_count"] = len(engine.fills)
    summary["filled_quantity"] = filled_total
    summary["slippage_total"] = slippage_total
    summary["snapshot"] = engine.snapshot()
    return summary
