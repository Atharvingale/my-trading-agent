"""Position and trade contracts with excursion analytics (Module 8).

Why separate math helpers: MFE/MAE, slippage, and PnL must be pure functions
of recorded prices so tests can prove them against a synthetic price path.
Positions are long-only in v1 (matching the paper portfolio): a position
holds one entry order and accumulates partial fills until closed by an exit
order of the opposite side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Position:
    position_id: str
    symbol: str
    side: str
    entry_order_id: str
    quantity: float
    entry_price: float
    stop: float = 0.0
    target: float = 0.0
    fees: float = 0.0
    funding: float = 0.0
    filled_quantity: float = 0.0
    exit_filled_quantity: float = 0.0
    realized_pnl: float = 0.0
    mfe: float = 0.0
    mae: float = 0.0
    slippage_bps_sum: float = 0.0
    slippage_samples: int = 0
    latency_ms_total: int = 0
    latency_samples: int = 0
    opened_at_ms: int = 0
    closed_at_ms: int | None = None
    amendments: int = 0
    reconcile_state: str = "CLEAN"
    mark_price: float = 0.0
    price_path: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.position_id.strip():
            raise ValueError("position_id must be non-empty")
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if self.quantity <= 0:
            raise ValueError("position quantity must be positive")
        if self.entry_price <= 0:
            raise ValueError("entry price must be positive")

    def exposure(self) -> float:
        return self.quantity * self.entry_price

    def open_quantity(self) -> float:
        return max(0.0, self.filled_quantity - self.exit_filled_quantity)

    def is_closed(self) -> bool:
        return self.closed_at_ms is not None

    def unrealized_pnl(self, mark_price: float) -> float:
        if self.side == "BUY":
            return (mark_price - self.entry_price) * self.filled_quantity
        return (self.entry_price - mark_price) * self.filled_quantity

    def average_slippage_bps(self) -> float | None:
        if self.slippage_samples == 0:
            return None
        return self.slippage_bps_sum / float(self.slippage_samples)

    def average_latency_ms(self) -> float | None:
        if self.latency_samples == 0:
            return None
        return float(self.latency_ms_total) / float(self.latency_samples)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        result["position_id"] = self.position_id
        result["symbol"] = self.symbol
        result["side"] = self.side
        result["entry_order_id"] = self.entry_order_id
        result["quantity"] = self.quantity
        result["entry_price"] = self.entry_price
        result["filled_quantity"] = self.filled_quantity
        result["exit_filled_quantity"] = self.exit_filled_quantity
        result["open_quantity"] = self.open_quantity()
        result["realized_pnl"] = self.realized_pnl
        result["fees"] = self.fees
        result["funding"] = self.funding
        result["mfe"] = self.mfe
        result["mae"] = self.mae
        result["stop"] = self.stop
        result["target"] = self.target
        result["reconcile_state"] = self.reconcile_state
        result["closed_at_ms"] = self.closed_at_ms
        return result


@dataclass(frozen=True)
class Trade:
    trade_id: str
    position_id: str
    entry_order_id: str
    exit_order_id: str
    decision_id: str
    execution_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    realized_pnl: float
    fees: float
    funding: float
    mfe: float
    mae: float
    duration_ms: int
    avg_slippage_bps: float | None
    avg_latency_ms: float | None
    amendments: int

    def net_pnl(self) -> float:
        return self.realized_pnl - self.fees - self.funding


def position_pnl(side: str, entry_price: float, exit_price: float, quantity: float) -> float:
    """Gross realized PnL for a closed quantity (fees handled separately)."""
    if side == "BUY":
        return (exit_price - entry_price) * quantity
    return (entry_price - exit_price) * quantity


def excursion(side: str, entry_price: float, price_path: list[float]) -> tuple[float, float]:
    """Return (MFE, MAE) in price points over the path while open.

    MFE is the best favorable move, MAE the worst adverse move. Both are
    non-negative magnitudes so a flat path yields (0, 0).
    """
    mfe = 0.0
    mae = 0.0
    for price in price_path:
        if side == "BUY":
            favorable = price - entry_price
            adverse = entry_price - price
        else:
            favorable = entry_price - price
            adverse = price - entry_price
        if favorable > mfe:
            mfe = favorable
        if adverse > mae:
            mae = adverse
    return mfe, mae
