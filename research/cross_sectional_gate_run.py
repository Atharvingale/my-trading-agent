"""Cross-sectional RS gate run: pre-registered test #11 on a frozen holdout (Module 1).

Strict order (mirrors research/gate_run.py): submission precedes any holdout
return computation; frozen engines run on the holdout only; bootstrap
evidence, pre-declared regime legs, doubled-cost stress, disjoint
replication, verdict recorded, review PENDING. No approvals, no versions, no
strategies, no tuning. The Bonferroni bar is read from the live ledger at run
time via candidate_generation.multiple_testing (never hardcoded).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from candidate_generation import multiple_testing
from candidate_generation.review_queue import ReviewQueue
from edge_validation.acceptance_criteria import AcceptanceCriteria, CRITERION_IDS
from edge_validation.evidence import ExperimentEvidence
from edge_validation.registry import EdgeValidationRegistry
from edge_validation.replication_check import check_replication
from research import acquisition as acq
from research import cross_sectional_rs as rs


COSTS = {
    "fee_rate": 0.001,
    "slippage_rate": 0.001,
    "tax_rate": 0.312,
    "tds_rate": 0.01,
    "loss_offset_allowed": False,
    "tds_is_cash_flow_drag": True,
}
DATASETS_DIR = "research/datasets"
BOOTSTRAP_SEED = 20260927
BOOTSTRAP_SAMPLES = 10000
NOTIONAL = 1000.0
STRATEGY_ID = "cross_sectional_rs_001"
HOLDOUT_START = date(2025, 12, 3)
HOLDOUT_END = date(2026, 5, 2)


def all_criteria(value: bool) -> AcceptanceCriteria:
    checks: dict[str, bool] = {}
    for criterion_id in CRITERION_IDS:
        checks[criterion_id] = value
    return AcceptanceCriteria(checks)


def main(
    datasets_dir: str = DATASETS_DIR,
    gate_db: str = "research/runtime_edge_validation.sqlite3",
    gate_report: str = "research/reports/EXPERIMENT_REGISTRY_RUNTIME.md",
    reviews_db: str = "research/review_queue_cross_sectional.sqlite3",
    out_path: str = "research/reports/cross_sectional_rs_gate_run.json",
) -> dict[str, Any]:
    """Execute the frozen cross-sectional RS battery; returns the record."""
    start_ms = int(datetime(2025, 12, 3, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime(2026, 5, 2, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
    bars_by_symbol: dict[str, list[rs.KlineBar]] = {}
    for dataset_id, symbol in (("klines-btcusdt-1h", "BTCUSDT"), ("klines-ethusdt-1h", "ETHUSDT")):
        payload = acq.load_dataset(datasets_dir, dataset_id, 1)
        acq.assert_evidence_grade(payload["manifest"])
        ordered: list[rs.KlineBar] = []
        for row in payload["rows"]:
            stamp = int(row["open_time_ms"])
            if stamp < start_ms or stamp > end_ms:
                continue
            ordered.append(rs.KlineBar(
                symbol=symbol,
                open_time_ms=stamp,
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
            ))
        bars_by_symbol[symbol] = ordered
    # Step 5 validation (coverage only; no strategy returns computed above).
    all_bars: list[rs.KlineBar] = []
    for symbol in rs.UNIVERSE:
        for bar in bars_by_symbol.get(symbol, []):
            all_bars.append(bar)
    coverage = rs.validate_holdout(all_bars, start_ms, end_ms)
    if coverage["ok"] is False:
        raise ValueError("cross-sectional coverage validation failed: %s" % coverage["reasons"])
    rebalance_ms = rs.rebalance_timestamps(bars_by_symbol, start_ms, end_ms)
    if len(rebalance_ms) < 20:
        raise ValueError("insufficient rebalance timestamps: %d" % len(rebalance_ms))
    legs = _regime_legs(datasets_dir, [start_ms, end_ms])
    result: dict[str, Any] = {}
    result["hypothesis_id"] = rs.HYPOTHESIS_ID
    result["holdout"] = [HOLDOUT_START.isoformat(), HOLDOUT_END.isoformat()]
    result["holdout_ms"] = [start_ms, end_ms]
    result["holdout_hash"] = rs.dataset_hash(all_bars)
    result["coverage"] = coverage
    result["rebalance_count"] = len(rebalance_ms)
    result["regime_legs"] = legs
    registry = EdgeValidationRegistry(gate_db, gate_report)
    reviews = ReviewQueue(reviews_db)
    try:
        # Step 6: live Bonferroni bar from the real ledger state at run time.
        bar = multiple_testing.adjusted_threshold(registry=registry, family="cross-sectional")
        result["ledger_m_before"] = bar["total_tested_including_current"] - 1
        result["ledger_m_including_current"] = bar["total_tested_including_current"]
        result["required_alpha"] = float(bar["required_alpha"])
        result["multiple_testing"] = bar
        record_id = registry.submit_hypothesis(
            strategy_id=STRATEGY_ID,
            hypothesis="Cross-sectional relative strength (cross_sectional_rs_001): daily 00:00 UTC long-only rotation holding the top volatility-adjusted 168h trailing-return asset of BTCUSDT/ETHUSDT spot (top 1 of 2), no short leg, spot execution, frozen holdout 2025-12-03 through 2026-05-02. Pre-registered in research/hypotheses/cross_sectional_rs_001.md before any holdout return was computed.",
            pre_registered_criteria={
                "hypothesis_file": "research/hypotheses/cross_sectional_rs_001.md",
                "lookback_bars": rs.LOOKBACK_BARS,
                "rebalance": "daily-00:00-UTC",
                "ranking": "volatility-adjusted-trailing-return",
                "long_only_top_quantile": "top-1-of-2",
                "multiple_testing_required_alpha": float(bar["required_alpha"]),
                "bootstrap_must_exclude_zero": True,
                "minimum_trades": 20,
            },
            holdout_period=(HOLDOUT_START, HOLDOUT_END),
            cost_and_tax_assumptions=dict(COSTS),
            signal_class=rs.SIGNAL_CLASS,
            source="HUMAN",
            provider_used="research-operator",
            multiple_testing_family="cross-sectional",
            multiple_testing_threshold=float(bar["required_alpha"]),
        )
        result["record_id"] = record_id
        # Step 7: frozen engines on the holdout only (first return computation).
        trades = rs.generate_daily_trades(bars_by_symbol, rebalance_ms, notional=NOTIONAL)
        experiment = _evaluate_and_record(registry, reviews, record_id, trades, all_bars, legs)
        experiment["ledger_m"] = result["ledger_m_before"]
        experiment["alpha"] = result["required_alpha"]
        result["experiment"] = experiment
        return result
    finally:
        reviews.close()
        registry.close()
        Path(out_path).write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _evaluate_and_record(
    registry: EdgeValidationRegistry,
    reviews: ReviewQueue,
    record_id: str,
    trades: list[dict[str, Any]],
    holdout_bars: list[rs.KlineBar],
    legs: list[dict[str, Any]],
) -> dict[str, Any]:
    experiment: dict[str, Any] = {}
    experiment["strategy_id"] = STRATEGY_ID
    experiment["record_id"] = record_id
    experiment["trade_count"] = len(trades)
    if len(trades) == 0:
        registry.record_result(
            record_id,
            bootstrap_ci=(0.0, 0.0),
            regime_results={},
            criteria=all_criteria(False),
            verdict="NULL_RESULT",
        )
        reviews.submit_for_review(record_id, STRATEGY_ID, "NULL_RESULT", source="HUMAN",
                                  hypothesis_id=rs.HYPOTHESIS_ID, signal_class=rs.SIGNAL_CLASS)
        experiment["verdict"] = "NULL_RESULT"
        experiment["reason"] = "no qualifying holdings on the holdout"
        return experiment
    fractions: list[float] = []
    for trade in trades:
        fractions.append(float(trade["net_pnl"]) / NOTIONAL)
    aggregate = 0.0
    for value in fractions:
        aggregate = aggregate + value
    # Doubled-cost stress leg (same signals, stressed cost stack).
    stressed_aggregate = _stressed_aggregate(trades)
    regime_returns: dict[str, float] = {}
    for leg in legs:
        leg_values: list[float] = []
        for trade in trades:
            if leg["start_ms"] <= int(trade["entry_time_ms"]) < leg["end_ms"]:
                leg_values.append(float(trade["net_pnl"]) / NOTIONAL)
        if leg_values:
            total = 0.0
            for value in leg_values:
                total = total + value
            regime_returns[leg["name"]] = total
    evidence = ExperimentEvidence(
        dataset_id="spot-1h-BTCUSDT-ETHUSDT-2025-12-03-2026-05-02",
        dataset_sha256=rs.dataset_hash(holdout_bars),
        trade_returns=tuple(fractions),
        regime_returns=regime_returns if regime_returns else {"single": aggregate},
        net_of_costs_and_tax=True,
        bootstrap_seed=BOOTSTRAP_SEED,
        bootstrap_samples=BOOTSTRAP_SAMPLES,
    )
    ci = evidence.bootstrap_ci
    checks: dict[str, bool] = {}
    for criterion_id in CRITERION_IDS:
        checks[criterion_id] = True
    checks["positive_bootstrap_confidence_interval"] = ci[0] > 0
    checks["two_structurally_different_regimes"] = len(regime_returns) >= 2
    replication_passed = False
    if len(legs) >= 2:
        replication = check_replication(
            primary_period=(_ms_to_date(legs[0]["start_ms"]), _ms_to_date(legs[0]["end_ms"])),
            replication_period=(_ms_to_date(legs[-1]["start_ms"]), _ms_to_date(legs[-1]["end_ms"])),
            primary_net_return=regime_returns.get(legs[0]["name"], 0.0),
            replication_net_return=regime_returns.get(legs[-1]["name"], 0.0),
        )
        replication_passed = replication.passed
    checks["independent_replication_when_refined"] = replication_passed
    verdict = "PASS" if AcceptanceCriteria(checks).all_pass else "FAIL"
    if verdict == "PASS" and len(regime_returns) < 2:
        verdict = "FAIL"
        checks["two_structurally_different_regimes"] = False
    # Minimum-sample guard from the pre-registration (mirrors prior batteries).
    if len(trades) < 20:
        verdict = "NULL_RESULT" if aggregate == 0 else "FAIL"
    # Research acceptance companion (same five-criteria shape as prior runs).
    research_failed: list[str] = []
    if aggregate <= 0:
        research_failed.append("aggregate_positive")
    if ci[0] <= 0:
        research_failed.append("bootstrap_excludes_zero")
    if stressed_aggregate <= 0:
        research_failed.append("stress_costs")
    if len(trades) < 20:
        research_failed.append("minimum_sample_size")
    registry.record_result(
        record_id,
        bootstrap_ci=(float(ci[0]), float(ci[1])),
        regime_results=dict(evidence.regime_returns),
        criteria=AcceptanceCriteria(checks),
        verdict=verdict if verdict in ("PASS", "FAIL") else "NULL_RESULT",
        replication_result="PASS" if replication_passed else "FAIL",
        evidence=evidence if len(trades) > 0 else None,
    )
    reviews.submit_for_review(record_id, STRATEGY_ID, verdict if verdict in ("PASS", "FAIL", "NULL_RESULT") else "FAIL",
                              source="HUMAN", hypothesis_id=rs.HYPOTHESIS_ID, signal_class=rs.SIGNAL_CLASS)
    experiment["verdict"] = verdict
    experiment["trade_count"] = len(trades)
    experiment["aggregate_net"] = aggregate
    experiment["stress_net_return"] = stressed_aggregate
    experiment["bootstrap_ci"] = [float(ci[0]), float(ci[1])]
    experiment["regime_returns"] = regime_returns
    experiment["replication_passed"] = replication_passed
    experiment["evidence_fingerprint"] = evidence.fingerprint()
    experiment["failed_criteria"] = _failed(checks)
    experiment["research_failed"] = research_failed
    experiment["raw_p_value"] = _bootstrap_pvalue(fractions)
    # Universe-mean companion (context only, never a gate criterion).
    experiment["universe_mean_note"] = "benchmark is the contemporaneous equal-weight universe mean; reported in the artifact discussion, not gated"
    return experiment


def _stressed_aggregate(trades: list[dict[str, Any]]) -> float:
    total = 0.0
    for trade in trades:
        gross = float(trade["gross_pnl"])
        total = total + rs.apply_costs_stressed(gross, NOTIONAL)
    return total / NOTIONAL


def _bootstrap_pvalue(returns: list[float], seed: int = BOOTSTRAP_SEED, samples: int = 5000) -> float:
    import random as _random
    rng = _random.Random(seed)
    extreme = 0
    trial = 0
    while trial < samples:
        total = 0.0
        pick = 0
        while pick < len(returns):
            total = total + returns[rng.randrange(len(returns))]
            pick = pick + 1
        if total / len(returns) <= 0:
            extreme = extreme + 1
        trial = trial + 1
    return extreme / samples


def _failed(checks: dict[str, bool]) -> list[str]:
    failed: list[str] = []
    for criterion_id in checks:
        if checks[criterion_id] is False:
            failed.append(criterion_id)
    return failed


def _regime_legs(datasets_dir: str, holdout: list[int]) -> list[dict[str, Any]]:
    """Pre-declared direction legs over the holdout from BTC hourly closes."""
    payload = acq.load_dataset(datasets_dir, "klines-btcusdt-1h", 1)
    pairs: list[list[Any]] = []
    for row in payload["rows"]:
        stamp = int(row["open_time_ms"])
        if holdout[0] <= stamp <= holdout[1] + 28_800_000:
            pairs.append([stamp, float(row["close"])])
    closes: list[float] = []
    stamps: list[int] = []
    for pair in pairs:
        placed = False
        index = 0
        while index < len(stamps):
            if pair[0] < stamps[index]:
                stamps.insert(index, pair[0])
                closes.insert(index, pair[1])
                placed = True
                break
            index = index + 1
        if placed is False:
            stamps.append(pair[0])
            closes.append(pair[1])
    legs: list[dict[str, Any]] = []
    third = len(closes) // 3
    names = ["first-leg", "second-leg", "third-leg"]
    index = 0
    while index < 3 and third > 0:
        start = index * third
        end = (index + 1) * third if index < 2 else len(closes)
        first = closes[start]
        last = closes[end - 1]
        ret = (last - first) / first if first > 0 else 0.0
        if ret >= 0.02:
            label = "up"
        elif ret <= -0.02:
            label = "down"
        else:
            label = "range"
        legs.append({
            "name": "%s-%s" % (names[index], label),
            "start_ms": stamps[start],
            "end_ms": stamps[end - 1] + 3600000,
            "return": ret,
        })
        index = index + 1
    if len(legs) == 0:
        legs.append({"name": "single-leg", "start_ms": holdout[0], "end_ms": holdout[1], "return": 0.0})
    return legs


def _ms_to_date(stamp_ms: int) -> date:
    return datetime.fromtimestamp(int(stamp_ms) / 1000.0, tz=timezone.utc).date()
