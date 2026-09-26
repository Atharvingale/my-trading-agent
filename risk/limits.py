"""Configuration-driven risk limits (Module 6).

Why a separate limits module: every threshold lives in one frozen dataclass
so launch values are auditable and no check hides a hardcoded number. Each
check is a pure function returning (ok, reason) in a fixed order, so a
rejection always names the first failed rule.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    # Launch values are conservative spot defaults; logged at promotion.
    max_position_notional_per_symbol: float = 1000.0
    max_portfolio_notional: float = 3000.0
    max_total_notional: float = 3000.0
    max_concurrent_positions: int = 3
    max_daily_loss: float = 200.0
    max_drawdown_rate: float = 0.10
    max_leverage: float = 1.0
    risk_per_trade: float = 0.01
    min_stop_distance_bps: float = 10.0
    max_stop_distance_bps: float = 500.0
    max_spread_bps: float = 25.0
    max_depth_fraction: float = 0.25
    min_order_notional: float = 10.0
    cooldown_seconds_after_stop: int = 3600

    def __post_init__(self) -> None:
        # Fail-closed construction: a misconfigured limit file raises here,
        # never as a silent trade-time surprise.
        numbers = {
            "max_position_notional_per_symbol": self.max_position_notional_per_symbol,
            "max_portfolio_notional": self.max_portfolio_notional,
            "max_total_notional": self.max_total_notional,
            "max_daily_loss": self.max_daily_loss,
            "max_drawdown_rate": self.max_drawdown_rate,
            "max_leverage": self.max_leverage,
            "risk_per_trade": self.risk_per_trade,
            "min_stop_distance_bps": self.min_stop_distance_bps,
            "max_stop_distance_bps": self.max_stop_distance_bps,
            "max_spread_bps": self.max_spread_bps,
            "max_depth_fraction": self.max_depth_fraction,
            "min_order_notional": self.min_order_notional,
        }
        for name in numbers:
            value = numbers[name]
            if isinstance(value, bool) or not isinstance(value, (float, int)):
                raise ValueError(f"{name} must be a number")
            if not value > 0:
                raise ValueError(f"{name} must be positive")
        if self.max_concurrent_positions < 1:
            raise ValueError("max_concurrent_positions must be at least 1")
        if self.cooldown_seconds_after_stop < 0:
            raise ValueError("cooldown_seconds_after_stop must be non-negative")
        if self.min_stop_distance_bps > self.max_stop_distance_bps:
            raise ValueError("min_stop_distance_bps must not exceed max_stop_distance_bps")
        if self.max_depth_fraction > 1.0:
            raise ValueError("max_depth_fraction must not exceed 1.0")
        if self.max_drawdown_rate >= 1.0:
            raise ValueError("max_drawdown_rate must be below 1.0")
        if self.risk_per_trade >= 1.0:
            raise ValueError("risk_per_trade must be below 1.0")


def check_symbol_exposure(
    limits: RiskLimits, symbol_exposure: float, new_notional: float
) -> tuple[bool, str | None]:
    if symbol_exposure + new_notional > limits.max_position_notional_per_symbol:
        return False, "symbol exposure %.2f + %.2f exceeds per-symbol max %.2f" % (
            symbol_exposure, new_notional, limits.max_position_notional_per_symbol)
    return True, None


def check_portfolio_exposure(
    limits: RiskLimits, open_notional: float, new_notional: float
) -> tuple[bool, str | None]:
    if open_notional + new_notional > limits.max_portfolio_notional:
        return False, "portfolio exposure %.2f + %.2f exceeds max %.2f" % (
            open_notional, new_notional, limits.max_portfolio_notional)
    if open_notional + new_notional > limits.max_total_notional:
        return False, "total notional %.2f + %.2f exceeds max %.2f" % (
            open_notional, new_notional, limits.max_total_notional)
    return True, None


def check_concurrent_positions(
    limits: RiskLimits, open_positions: int
) -> tuple[bool, str | None]:
    if open_positions >= limits.max_concurrent_positions:
        return False, "open positions %d at max %d" % (
            open_positions, limits.max_concurrent_positions)
    return True, None


def check_daily_loss(limits: RiskLimits, daily_realized_pnl: float) -> tuple[bool, str | None]:
    if daily_realized_pnl <= -limits.max_daily_loss:
        return False, "daily realized %.2f at loss limit %.2f" % (
            daily_realized_pnl, limits.max_daily_loss)
    return True, None


def check_drawdown(limits: RiskLimits, equity: float, peak_equity: float) -> tuple[bool, str | None]:
    if peak_equity <= 0:
        return False, "peak equity %.2f is not positive" % peak_equity
    drawdown = (peak_equity - equity) / peak_equity
    if drawdown >= limits.max_drawdown_rate:
        return False, "drawdown %.4f at limit %.4f" % (drawdown, limits.max_drawdown_rate)
    return True, None


def check_leverage(limits: RiskLimits, total_notional_after: float, equity: float) -> tuple[bool, str | None]:
    if equity <= 0:
        return False, "equity %.2f is not positive" % equity
    leverage = total_notional_after / equity
    if leverage > limits.max_leverage:
        return False, "leverage %.4f exceeds max %.4f" % (leverage, limits.max_leverage)
    return True, None


def check_stop_distance(
    limits: RiskLimits, reference_price: float, stop_price: float
) -> tuple[bool, str | None]:
    if reference_price <= 0 or stop_price <= 0:
        return False, "reference %.2f and stop %.2f must be positive" % (reference_price, stop_price)
    distance_bps = abs(reference_price - stop_price) / reference_price * 10000.0
    if distance_bps < limits.min_stop_distance_bps:
        return False, "stop distance %.2f bps below minimum %.2f" % (
            distance_bps, limits.min_stop_distance_bps)
    if distance_bps > limits.max_stop_distance_bps:
        return False, "stop distance %.2f bps above maximum %.2f" % (
            distance_bps, limits.max_stop_distance_bps)
    return True, None


def check_liquidity(
    limits: RiskLimits, order_notional: float, depth_notional: float | None, spread_bps: float | None
) -> tuple[bool, str | None]:
    if spread_bps is not None:
        if spread_bps > limits.max_spread_bps:
            return False, "spread %.2f bps exceeds max %.2f" % (spread_bps, limits.max_spread_bps)
    if depth_notional is None:
        return False, "no depth quote available"
    if depth_notional <= 0:
        return False, "depth %.2f is not positive" % depth_notional
    if order_notional > depth_notional * limits.max_depth_fraction:
        return False, "order notional %.2f exceeds %.0f%% of depth %.2f" % (
            order_notional, limits.max_depth_fraction * 100.0, depth_notional)
    return True, None


def check_cooldown(
    limits: RiskLimits, now_ms: int, last_stopout_ms: int | None
) -> tuple[bool, str | None]:
    if last_stopout_ms is None:
        return True, None
    elapsed_seconds = (int(now_ms) - int(last_stopout_ms)) / 1000.0
    if elapsed_seconds < 0:
        return False, "clock moved backwards since stop-out"
    if elapsed_seconds < float(limits.cooldown_seconds_after_stop):
        return False, "cooldown active: %.0fs since stop-out, need %ds" % (
            elapsed_seconds, limits.cooldown_seconds_after_stop)
    return True, None
