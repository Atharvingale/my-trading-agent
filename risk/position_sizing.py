"""Exact deterministic position sizing (Module 6).

Why a separate module: the quantity approved here is sealed into the
RiskDecision hash and Module 7 must verify it verbatim. Sizing is pure
arithmetic from equity, risk fraction, entry, and stop — no judgment, no
rounding downstream. Capping order is fixed (risk amount, then notional caps,
then depth cap) so reruns are byte-identical.
"""

from __future__ import annotations


def calculate_quantity(
    *,
    equity: float,
    risk_per_trade: float,
    entry_price: float,
    stop_price: float,
    max_position_notional: float,
    depth_notional: float | None = None,
    max_depth_fraction: float = 0.25,
) -> float:
    """Return the exact base-asset quantity for one trade.

    risk_amount = equity * risk_per_trade; quantity = risk_amount /
    |entry - stop|, then capped so entry*quantity fits the notional and depth
    budgets. Raises when any input cannot produce a positive size.
    """
    if isinstance(equity, bool) or not isinstance(equity, (float, int)):
        raise ValueError("equity must be a number")
    if equity <= 0:
        raise ValueError("equity must be positive")
    if isinstance(risk_per_trade, bool) or not isinstance(risk_per_trade, (float, int)):
        raise ValueError("risk_per_trade must be a number")
    if not 0.0 < float(risk_per_trade) < 1.0:
        raise ValueError("risk_per_trade must be in (0, 1)")
    if entry_price <= 0 or stop_price <= 0:
        raise ValueError("entry and stop prices must be positive")
    distance = abs(float(entry_price) - float(stop_price))
    if distance <= 0:
        raise ValueError("entry and stop must differ")
    risk_amount = float(equity) * float(risk_per_trade)
    quantity = risk_amount / distance
    notional = quantity * float(entry_price)
    if notional > float(max_position_notional):
        quantity = float(max_position_notional) / float(entry_price)
        notional = quantity * float(entry_price)
    if depth_notional is not None:
        depth_cap = float(depth_notional) * float(max_depth_fraction)
        if depth_cap <= 0:
            raise ValueError("depth cap is not positive")
        if notional > depth_cap:
            quantity = depth_cap / float(entry_price)
    if quantity <= 0:
        raise ValueError("sized quantity is not positive")
    return float(quantity)
