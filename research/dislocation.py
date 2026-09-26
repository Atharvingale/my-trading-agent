"""Cross-exchange dislocation experiments (Module 1 research, Module 15 provenance).

Signal sketch: when the cross-venue disagreement at T exceeds a threshold
for N consecutive confirmations, buy the cheap venue and sell the dear one
for a bounded convergence window. Executability demands synchronized
per-venue bid/ask quotes plus spread, depth, fee, and latency assumptions —
the current confirmation stream carries aggregates only, so the engine
refuses to simulate and reports exactly what is missing instead.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


MAX_PLAUSIBLE_DISAGREEMENT_BPS = 500.0
MIN_SPAN_DAYS = 60.0
MIN_OBSERVATIONS = 500


@dataclass(frozen=True)
class DislocationObservation:
    symbol: str
    timestamp_ms: int
    reference_price: float | None
    disagreement_bps: float | None
    source_count: int
    status: str
    venue_a: str | None = None
    bid_a: float | None = None
    ask_a: float | None = None
    depth_a: float | None = None
    venue_b: str | None = None
    bid_b: float | None = None
    ask_b: float | None = None
    depth_b: float | None = None


@dataclass(frozen=True)
class DislocationHypothesis:
    hypothesis_id: str
    signal_class: str
    threshold_bps: float
    persistence: int
    convergence_hours: float


DISLOCATION_HYPOTHESES: tuple[DislocationHypothesis, ...] = (
    DislocationHypothesis("D1", "cross-exchange dislocation", 5.0, 3, 1.0),
    DislocationHypothesis("D2", "cross-exchange dislocation", 10.0, 3, 1.0),
    DislocationHypothesis("D3", "cross-exchange dislocation", 20.0, 5, 2.0),
)


def dataset_hash(observations: list[DislocationObservation]) -> str:
    """SHA-256 over canonical rows; data/ is untracked so the hash is the version."""
    rows: list[list[Any]] = []
    for obs in observations:
        rows.append([
            obs.symbol, obs.timestamp_ms, obs.reference_price,
            obs.disagreement_bps, obs.source_count, obs.status,
            obs.venue_a, obs.bid_a, obs.ask_a, obs.depth_a,
            obs.venue_b, obs.bid_b, obs.ask_b, obs.depth_b,
        ])
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


def quality_gate(observations: list[DislocationObservation]) -> dict[str, Any]:
    """Validate ordering, duplicates, gaps, availability, and plausibility."""
    report: dict[str, Any] = {}
    report["n"] = len(observations)
    if len(observations) == 0:
        report["ok"] = False
        report["reasons"] = ["empty dataset"]
        return report
    ordered_ok = True
    seen: dict[str, dict[int, int]] = {}
    gaps = 0
    impossible = 0
    unavailable = 0
    first_ms: int | None = None
    last_ms: int | None = None
    symbols: list[str] = []
    for obs in observations:
        if obs.symbol not in seen:
            seen[obs.symbol] = {}
            symbols.append(obs.symbol)
        if first_ms is None or obs.timestamp_ms < first_ms:
            first_ms = obs.timestamp_ms
        if last_ms is None or obs.timestamp_ms > last_ms:
            last_ms = obs.timestamp_ms
        count = seen[obs.symbol].get(obs.timestamp_ms, 0)
        seen[obs.symbol][obs.timestamp_ms] = count + 1
        if obs.status == "UNAVAILABLE":
            unavailable = unavailable + 1
        if obs.disagreement_bps is not None and obs.disagreement_bps > MAX_PLAUSIBLE_DISAGREEMENT_BPS:
            impossible = impossible + 1
    for symbol in seen:
        stamps: list[int] = []
        for stamp in seen[symbol]:
            stamps.append(stamp)
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
        prior: int | None = None
        for stamp in ordered_stamps:
            if prior is not None and stamp <= prior:
                ordered_ok = False
            if prior is not None and (stamp - prior) > 3600000:
                gaps = gaps + 1
            prior = stamp
    duplicates = 0
    for symbol in seen:
        for stamp in seen[symbol]:
            if seen[symbol][stamp] > 1:
                duplicates = duplicates + (seen[symbol][stamp] - 1)
    span_days = 0.0
    if first_ms is not None and last_ms is not None:
        span_days = (last_ms - first_ms) / 86400000.0
    report["symbols"] = symbols
    report["ordered"] = ordered_ok
    report["duplicates"] = duplicates
    report["gaps_over_1h"] = gaps
    report["impossible_spreads"] = impossible
    report["unavailable"] = unavailable
    report["span_days"] = span_days
    reasons: list[str] = []
    if ordered_ok is False:
        reasons.append("timestamps out of order")
    if duplicates > 0:
        reasons.append("%d duplicate records" % duplicates)
    if impossible > 0:
        reasons.append("%d implausible disagreements beyond 500bps" % impossible)
    report["ok"] = len(reasons) == 0
    report["reasons"] = reasons
    return report


def check_executability(
    observations: list[DislocationObservation],
    *,
    fee_bps: float = 20.0,
    min_depth_notional: float = 1000.0,
) -> dict[str, Any]:
    """Determine whether an executable simulation is possible at all.

    A dislocation is only a tradable edge with synchronized per-venue bid/ask
    quotes, positive depth, and a known fee leg. Missing legs are named, never
    assumed; last-trade prices alone always fail this check.
    """
    missing: list[str] = []
    quotable = 0
    for obs in observations:
        legs = (obs.bid_a, obs.ask_a, obs.depth_a, obs.bid_b, obs.ask_b, obs.depth_b)
        valid = True
        for leg in legs:
            if leg is None or isinstance(leg, bool) or not leg > 0:
                valid = False
        if valid is False:
            continue
        if obs.ask_a is not None and obs.bid_a is not None and obs.ask_a < obs.bid_a:
            continue
        if obs.ask_b is not None and obs.bid_b is not None and obs.ask_b < obs.bid_b:
            continue
        if obs.depth_a is not None and obs.depth_b is not None:
            if obs.depth_a * obs.bid_a < min_depth_notional:
                continue
            if obs.depth_b * obs.bid_b < min_depth_notional:
                continue
        quotable = quotable + 1
    if quotable < MIN_OBSERVATIONS:
        missing.append("per-venue bid quotes with synchronized timestamps")
        missing.append("per-venue ask quotes with synchronized timestamps")
        missing.append("per-venue spread at signal time")
        missing.append("per-venue depth at signal time")
        missing.append("venue-pair fee schedule for the traded symbols")
        missing.append("transfer/settlement latency assumption between venues")
    usable = 0
    for obs in observations:
        if obs.status != "UNAVAILABLE" and obs.reference_price:
            usable = usable + 1
    executable = len(missing) == 0
    return {
        "executable": executable,
        "missing": missing,
        "usable_confirmations": usable,
        "quotable_observations": quotable,
        "fee_bps": float(fee_bps),
        "reason": "quotable per-venue books" if executable else (
            "aggregate disagreement without quotable per-venue prices cannot be simulated"),
    }


def describe_crossings(
    observations: list[DislocationObservation], hypothesis: DislocationHypothesis
) -> dict[str, Any]:
    """Descriptive only: threshold-crossing counts, never returns.

    Counting how often disagreement exceeds a threshold is measurement, not a
    backtest — no prices are assumed executable and no PnL is computed.
    """
    by_symbol: dict[str, list[DislocationObservation]] = {}
    for obs in observations:
        if obs.symbol not in by_symbol:
            by_symbol[obs.symbol] = []
        by_symbol[obs.symbol].append(obs)
    crossings = 0
    for symbol in by_symbol:
        streak = 0
        for obs in by_symbol[symbol]:
            if obs.disagreement_bps is not None and obs.disagreement_bps >= hypothesis.threshold_bps:
                streak = streak + 1
                if streak == hypothesis.persistence:
                    crossings = crossings + 1
            else:
                streak = 0
    return {
        "hypothesis_id": hypothesis.hypothesis_id,
        "threshold_bps": hypothesis.threshold_bps,
        "persistence": hypothesis.persistence,
        "crossings": crossings,
        "note": "descriptive count only; no executable prices, no returns computed",
    }


def evaluate_sufficiency(
    observations: list[DislocationObservation],
    regime_legs: list[str],
    total_tested_elsewhere: int = 0,
) -> dict[str, Any]:
    """Gate-grade sufficiency check ending in INCONCLUSIVE without execution data."""
    quality = quality_gate(observations)
    executable = check_executability(observations)
    legs: list[str] = []
    for leg in regime_legs:
        if leg not in legs:
            legs.append(leg)
    reasons: list[str] = []
    if executable["executable"] is False:
        for missing in executable["missing"]:
            reasons.append("missing executable data: %s" % missing)
    if len(observations) < MIN_OBSERVATIONS:
        reasons.append("only %d observations, need %d" % (len(observations), MIN_OBSERVATIONS))
    if quality.get("span_days", 0.0) < MIN_SPAN_DAYS:
        reasons.append("span %.1f days below %.0f-day gate minimum" % (
            quality.get("span_days", 0.0), MIN_SPAN_DAYS))
    if len(legs) < 2:
        reasons.append("only %d regime leg(s), need 2" % len(legs))
    if quality.get("ok", False) is False:
        for reason in quality.get("reasons", []):
            reasons.append("data quality: %s" % reason)
    verdict = "READY" if len(reasons) == 0 else "INCONCLUSIVE"
    return {
        "verdict": verdict,
        "reasons": reasons,
        "n": len(observations),
        "span_days": quality.get("span_days", 0.0),
        "regime_legs": legs,
        "dataset_hash": dataset_hash(observations),
        "hypotheses_registered": len(DISLOCATION_HYPOTHESES),
        "hypotheses_tested": 0,
        "note": "registered hypotheses consume no multiple-testing budget until tested",
        "ledger_tested_elsewhere": int(total_tested_elsewhere),
    }


def load_from_market_db(path: str, symbols: list[str] | None = None) -> list[DislocationObservation]:
    """Read cross-exchange confirmations from a Module 2 database (read-only)."""
    import sqlite3

    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT symbol, event_time_ms, payload_json FROM market_events"
            " WHERE event_type='crossExchangeConfirmation'"
        ).fetchall()
    finally:
        connection.close()
    wanted: dict[str, bool] = {}
    if symbols is not None:
        for symbol in symbols:
            wanted[str(symbol).strip().upper()] = True
    observations: list[DislocationObservation] = []
    for symbol, event_ms, payload in rows:
        token = str(symbol).strip().upper()
        if wanted and token not in wanted:
            continue
        try:
            doc = json.loads(payload)
        except Exception:
            continue
        ref = doc.get("reference_price")
        dis = doc.get("disagreement_bps")
        try:
            reference = float(ref) if ref is not None else None
        except (TypeError, ValueError):
            reference = None
        try:
            disagreement = float(dis) if dis is not None else None
        except (TypeError, ValueError):
            disagreement = None
        try:
            count = int(doc.get("source_count", 0))
        except (TypeError, ValueError):
            count = 0
        observations.append(DislocationObservation(
            symbol=token,
            timestamp_ms=int(event_ms),
            reference_price=reference,
            disagreement_bps=disagreement,
            source_count=count,
            status=str(doc.get("confirmation_status", "UNKNOWN")),
        ))
    # Re-polled confirmations repeat timestamps; dedup like funding history.
    deduped: dict[str, DislocationObservation] = {}
    for obs in observations:
        deduped["%s|%d" % (obs.symbol, obs.timestamp_ms)] = obs
    result: list[DislocationObservation] = []
    for key in deduped:
        result.append(deduped[key])
    return result
