"""Order and fill contracts with an explicit state machine (Module 8).

Why a closed transition table: an order must never jump from NEW to FILLED
without fills, and an ambiguous submission must never be assumed either way.
Every transition is checked against the table below, so illegal jumps raise
instead of silently corrupting position math.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class OrderState:
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"


# Legal transitions. SUBMISSION_UNKNOWN exits only through reconciliation
# (resolve_unknown), never through normal fill application.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    OrderState.NEW: (
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELED,
        OrderState.REJECTED,
        OrderState.SUBMISSION_UNKNOWN,
    ),
    OrderState.PARTIALLY_FILLED: (
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELED,
        OrderState.SUBMISSION_UNKNOWN,
    ),
    OrderState.SUBMISSION_UNKNOWN: (
        OrderState.FILLED,
        OrderState.PARTIALLY_FILLED,
        OrderState.CANCELED,
        OrderState.REJECTED,
    ),
    OrderState.FILLED: (),
    OrderState.CANCELED: (),
    OrderState.REJECTED: (),
}


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    price: float
    quantity: float
    fee: float = 0.0
    funding: float = 0.0
    latency_ms: int | None = None
    expected_price: float | None = None

    def __post_init__(self) -> None:
        # Fail-closed construction: a fill with no quantity or no price can
        # never enter position math, so it is rejected at the boundary.
        if not self.fill_id.strip():
            raise ValueError("fill_id must be non-empty")
        if not self.order_id.strip():
            raise ValueError("order_id must be non-empty")
        if self.price <= 0:
            raise ValueError("fill price must be positive")
        if self.quantity <= 0:
            raise ValueError("fill quantity must be positive")
        if self.fee < 0 or self.funding < 0:
            raise ValueError("fill fee and funding must be non-negative")

    def slippage_bps(self) -> float | None:
        """Actual vs expected price in bps; None when no expectation was set."""
        if self.expected_price is None or self.expected_price <= 0:
            return None
        return (self.price - self.expected_price) / self.expected_price * 10000.0


@dataclass
class Order:
    order_id: str
    execution_id: str
    decision_id: str
    symbol: str
    side: str
    quantity: float
    order_type: str
    state: str = OrderState.NEW
    filled_quantity: float = 0.0
    amendments: int = 0
    submit_latency_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.order_id.strip():
            raise ValueError("order_id must be non-empty")
        if not self.execution_id.strip():
            raise ValueError("execution_id must be non-empty")
        if not self.decision_id.strip():
            raise ValueError("decision_id must be non-empty")
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if self.quantity <= 0:
            raise ValueError("order quantity must be positive")
        if self.state not in TRANSITIONS:
            raise ValueError("unknown order state: %s" % self.state)

    def remaining(self) -> float:
        return max(0.0, self.quantity - self.filled_quantity)

    def transition(self, target: str) -> None:
        """Move state; raises on any illegal jump (never silently forced)."""
        allowed = TRANSITIONS[self.state]
        found = False
        for candidate in allowed:
            if candidate == target:
                found = True
        if found is False:
            raise ValueError("illegal order transition %s -> %s" % (self.state, target))
        self.state = target

    def apply_fill(self, fill: Fill) -> None:
        """Attach one fill; drives NEW/PARTIAL toward FILLED deterministically."""
        if fill.order_id != self.order_id:
            raise ValueError("fill %s belongs to order %s" % (fill.fill_id, fill.order_id))
        if self.state in (OrderState.FILLED, OrderState.CANCELED, OrderState.REJECTED):
            raise ValueError("order %s is terminal in %s" % (self.order_id, self.state))
        if self.state == OrderState.SUBMISSION_UNKNOWN:
            raise ValueError("order %s is SUBMISSION_UNKNOWN: reconcile first" % self.order_id)
        if fill.quantity > self.remaining() + 1e-9:
            raise ValueError("fill quantity %.6f exceeds remaining %.6f" % (
                fill.quantity, self.remaining()))
        self.filled_quantity = self.filled_quantity + fill.quantity
        if self.filled_quantity + 1e-9 >= self.quantity:
            self.filled_quantity = self.quantity
            self.transition(OrderState.FILLED)
        elif self.state == OrderState.NEW:
            self.transition(OrderState.PARTIALLY_FILLED)

    def mark_unknown(self) -> None:
        """Flag an ambiguous submission (timeout with no confirmation)."""
        self.transition(OrderState.SUBMISSION_UNKNOWN)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        result["order_id"] = self.order_id
        result["execution_id"] = self.execution_id
        result["decision_id"] = self.decision_id
        result["symbol"] = self.symbol
        result["side"] = self.side
        result["quantity"] = self.quantity
        result["order_type"] = self.order_type
        result["state"] = self.state
        result["filled_quantity"] = self.filled_quantity
        result["remaining"] = self.remaining()
        result["amendments"] = self.amendments
        return result
