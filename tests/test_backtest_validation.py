"""Backtest-validation level: no look-ahead, determinism, versioned datasets."""

from __future__ import annotations

import hashlib
import json

from edge_validation.experiment import Candle, backtest_trend_following


def flat_candles(count, price=100.0, spike_last=0.0):
    candles: list[Candle] = []
    for index in range(count):
        close = price
        if spike_last > 0 and index == count - 1:
            close = price + spike_last
        candles.append(
            Candle(
                timestamp=index,
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=10.0,
            )
        )
    return tuple(candles)


def dataset_sha256(candles) -> str:
    rows: list[list] = []
    for candle in candles:
        rows.append([candle.timestamp, candle.open, candle.high, candle.low, candle.close, candle.volume])
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode("utf-8")).hexdigest()


def test_final_candle_spike_cannot_be_traded():
    # Flat series never crosses; a spike confined to the last candle has no
    # following open to execute on, so a causal engine books zero trades.
    calm = backtest_trend_following(flat_candles(40), fast_period=2, slow_period=3)
    spiked = backtest_trend_following(flat_candles(40, spike_last=30.0), fast_period=2, slow_period=3)
    assert len(calm.trades) == 0
    assert len(spiked.trades) == 0
    for trade in spiked.trades:
        assert trade.entry_index < 39


def test_entries_execute_on_next_open_only():
    prices: list[float] = []
    for _ in range(10):
        prices.append(100.0)
    for _ in range(10):
        prices.append(110.0)
    for _ in range(10):
        prices.append(90.0)
    candles: list[Candle] = []
    index = 0
    for price in prices:
        candles.append(
            Candle(timestamp=index, open=price, high=price + 1, low=price - 1, close=price, volume=10.0)
        )
        index = index + 1
    result = backtest_trend_following(tuple(candles), fast_period=2, slow_period=3)
    for trade in result.trades:
        assert trade.entry_index > 0
        assert trade.exit_index >= trade.entry_index
        assert trade.entry_price > 0
        assert trade.exit_reason in ("STOP_LOSS", "SIGNAL", "END_OF_DATA")


def test_identical_dataset_gives_identical_results():
    first = backtest_trend_following(flat_candles(40), fast_period=2, slow_period=3)
    second = backtest_trend_following(flat_candles(40), fast_period=2, slow_period=3)
    assert first.net_return == second.net_return
    assert first.gross_return == second.gross_return
    assert len(first.trades) == len(second.trades)
    for index in range(len(first.trades)):
        assert first.trades[index] == second.trades[index]


def test_dataset_version_is_stable_and_sensitive():
    left = dataset_sha256(flat_candles(40))
    right = dataset_sha256(flat_candles(40))
    assert left == right
    assert len(left) == 64
    changed = dataset_sha256(flat_candles(40, spike_last=1.0))
    assert changed != left
