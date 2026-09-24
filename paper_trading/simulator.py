"""Hypothetical-fill simulator (Step 1B).

Pure function over caller-supplied snapshots: no network, no credentials, no
clock reads inside the math (timestamps flow in from the caller). Latency is
modeled by the caller passing the post-delay snapshot, which keeps the model
honest about what information was actually available at execution time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid5, NAMESPACE_URL


class InsufficientPositionError(ValueError):
    """Raised when a simulated SELL exceeds the paper position (no margin in v1)."""


@dataclass(frozen=True)
class PaperOrder:
    order_id: str
    symbol: str
    side: str
    quantity: float
    requested_price: float | None
    timestamp_ms: int

    def __post_init__(self) -> None:
        # Fail-closed order entry: an ambiguous order never simulates.
        if not self.order_id.strip():
            raise ValueError("order_id must be non-empty")
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if isinstance(self.quantity, bool):
            raise ValueError("quantity must be a positive number")
        try:
            qty = float(self.quantity)
        except (TypeError, ValueError):
            raise ValueError("quantity must be a positive number")
        if not qty > 0:
            raise ValueError("quantity must be positive")
        if self.requested_price is not None and not isinstance(self.requested_price, bool):
            try:
                price = float(self.requested_price)
            except (TypeError, ValueError):
                raise ValueError("requested_price must be a number or None")
            if not price > 0:
                raise ValueError("requested_price must be positive")


@dataclass(frozen=True)
class PaperFill:
    fill_id: str
    order_id: str
    symbol: str
    side: str
    requested_quantity: float
    filled_quantity: float
    requested_price: float | None
    fill_price: float
    fee_paid: float
    slippage_cost: float
    status: str
    reason: str | None
    timestamp_ms: int

    def notional(self) -> float:
        return self.filled_quantity * self.fill_price


def make_order_id(*, symbol: str, side: str, quantity: float, timestamp_ms: int) -> str:
    # Deterministic IDs so paper runs are reproducible from the same inputs.
    seed = "%s|%s|%.10f|%d" % (str(symbol).strip().upper(), str(side).strip().upper(), float(quantity), int(timestamp_ms))
    return str(uuid5(NAMESPACE_URL, "paper-order:" + seed))


def simulate_fill(
    order: PaperOrder,
    market: Mapping[str, Any],
    *,
    fee_rate: float = 0.001,
    slippage_bps: float = 10.0,
    timestamp_ms: int | None = None,
) -> list[PaperFill]:
    """Simulate fills of one paper order against one market snapshot.

    Market snapshot keys: bid, ask (preferred) or price + spread_bps fallback,
    plus optional depth_qty capping the immediately available quantity. A thin
    book yields a PARTIAL fill with the remainder explicitly unfilled rather
    than silently assumed. Returns a list (usually one fill) for a uniform
    downstream shape.
    """
    if not isinstance(order, PaperOrder):
        raise TypeError("order must be a PaperOrder")
    fee = float(fee_rate)
    slip_bps = float(slippage_bps)
    if not 0.0 <= fee <= 0.05:
        raise ValueError("fee_rate must be within [0, 0.05]")
    if not 0.0 <= slip_bps <= 500.0:
        raise ValueError("slippage_bps must be within [0, 500]")
    bid = _optional_float(market.get("bid"))
    ask = _optional_float(market.get("ask"))
    if bid is None or ask is None:
        mid = _optional_float(market.get("price"))
        spread = _optional_float(market.get("spread_bps"))
        if mid is None:
            raise ValueError("market snapshot needs bid/ask or price")
        half = (spread if spread is not None else 2.0) / 2.0 / 10000.0
        bid = mid * (1.0 - half)
        ask = mid * (1.0 + half)
    if not bid > 0 or not ask > 0 or ask < bid:
        raise ValueError("market bid/ask must be positive with ask >= bid")
    depth = _optional_float(market.get("depth_qty"))
    if depth is not None and not depth >= 0:
        raise ValueError("depth_qty must be non-negative when provided")
    available = float(order.quantity) if depth is None else min(float(order.quantity), depth)
    if available <= 0:
        fill = PaperFill(
            fill_id=str(uuid5(NAMESPACE_URL, "paper-fill:" + order.order_id + ":empty")),
            order_id=order.order_id,
            symbol=str(order.symbol).strip().upper(),
            side=order.side,
            requested_quantity=float(order.quantity),
            filled_quantity=0.0,
            requested_price=order.requested_price,
            fill_price=(ask if order.side == "BUY" else bid),
            fee_paid=0.0,
            slippage_cost=0.0,
            status="REJECTED",
            reason="EMPTY_BOOK",
            timestamp_ms=int(timestamp_ms) if timestamp_ms is not None else order.timestamp_ms,
        )
        return [fill]
    reference = ask if order.side == "BUY" else bid
    slip_rate = slip_bps / 10000.0
    if order.side == "BUY":
        fill_price = reference * (1.0 + slip_rate)
    else:
        fill_price = reference * (1.0 - slip_rate)
    notional = available * fill_price
    fee_paid = notional * fee
    slippage_cost = abs(fill_price - reference) * available
    status = "FILLED"
    reason = None
    if available < float(order.quantity):
        status = "PARTIAL"
        reason = "INSUFFICIENT_DEPTH"
    moment = int(timestamp_ms) if timestamp_ms is not None else order.timestamp_ms
    fill = PaperFill(
        fill_id=str(uuid5(NAMESPACE_URL, "paper-fill:" + order.order_id + ":0")),
        order_id=order.order_id,
        symbol=str(order.symbol).strip().upper(),
        side=order.side,
        requested_quantity=float(order.quantity),
        filled_quantity=available,
        requested_price=order.requested_price,
        fill_price=fill_price,
        fee_paid=fee_paid,
        slippage_cost=slippage_cost,
        status=status,
        reason=reason,
        timestamp_ms=moment,
    )
    return [fill]


def execution_report(order: PaperOrder, fills: list[PaperFill]) -> dict[str, Any]:
    """Expected-vs-realized summary for one paper order.

    Expected price is the requested price when given, else the fill reference
    is unavailable and expected slippage reports as None rather than zero, so
    missing expectations are never mistaken for perfect execution.
    """
    filled_qty = 0.0
    paid = 0.0
    fees = 0.0
    slips = 0.0
    for fill in fills:
        filled_qty += fill.filled_quantity
        paid += fill.filled_quantity * fill.fill_price
        fees += fill.fee_paid
        slips += fill.slippage_cost
    average = paid / filled_qty if filled_qty > 0 else None
    expected_slippage_bps: float | None = None
    if order.requested_price is not None and average is not None and order.requested_price > 0:
        if order.side == "BUY":
            expected_slippage_bps = (average - order.requested_price) / order.requested_price * 10000.0
        else:
            expected_slippage_bps = (order.requested_price - average) / order.requested_price * 10000.0
    statuses: list[str] = []
    for fill in fills:
        if fill.status not in statuses:
            statuses.append(fill.status)
    if filled_qty >= float(order.quantity):
        overall = "FILLED"
    elif filled_qty > 0:
        overall = "PARTIAL"
    else:
        overall = "REJECTED"
    return {
        "order_id": order.order_id,
        "symbol": str(order.symbol).strip().upper(),
        "side": order.side,
        "requested_quantity": float(order.quantity),
        "filled_quantity": filled_qty,
        "average_fill_price": average,
        "fees_paid": fees,
        "slippage_cost": slips,
        "expected_slippage_bps": expected_slippage_bps,
        "status": overall,
        "fill_statuses": statuses,
    }


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
        return number
    except (TypeError, ValueError):
        return None


def _utc_now_ms() -> int:
    # Only used by callers that explicitly want wall-clock stamping; the math
    # above never reads the clock on its own.
    return int(datetime.now(timezone.utc).timestamp() * 1000)
