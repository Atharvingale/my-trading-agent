"""Date-cluster bootstrap for oi_positioning_001 (Amendment 1 construction).

Why this file exists: same-day altcoin trades are correlated, so resampling
individual trades understates uncertainty. One observation per ENTRY DATE
(mean net return of trades entered that date) is resampled instead. Setting
Module 1 trade_returns to these date means makes the gate's own bootstrap
the cluster bootstrap with no gate edit.
"""

from __future__ import annotations

import math
import random
from typing import Any


def cluster_by_entry_date(trades: list) -> dict:
    """Group net fractions by entry day; values are per-trade fractions."""
    by_date: dict = {}
    for trade in trades:
        day = str(trade.get("entry_day", ""))
        frac = float(trade.get("net_pnl", 0.0)) / 1000.0
        if day not in by_date:
            by_date[day] = []
        by_date[day].append(frac)
    return by_date


def date_means(by_date: dict) -> list:
    """One observation per entry date = mean net fraction that date."""
    means: list = []
    for day in by_date:
        vals = by_date[day]
        total = 0.0
        for value in vals:
            total = total + float(value)
        means.append(total / float(len(vals)))
    return means


def gross_date_means(trades: list) -> list:
    """Same clustering for gross (pre-cost) fractions, information only."""
    by_date: dict = {}
    for trade in trades:
        day = str(trade.get("entry_day", ""))
        frac = float(trade.get("gross_pnl", 0.0)) / 1000.0
        if day not in by_date:
            by_date[day] = []
        by_date[day].append(frac)
    means: list = []
    for day in by_date:
        vals = by_date[day]
        total = 0.0
        for value in vals:
            total = total + float(value)
        means.append(total / float(len(vals)))
    return means


def bootstrap_ci(
    observations: list,
    *,
    seed: int = 20260928,
    samples: int = 10000,
) -> tuple:
    """Percentile bootstrap CI for the mean (resamples observations)."""
    if len(observations) == 0:
        raise ValueError("observations must be non-empty")
    rng = random.Random(seed)
    count = len(observations)
    means: list = []
    trial = 0
    while trial < samples:
        total = 0.0
        pick = 0
        while pick < count:
            total = total + observations[rng.randrange(count)]
            pick = pick + 1
        means.append(total / float(count))
        trial = trial + 1
    ordered: list = []
    for value in means:
        placed = False
        index = 0
        while index < len(ordered):
            if value < ordered[index]:
                ordered.insert(index, value)
                placed = True
                break
            index = index + 1
        if placed is False:
            ordered.append(value)
    lower = _percentile(ordered, 0.025)
    upper = _percentile(ordered, 0.975)
    return (lower, upper)


def mean_value(values: list) -> float:
    """Arithmetic mean with an explicit loop."""
    total = 0.0
    for value in values:
        total = total + float(value)
    if len(values) == 0:
        return 0.0
    return total / float(len(values))


def _percentile(values: list, fraction: float) -> float:
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return float(values[lower] + (values[upper] - values[lower]) * weight)
