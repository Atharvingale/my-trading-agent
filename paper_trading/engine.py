"""Thin paper-trading orchestrator (Step 1B).

Ties the fill simulator to the portfolio: one hypothetical order in,
simulated fills out, portfolio updated. Batch helper replays an ordered list
of (order, market snapshot) pairs so research scripts can simulate a whole
decision trail deterministically. Still no network, no credentials.
"""

from __future__ import annotations

from typing import Any, Mapping

from paper_trading.portfolio import PaperPortfolio
from paper_trading.simulator import PaperFill, PaperOrder, execution_report, simulate_fill


class PaperEngine:
    def __init__(self, portfolio: PaperPortfolio | None = None, *, starting_cash: float = 10000.0) -> None:
        if portfolio is not None:
            if not isinstance(portfolio, PaperPortfolio):
                raise TypeError("portfolio must be a PaperPortfolio")
            self.portfolio = portfolio
        else:
            self.portfolio = PaperPortfolio(starting_cash=starting_cash)
        self.orders: list[PaperOrder] = []
        self.fills: list[PaperFill] = []

    def submit(
        self,
        order: PaperOrder,
        market: Mapping[str, Any],
        *,
        fee_rate: float = 0.001,
        slippage_bps: float = 10.0,
        timestamp_ms: int | None = None,
    ) -> dict[str, Any]:
        # One order, one snapshot: fills simulate first, then the portfolio
        # applies them, so a rejected fill never moves cash.
        fills = simulate_fill(order, market, fee_rate=fee_rate, slippage_bps=slippage_bps, timestamp_ms=timestamp_ms)
        for fill in fills:
            self.portfolio.apply_fill(fill)
            self.fills.append(fill)
        self.orders.append(order)
        report = execution_report(order, fills)
        return report

    def replay(self, trail: list[tuple[PaperOrder, Mapping[str, Any]]], **kwargs: Any) -> list[dict[str, Any]]:
        # Deterministic replay in caller order; each step uses its own snapshot
        # so latency modeling stays with the research script, not the engine.
        reports: list[dict[str, Any]] = []
        for order, market in trail:
            reports.append(self.submit(order, market, **kwargs))
        return reports

    def equity(self, prices: dict[str, float]) -> float:
        return self.portfolio.equity(prices)

    def snapshot(self) -> dict[str, Any]:
        state = self.portfolio.snapshot()
        state["order_count"] = len(self.orders)
        state["fill_count"] = len(self.fills)
        return state
