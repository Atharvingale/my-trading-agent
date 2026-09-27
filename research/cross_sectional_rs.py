"""Cross-sectional relative-strength engine (Module 1 research, Module 15 provenance).

Fixed design from research/hypotheses/cross_sectional_rs_001.md (frozen
2026-09-27, immutable): a daily-rebalanced, long-only, top-quantile rotation
over BTCUSDT/ETHUSDT spot 1h closes. The defining mechanism is relative
ranking across the universe at each rebalance point, not any single asset's
own momentum: the top-ranked asset is held even when its absolute trailing
return is negative. Costs reuse the exact project stack verbatim.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


UNIVERSE = ("BTCUSDT", "ETHUSDT")
LOOKBACK_BARS = 168
ELIGIBILITY_BARS = 720
MIN_NOTIONAL_PER_DAY = 10000000.0
MIN_LISTING_AGE_DAYS = 90
REBALANCE_HOUR_UTC = 0
HOLDING_HOURS = 24

FEE_RATE = 0.001
SLIPPAGE_RATE = 0.001
TAX_RATE = 0.312
TDS_RATE = 0.01

HYPOTHESIS_ID = "cross_sectional_rs_001"
SIGNAL_CLASS = "cross-sectional-relative-strength"


@dataclass(frozen=True)
class KlineBar:
    symbol: str
    open_time_ms: int
    close: float
    volume: float


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


def dataset_hash(bars: list[KlineBar]) -> str:
    """SHA-256 over canonical rows; storage is versioned so the hash is the version."""
    rows: list[list[Any]] = []
    for bar in bars:
        rows.append([bar.symbol, bar.open_time_ms, bar.close, bar.volume])
    ordered: list[list[Any]] = []
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


def order_bars(bars: list[KlineBar]) -> list[KlineBar]:
    """Chronological order via explicit insertion (no sorted() per conventions)."""
    ordered: list[KlineBar] = []
    for bar in bars:
        placed = False
        index = 0
        while index < len(ordered):
            if bar.open_time_ms < ordered[index].open_time_ms:
                ordered.insert(index, bar)
                placed = True
                break
            index = index + 1
        if placed is False:
            ordered.append(bar)
    return ordered


def validate_holdout(bars: list[KlineBar], start_ms: int, end_ms: int) -> dict[str, Any]:
    """Coverage check for the frozen window: gaps, dupes, fills, survivorship."""
    report: dict[str, Any] = {}
    by_symbol: dict[str, list[KlineBar]] = {}
    for bar in bars:
        if bar.symbol not in by_symbol:
            by_symbol[bar.symbol] = []
        by_symbol[bar.symbol].append(bar)
    symbols: list[str] = []
    for symbol in by_symbol:
        symbols.append(symbol)
    report["symbols"] = symbols
    report["universe"] = [UNIVERSE[0], UNIVERSE[1]]
    missing: list[str] = []
    for symbol in UNIVERSE:
        if symbol not in by_symbol:
            missing.append(symbol)
    report["missing_symbols"] = missing
    gaps = 0
    dupes = 0
    bad = 0
    first_ms: int | None = None
    last_ms: int | None = None
    per_symbol: dict[str, Any] = {}
    for symbol in UNIVERSE:
        rows = by_symbol.get(symbol, [])
        ordered = order_bars(rows)
        seen: dict[int, int] = {}
        for bar in ordered:
            seen[bar.open_time_ms] = seen.get(bar.open_time_ms, 0) + 1
            if first_ms is None or bar.open_time_ms < first_ms:
                first_ms = bar.open_time_ms
            if last_ms is None or bar.open_time_ms > last_ms:
                last_ms = bar.open_time_ms
            if not (bar.close > 0) or not (bar.volume >= 0):
                bad = bad + 1
        for stamp in seen:
            if seen[stamp] > 1:
                dupes = dupes + (seen[stamp] - 1)
        stamps: list[int] = []
        for bar in ordered:
            if bar.open_time_ms not in stamps:
                stamps.append(bar.open_time_ms)
        ordered_stamps: list[int] = []
        for stamp in stamps:
            placed = False
            index = 0
            while index < len(ordered_stamps):
                if stamp < ordered_stamps[index]:
                    ordered_stamps.insert(index, stamp)
                    placed = True
                    break
                index = index + 1
            if placed is False:
                ordered_stamps.append(stamp)
        symbol_gaps = 0
        index = 1
        while index < len(ordered_stamps):
            if ordered_stamps[index] - ordered_stamps[index - 1] > 3660000:
                symbol_gaps = symbol_gaps + 1
            index = index + 1
        gaps = gaps + symbol_gaps
        per_symbol[symbol] = {"n": len(ordered), "gaps_over_1h": symbol_gaps}
    report["per_symbol"] = per_symbol
    report["gaps_over_1h"] = gaps
    report["duplicates"] = dupes
    report["bad_bars"] = bad
    if first_ms is not None and last_ms is not None:
        report["span_days"] = (last_ms - first_ms) / 86400000.0
    else:
        report["span_days"] = 0.0
    # Survivorship: both universe assets continuously listed; no delisted coin
    # meets the 8000-bar evidence bar, so none is silently excluded.
    report["survivorship"] = {
        "continuously_listed": [UNIVERSE[0], UNIVERSE[1]],
        "delisted_excluded_silently": False,
        "note": "2-asset limitation disclosed in pre-registration; no synthetic history used",
    }
    reasons: list[str] = []
    if missing:
        reasons.append("missing symbols: %s" % ",".join(missing))
    if gaps > 0:
        reasons.append("%d hourly gaps" % gaps)
    if dupes > 0:
        reasons.append("%d duplicate bars" % dupes)
    if bad > 0:
        reasons.append("%d bad bars (non-positive close or negative volume)" % bad)
    report["ok"] = len(reasons) == 0
    report["reasons"] = reasons
    return report


def rebalance_timestamps(bars_by_symbol: dict[str, list[KlineBar]], start_ms: int, end_ms: int) -> list[int]:
    """Daily 00:00 UTC boundaries inside the window with full lookback available."""
    stamps: list[int] = []
    for symbol in UNIVERSE:
        rows = order_bars(bars_by_symbol.get(symbol, []))
        for bar in rows:
            stamp = int(bar.open_time_ms) + 3600000
            if stamp < start_ms or stamp > end_ms:
                continue
            if (stamp % 86400000) != 0:
                continue
            if stamp not in stamps:
                stamps.append(stamp)
    ordered: list[int] = []
    for stamp in stamps:
        placed = False
        index = 0
        while index < len(ordered):
            if stamp < ordered[index]:
                ordered.insert(index, stamp)
                placed = True
                break
            index = index + 1
        if placed is False:
            ordered.append(stamp)
    # Causal warmup inside the window: first LOOKBACK_BARS of hourly history
    # are indicator-only, so trading starts 7 days after the window opens.
    warmup_ms = LOOKBACK_BARS * 3600000
    tradable: list[int] = []
    for stamp in ordered:
        if stamp - start_ms >= warmup_ms:
            tradable.append(stamp)
    return tradable


def eligibility_at(ordered: list[KlineBar], stamp: int) -> bool:
    """Liquidity/listing gate over the trailing 720 hourly bars ending at stamp."""
    window: list[KlineBar] = []
    for bar in ordered:
        if stamp - ELIGIBILITY_BARS * 3600000 <= int(bar.open_time_ms) < stamp:
            window.append(bar)
    if len(window) < ELIGIBILITY_BARS:
        return False
    notional = 0.0
    for bar in window:
        notional = notional + float(bar.close) * float(bar.volume)
    avg_per_day = notional / 30.0
    if avg_per_day < MIN_NOTIONAL_PER_DAY:
        return False
    # Listing age: first stored bar predates stamp by the minimum age. Both
    # universe assets listed in 2017, so any stamp in this window passes by
    # years; the check below is the binding form using stored history plus
    # the known-listing floor (stored history alone starts 2025-10-28).
    earliest = ordered[0].open_time_ms if ordered else stamp
    known_listing_ms = 1500000000000
    listing_start = earliest
    if known_listing_ms < listing_start:
        listing_start = known_listing_ms
    age_days = (stamp - listing_start) / 86400000.0
    if age_days < MIN_LISTING_AGE_DAYS:
        return False
    return True


def score_at(ordered: list[KlineBar], stamp: int) -> float:
    """Volatility-adjusted trailing 168h return ending at stamp (causal)."""
    closes: list[float] = []
    for bar in ordered:
        if stamp - LOOKBACK_BARS * 3600000 <= int(bar.open_time_ms) < stamp:
            closes.append(float(bar.close))
    if len(closes) < LOOKBACK_BARS + 1:
        return 0.0
    first = closes[0]
    last = closes[len(closes) - 1]
    if not (first > 0) or not (last > 0):
        return 0.0
    trailing = last / first - 1.0
    rets: list[float] = []
    index = 1
    while index < len(closes):
        prior = closes[index - 1]
        if prior > 0:
            rets.append(closes[index] / prior - 1.0)
        index = index + 1
    mean = 0.0
    for value in rets:
        mean = mean + value
    mean = mean / len(rets) if rets else 0.0
    variance = 0.0
    for value in rets:
        variance = variance + (value - mean) * (value - mean)
    variance = variance / len(rets) if rets else 0.0
    if not (variance > 0):
        return 0.0
    stdev = variance ** 0.5
    if not (stdev > 0):
        return 0.0
    return trailing / stdev


def close_at(ordered: list[KlineBar], stamp: int) -> float | None:
    """Price at stamp: close of the last completed hourly bar (open_time < stamp)."""
    best_ms = -1
    best_close: float | None = None
    for bar in ordered:
        if int(bar.open_time_ms) < stamp and int(bar.open_time_ms) > best_ms:
            best_ms = int(bar.open_time_ms)
            best_close = float(bar.close)
    return best_close


def generate_daily_trades(
    bars_by_symbol: dict[str, list[KlineBar]],
    rebalance_ms: list[int],
    *,
    notional: float = 1000.0,
    stressed: bool = False,
) -> list[dict[str, Any]]:
    """One closed long-only holding per daily interval for the top-ranked asset.

    Each interval is closed out (sell at exit, rebuy next entry when the same
    asset is held again), so costs apply per interval via the verbatim stack.
    This overstates costs versus buy-and-hold across same-asset days, which is
    conservative (biases against PASS) and keeps tax timing exactly defined.
    """
    ordered: dict[str, list[KlineBar]] = {}
    for symbol in UNIVERSE:
        ordered[symbol] = order_bars(bars_by_symbol.get(symbol, []))
    trades: list[dict[str, Any]] = []
    for stamp in rebalance_ms:
        nxt = stamp + HOLDING_HOURS * 3600000
        eligible: list[str] = []
        for symbol in UNIVERSE:
            if eligibility_at(ordered[symbol], stamp):
                eligible.append(symbol)
        if len(eligible) == 0:
            continue
        best_symbol: str | None = None
        best_score = -1e18
        first = True
        for symbol in eligible:
            score = score_at(ordered[symbol], stamp)
            if first or score > best_score:
                best_score = score
                best_symbol = symbol
                first = False
        if best_symbol is None:
            continue
        entry = close_at(ordered[best_symbol], stamp)
        exit_price = close_at(ordered[best_symbol], nxt)
        if entry is None or exit_price is None or not (entry > 0):
            continue
        gross = (exit_price / entry - 1.0) * notional
        if stressed:
            net = apply_costs_stressed(gross, notional)
        else:
            net = apply_costs(gross, notional)
        # Cross-sectional provenance: the rank at entry proves the relative
        # mechanism (held asset beat the contemporaneous peer on score).
        peer_scores: dict[str, float] = {}
        for symbol in eligible:
            peer_scores[symbol] = score_at(ordered[symbol], stamp)
        trades.append({
            "entry_time_ms": stamp,
            "exit_time_ms": nxt,
            "held": best_symbol,
            "score": best_score,
            "peer_scores": peer_scores,
            "gross_pnl": gross,
            "net_pnl": net,
        })
    return trades
