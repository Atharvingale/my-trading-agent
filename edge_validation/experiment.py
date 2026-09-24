"""Causal, single-asset edge-validation backtest primitives."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Trade:
    entry_index: int
    exit_index: int
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    fees: float
    slippage: float
    tax: float
    tds: float
    net_pnl: float
    exit_reason: str


@dataclass(frozen=True)
class BacktestResult:
    trades: tuple[Trade, ...]
    starting_capital: float
    ending_capital: float
    gross_return: float
    net_return: float
    fees: float
    slippage: float
    tax: float
    tds: float


@dataclass(frozen=True)
class AcceptanceResult:
    passed: bool
    failed_criteria: tuple[str, ...]


def backtest_trend_following(
    candles: Sequence[Candle],
    *,
    starting_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    slippage_rate: float = 0.001,
    tax_rate: float = 0.312,
    tds_rate: float = 0.01,
    fast_period: int = 5,
    slow_period: int = 20,
    stop_loss_rate: float = 0.02,
    stress: bool = False,
) -> BacktestResult:
    """Run a causal long-only EMA crossover with spot friction and VDA tax.

    Signals use the completed candle at index ``i`` and execute at the next
    candle open. Stops are checked before signal exits on every held candle.
    The position is sized at 25% of available cash to keep this primitive
    deterministic and bounded; it is not an execution recommendation.
    """
    _validate_candles(candles)
    if starting_capital <= 0 or fee_rate < 0 or slippage_rate < 0:
        raise ValueError("capital and cost rates must be positive/non-negative")
    if fast_period < 2 or slow_period <= fast_period:
        raise ValueError("slow_period must exceed fast_period >= 2")
    multiplier = 2.0 if stress else 1.0
    fee = fee_rate * multiplier
    slippage = slippage_rate * multiplier
    cash = starting_capital
    trades = []
    position = None
    gross_total = 0.0
    fee_total = 0.0
    slip_total = 0.0
    tax_total = 0.0
    tds_total = 0.0

    index = slow_period
    while index < len(candles):
        candle = candles[index]
        if position is not None:
            stop_price = position["entry_price"] * (1.0 - stop_loss_rate)
            if candle.low <= stop_price:
                trade = _close_position(
                    position, index, stop_price, "STOP_LOSS", fee, slippage, tax_rate, tds_rate
                )
                cash += position["notional"] + trade.net_pnl
                trades.append(trade)
                gross_total += trade.gross_pnl
                fee_total += trade.fees
                slip_total += trade.slippage
                tax_total += trade.tax
                tds_total += trade.tds
                position = None
                index += 1
                continue
            if _ema(candles, index, fast_period) < _ema(candles, index, slow_period):
                exit_price = candle.close
                trade = _close_position(
                    position, index, exit_price, "SIGNAL", fee, slippage, tax_rate, tds_rate
                )
                cash += position["notional"] + trade.net_pnl
                trades.append(trade)
                gross_total += trade.gross_pnl
                fee_total += trade.fees
                slip_total += trade.slippage
                tax_total += trade.tax
                tds_total += trade.tds
                position = None
                index += 1
                continue
        if position is None and index + 1 < len(candles):
            prior_fast = _ema(candles, index - 1, fast_period)
            prior_slow = _ema(candles, index - 1, slow_period)
            current_fast = _ema(candles, index, fast_period)
            current_slow = _ema(candles, index, slow_period)
            if prior_fast <= prior_slow and current_fast > current_slow:
                entry_price = candles[index + 1].open * (1.0 + slippage)
                notional = cash * 0.25
                quantity = notional / entry_price
                entry_fee = notional * fee
                cash -= notional + entry_fee
                position = {
                    "entry_index": index + 1,
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "notional": notional,
                    "entry_fee": entry_fee,
                }
        index += 1

    if position is not None:
        trade = _close_position(
            position, len(candles) - 1, candles[-1].close, "END_OF_DATA", fee, slippage, tax_rate, tds_rate
        )
        cash += position["notional"] + trade.net_pnl
        trades.append(trade)
        gross_total += trade.gross_pnl
        fee_total += trade.fees
        slip_total += trade.slippage
        tax_total += trade.tax
        tds_total += trade.tds

    ending = cash
    return BacktestResult(
        trades=tuple(trades),
        starting_capital=starting_capital,
        ending_capital=ending,
        gross_return=gross_total / starting_capital,
        net_return=(ending - starting_capital) / starting_capital,
        fees=fee_total,
        slippage=slip_total,
        tax=tax_total,
        tds=tds_total,
    )


def backtest_mean_reversion(
    candles: Sequence[Candle],
    *,
    starting_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    slippage_rate: float = 0.001,
    tax_rate: float = 0.312,
    tds_rate: float = 0.01,
    lookback: int = 20,
    zscore: float = 1.0,
    stop_loss_rate: float = 0.02,
    stress: bool = False,
) -> BacktestResult:
    """Long-only z-score reversion: enter after completed oversold bars."""
    _validate_candles(candles)
    if lookback < 2:
        raise ValueError("lookback must be at least 2")

    def should_enter(index: int) -> bool:
        if index < lookback:
            return False
        closes = []
        start = index - lookback + 1
        while start <= index:
            closes.append(candles[start].close)
            start += 1
        mean = _mean(closes)
        stdev = _stdev(closes)
        if stdev == 0:
            return False
        return (closes[-1] - mean) / stdev <= -zscore

    def should_exit(index: int) -> bool:
        closes = []
        start = index - lookback + 1
        if start < 0:
            return False
        while start <= index:
            closes.append(candles[start].close)
            start += 1
        return candles[index].close >= _mean(closes)

    return _simulate_long_only(
        candles,
        starting_capital=starting_capital,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        tax_rate=tax_rate,
        tds_rate=tds_rate,
        stop_loss_rate=stop_loss_rate,
        stress=stress,
        start_index=lookback,
        should_enter=should_enter,
        should_exit=should_exit,
    )


def backtest_vwap_reversion(
    candles: Sequence[Candle],
    *,
    starting_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    slippage_rate: float = 0.001,
    tax_rate: float = 0.312,
    tds_rate: float = 0.01,
    lookback: int = 20,
    deviation: float = 0.02,
    stop_loss_rate: float = 0.02,
    stress: bool = False,
) -> BacktestResult:
    """Enter when a completed close is below VWAP by a fixed deviation."""
    _validate_candles(candles)
    if lookback < 2:
        raise ValueError("lookback must be at least 2")

    def should_enter(index: int) -> bool:
        if index < lookback - 1:
            return False
        vwap = _vwap(candles, index, lookback)
        if vwap <= 0:
            return False
        return candles[index].close <= vwap * (1.0 - deviation)

    def should_exit(index: int) -> bool:
        vwap = _vwap(candles, index, lookback)
        return candles[index].close >= vwap

    return _simulate_long_only(
        candles,
        starting_capital=starting_capital,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        tax_rate=tax_rate,
        tds_rate=tds_rate,
        stop_loss_rate=stop_loss_rate,
        stress=stress,
        start_index=lookback,
        should_enter=should_enter,
        should_exit=should_exit,
    )


def backtest_order_flow(
    candles: Sequence[Candle],
    *,
    starting_capital: float = 10_000.0,
    fee_rate: float = 0.001,
    slippage_rate: float = 0.001,
    tax_rate: float = 0.312,
    tds_rate: float = 0.01,
    lookback: int = 20,
    volume_multiple: float = 2.0,
    stop_loss_rate: float = 0.02,
    stress: bool = False,
) -> BacktestResult:
    """Enter after a completed volume expansion relative to recent bars."""
    _validate_candles(candles)
    if lookback < 2:
        raise ValueError("lookback must be at least 2")

    def should_enter(index: int) -> bool:
        if index < lookback:
            return False
        volumes = []
        start = index - lookback
        while start < index:
            volumes.append(candles[start].volume)
            start += 1
        average = _mean(volumes)
        return candles[index].volume > volume_multiple * average and average > 0

    def should_exit(index: int) -> bool:
        if index < lookback:
            return False
        volumes = []
        start = index - lookback
        while start < index:
            volumes.append(candles[start].volume)
            start += 1
        return candles[index].volume <= _mean(volumes)

    return _simulate_long_only(
        candles,
        starting_capital=starting_capital,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        tax_rate=tax_rate,
        tds_rate=tds_rate,
        stop_loss_rate=stop_loss_rate,
        stress=stress,
        start_index=lookback,
        should_enter=should_enter,
        should_exit=should_exit,
    )


def _simulate_long_only(
    candles: Sequence[Candle],
    *,
    starting_capital: float,
    fee_rate: float,
    slippage_rate: float,
    tax_rate: float,
    tds_rate: float,
    stop_loss_rate: float,
    stress: bool,
    start_index: int,
    should_enter,
    should_exit,
) -> BacktestResult:
    if starting_capital <= 0 or fee_rate < 0 or slippage_rate < 0:
        raise ValueError("capital and cost rates must be positive/non-negative")
    multiplier = 2.0 if stress else 1.0
    fee = fee_rate * multiplier
    slippage = slippage_rate * multiplier
    cash = starting_capital
    trades = []
    position = None
    gross_total = 0.0
    fee_total = 0.0
    slip_total = 0.0
    tax_total = 0.0
    tds_total = 0.0
    index = start_index
    while index < len(candles):
        candle = candles[index]
        if position is not None:
            stop_price = position["entry_price"] * (1.0 - stop_loss_rate)
            if candle.low <= stop_price:
                trade = _close_position(
                    position, index, stop_price, "STOP_LOSS", fee, slippage, tax_rate, tds_rate
                )
                cash += position["notional"] + trade.net_pnl
                trades.append(trade)
                gross_total += trade.gross_pnl
                fee_total += trade.fees
                slip_total += trade.slippage
                tax_total += trade.tax
                tds_total += trade.tds
                position = None
                index += 1
                continue
            if position["entry_index"] != index and should_exit(index):
                trade = _close_position(
                    position, index, candle.close, "SIGNAL", fee, slippage, tax_rate, tds_rate
                )
                cash += position["notional"] + trade.net_pnl
                trades.append(trade)
                gross_total += trade.gross_pnl
                fee_total += trade.fees
                slip_total += trade.slippage
                tax_total += trade.tax
                tds_total += trade.tds
                position = None
                index += 1
                continue
        if position is None and index + 1 < len(candles) and should_enter(index):
            entry_price = candles[index + 1].open * (1.0 + slippage)
            notional = cash * 0.25
            quantity = notional / entry_price
            entry_fee = notional * fee
            cash -= notional + entry_fee
            position = {
                "entry_index": index + 1,
                "entry_price": entry_price,
                "quantity": quantity,
                "notional": notional,
                "entry_fee": entry_fee,
            }
        index += 1

    if position is not None:
        trade = _close_position(
            position, len(candles) - 1, candles[-1].close, "END_OF_DATA", fee, slippage, tax_rate, tds_rate
        )
        cash += position["notional"] + trade.net_pnl
        trades.append(trade)
        gross_total += trade.gross_pnl
        fee_total += trade.fees
        slip_total += trade.slippage
        tax_total += trade.tax
        tds_total += trade.tds

    ending = cash
    return BacktestResult(
        trades=tuple(trades),
        starting_capital=starting_capital,
        ending_capital=ending,
        gross_return=gross_total / starting_capital,
        net_return=(ending - starting_capital) / starting_capital,
        fees=fee_total,
        slippage=slip_total,
        tax=tax_total,
        tds=tds_total,
    )


def evaluate_acceptance(
    *,
    window_returns: Sequence[float],
    aggregate_return: float,
    bootstrap_ci: tuple[float, float],
    risk_free_return: float,
    stress_return: float,
    trade_count: int,
) -> AcceptanceResult:
    """Apply the preregistered five research criteria without tuning inputs."""
    failed = []
    if len(window_returns) != 4 or sum(value > 0 for value in window_returns) < 3:
        failed.append("three_of_four_windows")
    if aggregate_return <= 0:
        failed.append("aggregate_positive")
    if bootstrap_ci[0] <= 0:
        failed.append("bootstrap_excludes_zero")
    if aggregate_return - risk_free_return <= bootstrap_ci[1] - bootstrap_ci[0]:
        failed.append("beats_risk_free_by_ci_width")
    if stress_return <= 0:
        failed.append("stress_costs")
    if trade_count < 20:
        failed.append("minimum_sample_size")
    return AcceptanceResult(passed=not failed, failed_criteria=tuple(failed))


def _close_position(position, exit_index, raw_exit, reason, fee, slippage, tax_rate, tds_rate):
    exit_price = raw_exit * (1.0 - slippage)
    quantity = position["quantity"]
    gross = (exit_price - position["entry_price"]) * quantity
    exit_notional = exit_price * quantity
    exit_fee = exit_notional * fee
    total_fees = position["entry_fee"] + exit_fee
    tds = exit_notional * tds_rate
    tax_base = max(0.0, gross - total_fees - tds)
    tax = tax_base * tax_rate
    net = gross - total_fees - tds - tax
    return Trade(
        entry_index=position["entry_index"], exit_index=exit_index,
        entry_price=position["entry_price"], exit_price=exit_price,
        quantity=quantity, gross_pnl=gross, fees=total_fees,
        slippage=(position["entry_price"] - position["entry_price"] / (1.0 + slippage)) * quantity
        + (raw_exit - exit_price) * quantity,
        tax=tax, tds=tds, net_pnl=net, exit_reason=reason,
    )


def _mean(values: Sequence[float]) -> float:
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


def _stdev(values: Sequence[float]) -> float:
    mean = _mean(values)
    total = 0.0
    for value in values:
        total += (value - mean) ** 2
    return (total / len(values)) ** 0.5


def _vwap(candles: Sequence[Candle], end: int, lookback: int) -> float:
    start = max(0, end - lookback + 1)
    numerator = 0.0
    denominator = 0.0
    index = start
    while index <= end:
        candle = candles[index]
        typical = (candle.high + candle.low + candle.close) / 3.0
        numerator += typical * candle.volume
        denominator += candle.volume
        index += 1
    if denominator == 0:
        return candles[end].close
    return numerator / denominator


def _ema(candles: Sequence[Candle], end: int, period: int) -> float:
    values = []
    start = max(0, end - period * 3)
    index = start
    while index <= end:
        values.append(candles[index].close)
        index += 1
    if len(values) < period:
        raise ValueError("not enough candles for indicator")
    value = sum(values[:period]) / period
    alpha = 2.0 / (period + 1.0)
    for item in values[period:]:
        value = alpha * item + (1.0 - alpha) * value
    return value


def _validate_candles(candles: Sequence[Candle]) -> None:
    if len(candles) < 3:
        raise ValueError("at least three candles are required")
    prior = None
    for candle in candles:
        if candle.high < candle.low or candle.open <= 0 or candle.close <= 0:
            raise ValueError("invalid candle price range")
        if prior is not None and candle.timestamp <= prior:
            raise ValueError("candle timestamps must be strictly increasing")
        prior = candle.timestamp
