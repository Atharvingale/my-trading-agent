"""Funding-rate carry experiments (Module 1 research, Module 15 provenance).

Causal model: the funding rate settling at T is observed at T; a position
opened at T earns the rate settling at T+1 plus the mark move over [T, T+1].
Signals use trailing settled rates only — the earned rate is the bet, never
an input. Costs use the exact project assumptions (0.10%/side fee and
slippage, 31.2% VDA tax on gains without loss offset, 1% TDS cash-flow drag).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


FEE_RATE = 0.001
SLIPPAGE_RATE = 0.001
TAX_RATE = 0.312
TDS_RATE = 0.01
MIN_PERIODS = 20
MIN_REGIMES = 2
MIN_SPAN_DAYS = 60.0
MAX_ABS_RATE = 0.01


@dataclass(frozen=True)
class FundingObservation:
    symbol: str
    funding_time_ms: int
    rate: float
    mark_price: float


@dataclass(frozen=True)
class FundingHypothesis:
    hypothesis_id: str
    signal_class: str
    direction: str
    threshold: float
    persistence: int
    holding_periods: int
    volatility_filter: bool


FUNDING_HYPOTHESES: tuple[FundingHypothesis, ...] = (
    FundingHypothesis("F1", "funding-rate carry", "SHORT", 0.0001, 3, 1, False),
    FundingHypothesis("F2", "funding-rate carry", "SHORT", 0.0005, 3, 1, False),
    FundingHypothesis("F3", "funding-rate carry", "LONG", -0.0001, 3, 1, False),
)


@dataclass(frozen=True)
class AnomalyHypothesis:
    """F4: funding anomaly fade — a distinct class from F1–F3 level crossing.

    Where F1–F3 trigger on fixed rate thresholds, F4 normalizes the current
    rate against its own trailing distribution and fades extremes: crowded
    positioning (abnormal funding) tends to normalize, so the trade collects
    carry while positioned for the snap-back. Adaptive, two-sided, one rule.
    """

    hypothesis_id: str
    signal_class: str
    lookback: int
    z_threshold: float
    holding_periods: int


F4 = AnomalyHypothesis("F4", "funding-rate carry", 30, 2.0, 1)


def freeze_hypothesis(hypothesis: AnomalyHypothesis) -> dict[str, str]:
    """Canonical pre-registration record; hash proves params predated evaluation."""
    import hashlib as _hashlib

    canonical = json.dumps({
        "hypothesis_id": hypothesis.hypothesis_id,
        "signal_class": hypothesis.signal_class,
        "lookback": hypothesis.lookback,
        "z_threshold": hypothesis.z_threshold,
        "holding_periods": hypothesis.holding_periods,
    }, separators=(",", ":"), sort_keys=True)
    return {
        "canonical": canonical,
        "sha256": _hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _ordered_rows(rows: list[list[Any]]) -> list[list[Any]]:
    # Explicit insertion order (no sorted() per project conventions) so the
    # dataset hash is canonical and reproducible across runs.
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
    return ordered


def dataset_hash(observations: list[FundingObservation]) -> str:
    """SHA-256 over canonical rows; data/ is untracked so the hash is the version."""
    rows: list[list[Any]] = []
    for obs in observations:
        rows.append([obs.symbol, obs.funding_time_ms, obs.rate, obs.mark_price])
    ordered = _ordered_rows(rows)
    return hashlib.sha256(json.dumps(ordered, separators=(",", ":")).encode("utf-8")).hexdigest()


def quality_gate(observations: list[FundingObservation]) -> dict[str, Any]:
    """Validate ordering, duplicates, gaps, marks, and realistic rates."""
    report: dict[str, Any] = {}
    report["n"] = len(observations)
    if len(observations) == 0:
        report["ok"] = False
        report["reasons"] = ["empty dataset"]
        return report
    by_symbol: dict[str, list[FundingObservation]] = {}
    for obs in observations:
        if obs.symbol not in by_symbol:
            by_symbol[obs.symbol] = []
        by_symbol[obs.symbol].append(obs)
    symbols: list[str] = []
    for symbol in by_symbol:
        symbols.append(symbol)
    report["symbols"] = symbols
    ordered_ok = True
    seen: dict[str, dict[int, int]] = {}
    gaps = 0
    unrealistic = 0
    missing_marks = 0
    first_ms: int | None = None
    last_ms: int | None = None
    for symbol in by_symbol:
        rows = by_symbol[symbol]
        seen[symbol] = {}
        prior: int | None = None
        for obs in rows:
            if first_ms is None or obs.funding_time_ms < first_ms:
                first_ms = obs.funding_time_ms
            if last_ms is None or obs.funding_time_ms > last_ms:
                last_ms = obs.funding_time_ms
            if prior is not None and obs.funding_time_ms <= prior:
                ordered_ok = False
            prior = obs.funding_time_ms
            count = seen[symbol].get(obs.funding_time_ms, 0)
            seen[symbol][obs.funding_time_ms] = count + 1
            if abs(obs.rate) > MAX_ABS_RATE:
                unrealistic = unrealistic + 1
            if obs.mark_price <= 0:
                missing_marks = missing_marks + 1
        stamps: list[int] = []
        for stamp in seen[symbol]:
            stamps.append(stamp)
        ordered_stamps: list[int] = []
        for stamp in stamps:
            placed = False
            position = 0
            while position < len(ordered_stamps):
                if stamp < ordered_stamps[position]:
                    ordered_stamps.insert(position, stamp)
                    placed = True
                    break
                position = position + 1
            if placed is False:
                ordered_stamps.append(stamp)
        index = 1
        while index < len(ordered_stamps):
            gap_hours = (ordered_stamps[index] - ordered_stamps[index - 1]) / 3600000.0
            if gap_hours > 9.0:
                gaps = gaps + 1
            index = index + 1
    duplicates = 0
    for symbol in seen:
        for stamp in seen[symbol]:
            if seen[symbol][stamp] > 1:
                duplicates = duplicates + (seen[symbol][stamp] - 1)
    span_days = 0.0
    if first_ms is not None and last_ms is not None:
        span_days = (last_ms - first_ms) / 86400000.0
    report["ordered"] = ordered_ok
    report["duplicates"] = duplicates
    report["gaps_over_9h"] = gaps
    report["unrealistic_rates"] = unrealistic
    report["missing_marks"] = missing_marks
    report["span_days"] = span_days
    reasons: list[str] = []
    if ordered_ok is False:
        reasons.append("timestamps out of order")
    if duplicates > 0:
        reasons.append("%d duplicate records" % duplicates)
    if unrealistic > 0:
        reasons.append("%d unrealistic rates beyond 1%%/8h" % unrealistic)
    if missing_marks > 0:
        reasons.append("%d missing mark prices" % missing_marks)
    report["ok"] = len(reasons) == 0
    report["reasons"] = reasons
    return report


def apply_costs(gross_pnl: float, notional: float) -> float:
    """Project cost stack on one closed holding: fees, slippage, TDS, tax."""
    fees = notional * FEE_RATE * 2.0
    slippage = notional * SLIPPAGE_RATE * 2.0
    tds = notional * TDS_RATE
    remainder = gross_pnl - fees - slippage - tds
    tax = max(0.0, remainder) * TAX_RATE
    return gross_pnl - fees - slippage - tds - tax


def generate_trades(
    observations: list[FundingObservation],
    hypothesis: FundingHypothesis,
    *,
    notional: float = 1000.0,
) -> list[dict[str, Any]]:
    """Causal carry simulation: trailing rates at T decide, T→T+1 pays.

    Direction SHORT collects positive funding (pays when negative); LONG is
    the mirror. Every input at holding i is known at or before entry T.
    """
    by_symbol: dict[str, list[FundingObservation]] = {}
    for obs in observations:
        if obs.symbol not in by_symbol:
            by_symbol[obs.symbol] = []
        by_symbol[obs.symbol].append(obs)
    trades: list[dict[str, Any]] = []
    for symbol in by_symbol:
        rows = by_symbol[symbol]
        ordered: list[FundingObservation] = []
        for obs in rows:
            placed = False
            index = 0
            while index < len(ordered):
                if obs.funding_time_ms < ordered[index].funding_time_ms:
                    ordered.insert(index, obs)
                    placed = True
                    break
                index = index + 1
            if placed is False:
                ordered.append(obs)
        vols: list[float] = []
        index = 1
        while index < len(ordered):
            prior = ordered[index - 1].mark_price
            if prior > 0:
                vols.append(abs(ordered[index].mark_price - prior) / prior)
            else:
                vols.append(0.0)
            index = index + 1
        vol_median = _median(vols)
        index = hypothesis.persistence
        while index + hypothesis.holding_periods < len(ordered):
            window: list[float] = []
            k = index - hypothesis.persistence
            while k < index:
                window.append(ordered[k].rate)
                k = k + 1
            mean_rate = _mean(window)
            enter = False
            if hypothesis.direction == "SHORT" and mean_rate > hypothesis.threshold:
                enter = True
            if hypothesis.direction == "LONG" and mean_rate < hypothesis.threshold:
                enter = True
            if enter and hypothesis.volatility_filter and vols[index - 1] > vol_median:
                enter = False
            if enter:
                entry = ordered[index]
                exit_obs = ordered[index + hypothesis.holding_periods]
                # Correction 2026-09-26 (documented, pre-registration unchanged):
                # an earlier revision had this sign inverted (SHORT earned
                # -rate). Perps settle funding from longs to shorts when the
                # rate is positive, so SHORT collects +rate and LONG collects
                # -rate. The recorded F1-F3 NULLs are unaffected (0 trades).
                earned = exit_obs.rate * notional
                if hypothesis.direction == "LONG":
                    earned = -exit_obs.rate * notional
                price_move = (exit_obs.mark_price - entry.mark_price) / entry.mark_price
                if hypothesis.direction == "SHORT":
                    price_move = -price_move
                gross = earned + price_move * notional
                net = apply_costs(gross, notional)
                trades.append({
                    "symbol": symbol,
                    "entry_time_ms": entry.funding_time_ms,
                    "exit_time_ms": exit_obs.funding_time_ms,
                    "direction": hypothesis.direction,
                    "gross_pnl": gross,
                    "net_pnl": net,
                })
            index = index + 1
    return trades


def generate_anomaly_trades(
    observations: list[FundingObservation],
    hypothesis: AnomalyHypothesis,
    *,
    notional: float = 1000.0,
) -> list[dict[str, Any]]:
    """Causal anomaly fade: z-scores from trailing settled rates only.

    At settlement T the z-score uses rates[T-lookback:T] — all settled and
    known. |z| beyond threshold fades the anomaly (SHORT abnormally positive
    funding, LONG abnormally negative); the earned rate at T+1 is the bet.
    Zero-variance windows produce no signal rather than a division artifact.
    """
    if hypothesis.lookback < 5:
        raise ValueError("lookback must be at least 5")
    if hypothesis.z_threshold <= 0:
        raise ValueError("z_threshold must be positive")
    by_symbol: dict[str, list[FundingObservation]] = {}
    for obs in observations:
        if obs.symbol not in by_symbol:
            by_symbol[obs.symbol] = []
        by_symbol[obs.symbol].append(obs)
    trades: list[dict[str, Any]] = []
    for symbol in by_symbol:
        rows = by_symbol[symbol]
        ordered: list[FundingObservation] = []
        for obs in rows:
            placed = False
            index = 0
            while index < len(ordered):
                if obs.funding_time_ms < ordered[index].funding_time_ms:
                    ordered.insert(index, obs)
                    placed = True
                    break
                index = index + 1
            if placed is False:
                ordered.append(obs)
        index = hypothesis.lookback
        while index + hypothesis.holding_periods < len(ordered):
            window: list[float] = []
            k = index - hypothesis.lookback
            while k < index:
                window.append(ordered[k].rate)
                k = k + 1
            mean = _mean(window)
            variance = 0.0
            for rate in window:
                variance = variance + (rate - mean) ** 2
            variance = variance / len(window)
            if variance <= 0:
                index = index + 1
                continue
            deviation = variance ** 0.5
            z = (ordered[index].rate - mean) / deviation
            direction = None
            if z > hypothesis.z_threshold:
                direction = "SHORT"
            elif z < -hypothesis.z_threshold:
                direction = "LONG"
            if direction is not None:
                entry = ordered[index]
                exit_obs = ordered[index + hypothesis.holding_periods]
                earned = exit_obs.rate * notional
                if direction == "LONG":
                    earned = -exit_obs.rate * notional
                price_move = (exit_obs.mark_price - entry.mark_price) / entry.mark_price
                if direction == "SHORT":
                    price_move = -price_move
                gross = earned + price_move * notional
                net = apply_costs(gross, notional)
                trades.append({
                    "symbol": symbol,
                    "entry_time_ms": entry.funding_time_ms,
                    "exit_time_ms": exit_obs.funding_time_ms,
                    "direction": direction,
                    "z_score": z,
                    "gross_pnl": gross,
                    "net_pnl": net,
                })
            index = index + 1
    return trades


def evaluate_sufficiency(
    observations: list[FundingObservation],
    regime_legs: list[str],
    total_tested_elsewhere: int = 0,
) -> dict[str, Any]:
    """Gate-grade sufficiency check: sample, span, and regime legs.

    Returns INCONCLUSIVE whenever the data cannot support a verdict, without
    consuming any holdout. No statistics are promoted past this point.
    """
    quality = quality_gate(observations)
    legs: list[str] = []
    for leg in regime_legs:
        if leg not in legs:
            legs.append(leg)
    verdict = "READY"
    reasons: list[str] = []
    if len(observations) < MIN_PERIODS:
        verdict = "INCONCLUSIVE"
        reasons.append("only %d periods, need %d" % (len(observations), MIN_PERIODS))
    if quality.get("span_days", 0.0) < MIN_SPAN_DAYS:
        verdict = "INCONCLUSIVE"
        reasons.append("span %.1f days below %.0f-day gate minimum" % (
            quality.get("span_days", 0.0), MIN_SPAN_DAYS))
    if len(legs) < MIN_REGIMES:
        verdict = "INCONCLUSIVE"
        reasons.append("only %d regime leg(s), need %d" % (len(legs), MIN_REGIMES))
    if quality.get("ok", False) is False:
        verdict = "INCONCLUSIVE"
        for reason in quality.get("reasons", []):
            reasons.append("data quality: %s" % reason)
    return {
        "verdict": verdict,
        "reasons": reasons,
        "n": len(observations),
        "span_days": quality.get("span_days", 0.0),
        "regime_legs": legs,
        "dataset_hash": dataset_hash(observations),
        "hypotheses_registered": len(FUNDING_HYPOTHESES),
        "hypotheses_tested": 0,
        "note": "registered hypotheses consume no multiple-testing budget until tested",
        "ledger_tested_elsewhere": int(total_tested_elsewhere),
    }


def describe_stats(observations: list[FundingObservation]) -> dict[str, Any]:
    """Descriptive only: distribution shape to size the missing-data spec."""
    rates: list[float] = []
    for obs in observations:
        rates.append(obs.rate)
    positive = 0
    for rate in rates:
        if rate > 0:
            positive = positive + 1
    return {
        "n": len(rates),
        "mean_rate": _mean(rates) if rates else 0.0,
        "fraction_positive": (positive / len(rates)) if rates else 0.0,
    }


def _mean(values: list[float]) -> float:
    total = 0.0
    for value in values:
        total = total + value
    return total / len(values) if values else 0.0


def _median(values: list[float]) -> float:
    ordered: list[float] = []
    for value in values:
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
    if len(ordered) == 0:
        return 0.0
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def load_from_market_db(path: str, symbols: list[str] | None = None) -> list[FundingObservation]:
    """Read funding history rows from a Module 2 database file (read-only)."""
    import sqlite3

    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT payload_json FROM market_events WHERE event_type='futuresFundingRate'"
        ).fetchall()
    finally:
        connection.close()
    wanted: dict[str, bool] = {}
    if symbols is not None:
        for symbol in symbols:
            wanted[str(symbol).strip().upper()] = True
    observations: list[FundingObservation] = []
    for row in rows:
        try:
            items = json.loads(row[0]).get("items", [])
        except Exception:
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", "")).strip().upper()
            if wanted and symbol not in wanted:
                continue
            try:
                rate = float(item.get("fundingRate", 0.0))
                mark = float(item.get("markPrice", 0.0))
                stamp = int(item.get("fundingTime", 0))
            except (TypeError, ValueError):
                continue
            if stamp <= 0:
                continue
            observations.append(FundingObservation(
                symbol=symbol, funding_time_ms=stamp, rate=rate, mark_price=mark,
            ))
    deduped: dict[str, FundingObservation] = {}
    for obs in observations:
        key = "%s|%d" % (obs.symbol, obs.funding_time_ms)
        deduped[key] = obs
    result: list[FundingObservation] = []
    for key in deduped:
        result.append(deduped[key])
    return result
