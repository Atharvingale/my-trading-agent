"""OI positioning engine (Module 1 research, oi_positioning_001 + 20d variant).

Why this file exists: implements the frozen long-only bottom-decile
top-trader-positions contrarian over the pre-registered 60-symbol spot
universe. Signal uses futures metrics daily 23:55 UTC values; trades price
on spot daily OPENs. Costs reuse the exact project stack verbatim.
Holding period and lookback are parameters (defaults reproduce
oi_positioning_001 exactly: 5-day hold, 90-day lookback); the 20-day
variant passes hold_days=20 with lookback unchanged at 90.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


FEE_RATE = 0.001
SLIPPAGE_RATE = 0.001
TAX_RATE = 0.312
TDS_RATE = 0.01

SIGNAL_FIELD = "sum_toptrader_long_short_ratio"
LOOKBACK_DAYS = 90
PERCENTILE_THRESHOLD = 0.10
HOLD_DAYS = 5

HYPOTHESIS_ID = "oi_positioning_001"
SIGNAL_CLASS = "open-interest-positioning-dynamics"


@dataclass(frozen=True)
class MetricsDaily:
    symbol: str
    day: str
    value: float


@dataclass(frozen=True)
class SpotDaily:
    symbol: str
    day: str
    open_price: float


def apply_costs(gross_pnl: float, notional: float) -> float:
    """Project cost stack on one closed holding: fees, slippage, TDS, tax."""
    fees = notional * FEE_RATE * 2.0
    slippage = notional * SLIPPAGE_RATE * 2.0
    tds = notional * TDS_RATE
    remainder = gross_pnl - fees - slippage - tds
    tax = max(0.0, remainder) * TAX_RATE
    return gross_pnl - fees - slippage - tds - tax


def apply_costs_stressed(gross_pnl: float, notional: float) -> float:
    """Doubled-cost stress leg: fee and slippage x2, tax/TDS unchanged."""
    fees = notional * (FEE_RATE * 2.0) * 2.0
    slippage = notional * (SLIPPAGE_RATE * 2.0) * 2.0
    tds = notional * TDS_RATE
    remainder = gross_pnl - fees - slippage - tds
    tax = max(0.0, remainder) * TAX_RATE
    return gross_pnl - fees - slippage - tds - tax


def dataset_hash(days: list) -> str:
    """SHA-256 over canonical rows; the hash is the frozen version."""
    rows: list = []
    for item in days:
        rows.append(item)
    ordered: list = []
    for row in rows:
        placed = False
        index = 0
        while index < len(ordered):
            if (row[0], row[1]) < (ordered[index][0], ordered[index][1]):
                ordered.insert(index, row)
                placed = True
                break
            index = index + 1
        if placed is False:
            ordered.append(row)
    return hashlib.sha256(json.dumps(ordered, separators=(",", ":")).encode("utf-8")).hexdigest()


def signal_dates(values_by_day: dict, lookback: int = LOOKBACK_DAYS) -> list:
    """Bottom-decile dates: value rank <=10% among prior lookback days only.

    Why strict exclusion: D's own value never enters its percentile;
    lookback prior days required, else ineligible. No look-ahead.
    Default lookback reproduces oi_positioning_001 exactly.
    """
    days: list = []
    for day in values_by_day:
        days.append(day)
    ordered_days: list = []
    for day in days:
        placed = False
        index = 0
        while index < len(ordered_days):
            if day < ordered_days[index]:
                ordered_days.insert(index, day)
                placed = True
                break
            index = index + 1
        if placed is False:
            ordered_days.append(day)
    look = int(lookback)
    fired: list = []
    index = look
    while index < len(ordered_days):
        day = ordered_days[index]
        window: list = []
        k = index - look
        while k < index:
            window.append(values_by_day[ordered_days[k]])
            k = k + 1
        current = values_by_day[day]
        below_or_equal = 0
        for past in window:
            if past <= current:
                below_or_equal = below_or_equal + 1
        # Percentile = rank among priors; bottom decile fires.
        # rank = (# priors <= current) / look; current smallest -> 1/look.
        rank = float(below_or_equal) / float(look)
        # Count strictly smaller for tie handling: fire when at most 9
        # priors are strictly below (equivalent to <=0.10 with tie guard).
        strictly_below = 0
        for past in window:
            if past < current:
                strictly_below = strictly_below + 1
        if float(strictly_below + 1) / float(look + 1) <= PERCENTILE_THRESHOLD + 1e-12:
            fired.append(day)
        index = index + 1
    return fired


def add_days(day: str, delta: int) -> str:
    """Calendar day shift for YYYY-MM-DD (stdlib only)."""
    import datetime as _dt

    base = _dt.date.fromisoformat(day)
    shifted = base + _dt.timedelta(days=int(delta))
    return shifted.isoformat()


def generate_trades(
    metrics_by_symbol: dict,
    opens_by_symbol_day: dict,
    universe: list,
    first_signal_day: str,
    last_signal_day: str,
    *,
    notional: float = 1000.0,
    stressed: bool = False,
    hold_days: int = HOLD_DAYS,
    lookback: int = LOOKBACK_DAYS,
) -> list:
    """One spot long per signal; no re-entry while held.

    Entry at D+1 spot OPEN, exit at D+1+hold_days spot OPEN (hold_days
    after entry; 5-day default exits D+6, 20-day exits D+21).
    Missing opens invalidate that signal (never filled).
    Default hold/lookback reproduce oi_positioning_001 exactly.
    """
    trades: list = []
    hold = int(hold_days)
    for symbol in universe:
        values = metrics_by_symbol.get(symbol, {})
        fired = signal_dates(values, lookback=lookback)
        held_until = ""
        for day in fired:
            if day < first_signal_day or day > last_signal_day:
                continue
            if held_until != "" and day <= held_until:
                continue
            entry_day = add_days(day, 1)
            exit_day = add_days(day, 1 + hold)
            entry = opens_by_symbol_day.get(symbol, {}).get(entry_day, None)
            exit_price = opens_by_symbol_day.get(symbol, {}).get(exit_day, None)
            if entry is None or exit_price is None:
                continue
            if not (entry > 0):
                continue
            gross = (exit_price / entry - 1.0) * notional
            if stressed:
                net = apply_costs_stressed(gross, notional)
            else:
                net = apply_costs(gross, notional)
            trades.append({
                "symbol": symbol,
                "signal_day": day,
                "entry_day": entry_day,
                "exit_day": exit_day,
                "gross_pnl": gross,
                "net_pnl": net,
            })
            held_until = exit_day
    return trades
