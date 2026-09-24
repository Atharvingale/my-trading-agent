"""Paper portfolio: cash and positions updated only by simulated fills.

Long-only in v1: selling more than the held quantity raises instead of
creating margin debt, because silent leverage has no place in a simulator
whose output may one day inform real sizing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from paper_trading.simulator import InsufficientPositionError, PaperFill


@dataclass
class PositionLot:
    quantity: float
    average_price: float


@dataclass
class PaperPortfolio:
    starting_cash: float
    cash: float = 0.0
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    _positions: dict[str, PositionLot] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        try:
            starting = float(self.starting_cash)
        except (TypeError, ValueError):
            raise ValueError("starting_cash must be a positive number")
        if isinstance(self.starting_cash, bool) or not starting > 0:
            raise ValueError("starting_cash must be a positive number")
        if self.cash == 0.0:
            self.cash = starting

    def position_qty(self, symbol: str) -> float:
        lot = self._positions.get(str(symbol).strip().upper())
        if lot is None:
            return 0.0
        return lot.quantity

    def apply_fill(self, fill: PaperFill) -> None:
        # Cash moves on filled quantity only; fees leave with the fill.
        if not isinstance(fill, PaperFill):
            raise TypeError("fill must be a PaperFill")
        if fill.filled_quantity <= 0:
            return
        token = str(fill.symbol).strip().upper()
        notional = fill.filled_quantity * fill.fill_price
        if fill.side == "BUY":
            cost = notional + fill.fee_paid
            if cost > self.cash + 1e-9:
                raise InsufficientPositionError("paper cash insufficient for simulated BUY")
            self.cash -= cost
            self.fees_paid += fill.fee_paid
            lot = self._positions.get(token)
            if lot is None:
                self._positions[token] = PositionLot(quantity=fill.filled_quantity, average_price=fill.fill_price)
            else:
                combined = lot.quantity + fill.filled_quantity
                blended = (lot.quantity * lot.average_price + fill.filled_quantity * fill.fill_price) / combined
                self._positions[token] = PositionLot(quantity=combined, average_price=blended)
        else:
            lot = self._positions.get(token)
            held = lot.quantity if lot is not None else 0.0
            if fill.filled_quantity > held + 1e-9:
                raise InsufficientPositionError("paper position insufficient for simulated SELL")
            proceeds = notional - fill.fee_paid
            self.cash += proceeds
            self.fees_paid += fill.fee_paid
            if lot is not None:
                realized = (fill.fill_price - lot.average_price) * fill.filled_quantity
                self.realized_pnl += realized
                remaining = held - fill.filled_quantity
                if remaining <= 1e-9:
                    del self._positions[token]
                else:
                    self._positions[token] = PositionLot(quantity=remaining, average_price=lot.average_price)

    def equity(self, prices: dict[str, float]) -> float:
        # Mark-to-market on caller-supplied prices; unknown symbols mark at
        # cost so missing data never invents gains or losses.
        total = self.cash
        for symbol in self._positions:
            lot = self._positions[symbol]
            mark = prices.get(symbol)
            if mark is None or isinstance(mark, bool):
                total += lot.quantity * lot.average_price
                continue
            try:
                price = float(mark)
            except (TypeError, ValueError):
                price = lot.average_price
            if not price > 0:
                price = lot.average_price
            total += lot.quantity * price
        return total

    def snapshot(self) -> dict[str, Any]:
        positions: dict[str, dict[str, float]] = {}
        for symbol in self._positions:
            lot = self._positions[symbol]
            positions[symbol] = {"quantity": lot.quantity, "average_price": lot.average_price}
        return {
            "cash": self.cash,
            "starting_cash": float(self.starting_cash),
            "realized_pnl": self.realized_pnl,
            "fees_paid": self.fees_paid,
            "positions": positions,
        }
