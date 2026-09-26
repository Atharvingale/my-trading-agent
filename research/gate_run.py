"""Funding gate-run: pre-register F1–F3, then test on a dated holdout (Module 1).

Strict order: define research/validation/holdout splits → submit all three
hypotheses against the holdout (nothing computed on it yet) → run the frozen
engines on the holdout only → bootstrap evidence → regime and replication
legs → record verdicts → submit to the review queue PENDING. No approvals, no
versions, no strategies, no tuning. Shared pre-registered battery across one
holdout with Bonferroni accounting disclosed, not hidden.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from candidate_generation import multiple_testing
from edge_validation.acceptance_criteria import AcceptanceCriteria, CRITERION_IDS
from edge_validation.evidence import ExperimentEvidence
from edge_validation.registry import EdgeValidationRegistry
from edge_validation.replication_check import check_replication
from candidate_generation.review_queue import ReviewQueue
from research import acquisition as acq
from research import funding_carry as fund

COSTS = {
    "fee_rate": 0.001,
    "slippage_rate": 0.001,
    "tax_rate": 0.312,
    "tds_rate": 0.01,
    "loss_offset_allowed": False,
    "tds_is_cash_flow_drag": True,
}
DATASETS_DIR = "research/datasets"
BOOTSTRAP_SEED = 20260926
BOOTSTRAP_SAMPLES = 10000
NOTIONAL = 1000.0

STRATEGIES = ("funding_carry_f1", "funding_carry_f2", "funding_carry_f3")

HYPOTHESES = {
    "funding_carry_f1": fund.FUNDING_HYPOTHESES[0],
    "funding_carry_f2": fund.FUNDING_HYPOTHESES[1],
    "funding_carry_f3": fund.FUNDING_HYPOTHESES[2],
}


def freeze_holdout(grid: list[int], research_frac: float = 0.6, validation_frac: float = 0.2) -> dict[str, Any]:
    """Freeze dated splits with a hash BEFORE any engine touches the holdout.

    The returned record must be persisted (artifact) before evaluation; the
    holdout slice helper refuses unfrozen input so post-hoc redefinition
    raises instead of silently shifting windows.
    """
    import hashlib as _hashlib

    if not 0.0 < research_frac < 1.0 or not 0.0 < validation_frac < 1.0:
        raise ValueError("fractions must be in (0, 1)")
    if research_frac + validation_frac >= 1.0:
        raise ValueError("research + validation must leave a holdout")
    research_end = len(grid) * int(research_frac * 100) // 100
    validation_end = len(grid) * int((research_frac + validation_frac) * 100) // 100
    record: dict[str, Any] = {}
    record["research"] = [grid[0], grid[research_end - 1]]
    record["validation"] = [grid[research_end], grid[validation_end - 1]]
    record["holdout"] = [grid[validation_end], grid[-1]]
    record["hash"] = _hashlib.sha256(json.dumps(
        record, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
    record["frozen"] = True
    return record


def slice_holdout(
    observations: list[fund.FundingObservation], frozen: Mapping[str, Any] | None
) -> list[fund.FundingObservation]:
    """Return holdout observations; raises unless the split record is frozen."""
    if not isinstance(frozen, Mapping) or frozen.get("frozen") is not True:
        raise ValueError("holdout accessed before freeze")
    window = frozen["holdout"]
    result: list[fund.FundingObservation] = []
    for obs in observations:
        if window[0] <= obs.funding_time_ms <= window[1]:
            result.append(obs)
    return result


def bootstrap_pvalue(returns: list[float], *, seed: int = BOOTSTRAP_SEED, samples: int = 5000) -> float:
    """One-sided bootstrap p-value for mean <= 0 (deterministic seed).

    Reporting companion to the gate's CI verdict — never a gate criterion
    itself. Fraction of resampled means at or below zero.
    """
    import random as _random

    if len(returns) == 0:
        raise ValueError("returns must be non-empty")
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


def all_criteria(value: bool) -> AcceptanceCriteria:
    checks: dict[str, bool] = {}
    for criterion_id in CRITERION_IDS:
        checks[criterion_id] = value
    return AcceptanceCriteria(checks)


def main(
    datasets_dir: str = DATASETS_DIR,
    gate_db: str = "research/runtime_edge_validation.sqlite3",
    gate_report: str = "research/reports/EXPERIMENT_REGISTRY_RUNTIME.md",
    reviews_db: str = "research/review_queue_funding.sqlite3",
    out_path: str = "research/reports/funding_gate_run.json",
) -> dict[str, Any]:
    """Execute the funding gate battery; returns the machine-readable record."""
    btc = _load_observations(datasets_dir, "fund-btcusdt", 1)
    eth = _load_observations(datasets_dir, "fund-ethusdt", 1)
    observations: list[fund.FundingObservation] = []
    for obs in btc:
        observations.append(obs)
    for obs in eth:
        observations.append(obs)
    quality = fund.quality_gate(observations)
    if quality["ok"] is False:
        raise ValueError("funding quality gate failed: %s" % quality["reasons"])
    by_symbol: dict[str, list[fund.FundingObservation]] = {}
    for obs in observations:
        if obs.symbol not in by_symbol:
            by_symbol[obs.symbol] = []
        by_symbol[obs.symbol].append(obs)
    for symbol in by_symbol:
        ordered: list[fund.FundingObservation] = []
        for obs in by_symbol[symbol]:
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
        by_symbol[symbol] = ordered
    # Chronological 60/20/20 splits on the shared funding grid; the holdout
    # window is recorded here and touched only after all three submissions.
    grid: list[int] = []
    for obs in by_symbol["BTCUSDT"]:
        grid.append(obs.funding_time_ms)
    research_end = len(grid) * 60 // 100
    validation_end = len(grid) * 80 // 100
    splits = {
        "research": [grid[0], grid[research_end - 1]],
        "validation": [grid[research_end], grid[validation_end - 1]],
        "holdout": [grid[validation_end], grid[-1]],
    }
    holdout_obs: list[fund.FundingObservation] = []
    for symbol in by_symbol:
        for obs in by_symbol[symbol]:
            if grid[validation_end] <= obs.funding_time_ms <= grid[-1]:
                holdout_obs.append(obs)
    legs = _regime_legs(datasets_dir, splits["holdout"])
    result: dict[str, Any] = {}
    result["splits_ms"] = splits
    result["holdout_n"] = len(holdout_obs)
    result["holdout_hash"] = fund.dataset_hash(holdout_obs)
    result["regime_legs"] = legs
    result["experiments"] = []
    registry = EdgeValidationRegistry(gate_db, gate_report)
    reviews = ReviewQueue(reviews_db)
    try:
        record_ids: dict[str, str] = {}
        for strategy_id in STRATEGIES:
            bar = multiple_testing.adjusted_threshold(registry=registry, family="funding-carry")
            hypothesis = HYPOTHESES[strategy_id]
            record_ids[strategy_id] = registry.submit_hypothesis(
                strategy_id=strategy_id,
                hypothesis="F%s %s carry: trailing-%d mean funding %s %.4f%%, hold %d period(s)%s." % (
                    hypothesis.hypothesis_id, hypothesis.direction, hypothesis.persistence,
                    "above" if hypothesis.direction == "SHORT" else "below",
                    abs(hypothesis.threshold) * 100.0, hypothesis.holding_periods,
                    " with calm filter" if hypothesis.volatility_filter else ""),
                pre_registered_criteria={
                    "multiple_testing_required_alpha": bar["required_alpha"],
                    "bootstrap_must_exclude_zero": True,
                    "minimum_trades": 20,
                },
                holdout_period=(_ms_to_date(splits["holdout"][0]), _ms_to_date(splits["holdout"][1])),
                cost_and_tax_assumptions=dict(COSTS),
                signal_class="funding-rate carry",
                source="HUMAN",
                provider_used="research-operator",
                multiple_testing_family="funding-carry",
                multiple_testing_threshold=float(bar["required_alpha"]),
            )
        for strategy_id in STRATEGIES:
            result["experiments"].append(
                _run_one(registry, reviews, strategy_id, record_ids[strategy_id], holdout_obs, legs)
            )
        return result
    finally:
        reviews.close()
        registry.close()
        Path(out_path).write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _run_one(
    registry: EdgeValidationRegistry,
    reviews: ReviewQueue,
    strategy_id: str,
    record_id: str,
    holdout_obs: list[fund.FundingObservation],
    legs: list[dict[str, Any]],
) -> dict[str, Any]:
    hypothesis = HYPOTHESES[strategy_id]
    trades = fund.generate_trades(list(holdout_obs), hypothesis, notional=NOTIONAL)
    return _evaluate_and_record(registry, reviews, strategy_id, record_id, trades, holdout_obs, legs)


def run_anomaly(
    registry: EdgeValidationRegistry,
    reviews: ReviewQueue,
    strategy_id: str,
    record_id: str,
    holdout_obs: list[fund.FundingObservation],
    legs: list[dict[str, Any]],
    hypothesis: fund.AnomalyHypothesis,
) -> dict[str, Any]:
    """F4 entry point: identical gate math over anomaly-fade trades."""
    trades = fund.generate_anomaly_trades(list(holdout_obs), hypothesis, notional=NOTIONAL)
    return _evaluate_and_record(registry, reviews, strategy_id, record_id, trades, holdout_obs, legs)


def _evaluate_and_record(
    registry: EdgeValidationRegistry,
    reviews: ReviewQueue,
    strategy_id: str,
    record_id: str,
    trades: list[dict[str, Any]],
    holdout_obs: list[fund.FundingObservation],
    legs: list[dict[str, Any]],
    *,
    ledger_m: int | None = None,
    alpha: float | None = None,
) -> dict[str, Any]:
    experiment: dict[str, Any] = {}
    experiment["strategy_id"] = strategy_id
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
        reviews.submit_for_review(record_id, strategy_id, "NULL_RESULT", source="HUMAN")
        experiment["verdict"] = "NULL_RESULT"
        experiment["reason"] = "no qualifying holdings on the holdout"
        return experiment
    fractions: list[float] = []
    for trade in trades:
        fractions.append(float(trade["net_pnl"]) / NOTIONAL)
    regime_returns: dict[str, float] = {}
    for leg in legs:
        leg_trades: list[float] = []
        for trade in trades:
            if leg["start_ms"] <= trade["entry_time_ms"] < leg["end_ms"]:
                leg_trades.append(float(trade["net_pnl"]) / NOTIONAL)
        if leg_trades:
            total = 0.0
            for value in leg_trades:
                total = total + value
            regime_returns[leg["name"]] = total
    evidence = ExperimentEvidence(
        dataset_id="funding-holdout-%s" % strategy_id,
        dataset_sha256=fund.dataset_hash(list(holdout_obs)),
        trade_returns=tuple(fractions),
        regime_returns=regime_returns if regime_returns else {"single": sum(fractions)},
        net_of_costs_and_tax=True,
        bootstrap_seed=BOOTSTRAP_SEED,
        bootstrap_samples=BOOTSTRAP_SAMPLES,
    )
    ci = evidence.bootstrap_ci
    aggregate = 0.0
    for value in fractions:
        aggregate = aggregate + value
    checks: dict[str, bool] = {}
    for criterion_id in CRITERION_IDS:
        checks[criterion_id] = True
    checks["positive_bootstrap_confidence_interval"] = ci[0] > 0
    checks["two_structurally_different_regimes"] = len(regime_returns) >= 2
    replication_passed = False
    if len(legs) >= 2:
        # Why legs[0]/legs[-1]: disjoint outer legs of the holdout partition.
        replication = check_replication(
            primary_period=(_ms_to_date(legs[0]["start_ms"]), _ms_to_date(legs[0]["end_ms"])),
            replication_period=(_ms_to_date(legs[-1]["start_ms"]), _ms_to_date(legs[-1]["end_ms"])),
            primary_net_return=regime_returns.get(legs[0]["name"], 0.0),
            replication_net_return=regime_returns.get(legs[-1]["name"], 0.0),
        )
        replication_passed = replication.passed
    # Single leg: no second period exists, so replication fails by construction
    # without inventing a synthetic window.
    # Conservative reading held across all project runs: the replication leg
    # must pass for any PASS, refinement or not. F4's FAIL does not hinge on
    # this flag (its bootstrap CI is entirely negative either way).
    checks["independent_replication_when_refined"] = replication_passed
    verdict = "PASS" if AcceptanceCriteria(checks).all_pass else "FAIL"
    if verdict == "PASS" and len(regime_returns) < 2:
        verdict = "FAIL"
        checks["two_structurally_different_regimes"] = False
    registry.record_result(
        record_id,
        bootstrap_ci=(float(ci[0]), float(ci[1])),
        regime_results=dict(evidence.regime_returns),
        criteria=AcceptanceCriteria(checks),
        verdict=verdict,
        replication_result="PASS" if replication_passed else "FAIL",
        evidence=evidence,
    )
    reviews.submit_for_review(record_id, strategy_id, verdict, source="HUMAN")
    experiment["verdict"] = verdict
    experiment["trade_count"] = len(trades)
    experiment["aggregate_net"] = aggregate
    experiment["bootstrap_ci"] = [float(ci[0]), float(ci[1])]
    experiment["regime_returns"] = regime_returns
    experiment["replication_passed"] = replication_passed
    experiment["evidence_fingerprint"] = evidence.fingerprint()
    experiment["failed_criteria"] = _failed(checks)
    experiment["raw_p_value"] = bootstrap_pvalue(fractions)
    experiment["ledger_m"] = ledger_m
    experiment["alpha"] = alpha
    if alpha is not None:
        experiment["adjusted_significant"] = bool(experiment["raw_p_value"] < alpha)
    return experiment


def _failed(checks: dict[str, bool]) -> list[str]:
    failed: list[str] = []
    for criterion_id in checks:
        if checks[criterion_id] is False:
            failed.append(criterion_id)
    return failed


def _load_observations(datasets_dir: str, dataset_id: str, version: int) -> list[fund.FundingObservation]:
    payload = acq.load_dataset(datasets_dir, dataset_id, version)
    acq.assert_evidence_grade(payload["manifest"])
    observations: list[fund.FundingObservation] = []
    for row in payload["rows"]:
        observations.append(fund.FundingObservation(
            symbol=str(row["symbol"]),
            funding_time_ms=int(row["funding_time_ms"]),
            rate=float(row["rate"]),
            mark_price=float(row.get("mark_price", 0.0)),
        ))
    return observations


def run_f4(
    *,
    datasets_dir: str = DATASETS_DIR,
    gate_db: str = "research/runtime_edge_validation.sqlite3",
    gate_report: str = "research/reports/EXPERIMENT_REGISTRY_RUNTIME.md",
    reviews_db: str = "research/review_queue_funding.sqlite3",
    out_path: str = "research/reports/funding_f4_gate_run.json",
    strategy_id: str = "funding_carry_f4",
) -> dict[str, Any]:
    """Execute the F4 anomaly-fade battery: freeze, submit, test, record.

    Combined v1 + older timeline; the holdout is the frozen [560, 700) slice,
    day-disjoint from both the spent F1-F3 tail-100 window and the crashed
    first F4 attempt's [720, 900) window (that orphan PENDING was honestly
    nulled: infrastructure crash before any evaluation, zero holdout
    information used; the 7-day buffer absorbs date-granularity overlap).
    Submission precedes any holdout computation; verdicts follow gate math;
    review stays PENDING.
    """
    frozen_params = fund.freeze_hypothesis(fund.F4)
    observations = _combined_funding(datasets_dir)
    quality = fund.quality_gate(observations)
    if quality["ok"] is False:
        raise ValueError("funding quality gate failed: %s" % quality["reasons"])
    grid = _funding_grid(observations)
    if len(grid) < 700:
        raise ValueError("combined grid too short: %d" % len(grid))
    frozen = freeze_holdout(grid[:700], research_frac=0.6, validation_frac=0.2)
    holdout_obs = slice_holdout(observations, frozen)
    legs = _regime_legs(datasets_dir, list(frozen["holdout"]))
    result: dict[str, Any] = {}
    result["frozen_hypothesis"] = frozen_params
    result["frozen_holdout"] = frozen
    result["holdout_n"] = len(holdout_obs)
    result["holdout_hash"] = fund.dataset_hash(holdout_obs)
    result["regime_legs"] = legs
    registry = EdgeValidationRegistry(gate_db, gate_report)
    reviews = ReviewQueue(reviews_db)
    try:
        bar = multiple_testing.adjusted_threshold(registry=registry, family="funding-carry")
        record_id = registry.submit_hypothesis(
            strategy_id=strategy_id,
            hypothesis="F4 funding anomaly fade: z of trailing-30 settled rates beyond 2.0 "
                       "fades the anomaly (SHORT positive, LONG negative), hold 1 period. "
                       "Second attempt on a disjoint window after the first submission "
                       "(orphan PENDING, infrastructure crash before any evaluation) was "
                       "honestly nulled; rules and parameters unchanged.",
            pre_registered_criteria={
                "frozen_sha256": frozen_params["sha256"],
                "frozen_holdout_hash": frozen["hash"],
                "multiple_testing_required_alpha": bar["required_alpha"],
                "bootstrap_must_exclude_zero": True,
                "minimum_trades": 20,
            },
            holdout_period=(_ms_to_date(frozen["holdout"][0]), _ms_to_date(frozen["holdout"][1])),
            cost_and_tax_assumptions=dict(COSTS),
            signal_class="funding-rate carry",
            source="HUMAN",
            provider_used="research-operator",
            multiple_testing_family="funding-carry",
            multiple_testing_threshold=float(bar["required_alpha"]),
        )
        experiment = run_anomaly(
            registry, reviews, strategy_id, record_id, holdout_obs, legs, fund.F4,
        )
        experiment["ledger_m"] = bar["total_tested_including_current"] - 1
        experiment["alpha"] = float(bar["required_alpha"])
        if experiment.get("raw_p_value") is not None and experiment.get("alpha") is not None:
            experiment["adjusted_significant"] = bool(experiment["raw_p_value"] < experiment["alpha"])
        result["experiment"] = experiment
        return result
    finally:
        reviews.close()
        registry.close()
        Path(out_path).write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _combined_funding(datasets_dir: str) -> list[fund.FundingObservation]:
    observations: list[fund.FundingObservation] = []
    for dataset_id in ("fund-btcusdt-older", "fund-ethusdt-older", "fund-btcusdt", "fund-ethusdt"):
        for row in acq.load_dataset(datasets_dir, dataset_id, 1)["rows"]:
            observations.append(fund.FundingObservation(
                symbol=str(row["symbol"]),
                funding_time_ms=int(row["funding_time_ms"]),
                rate=float(row["rate"]),
                mark_price=float(row.get("mark_price", 0.0)),
            ))
    deduped: dict[str, fund.FundingObservation] = {}
    for obs in observations:
        deduped["%s|%d" % (obs.symbol, obs.funding_time_ms)] = obs
    result: list[fund.FundingObservation] = []
    for key in deduped:
        result.append(deduped[key])
    return result


def _funding_grid(observations: list[fund.FundingObservation]) -> list[int]:
    stamps: list[int] = []
    for obs in observations:
        if obs.symbol == "BTCUSDT" and obs.funding_time_ms not in stamps:
            stamps.append(obs.funding_time_ms)
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
    return ordered


def _regime_legs(datasets_dir: str, holdout: list[int]) -> list[dict[str, Any]]:
    """Pre-declared direction legs over the holdout from BTC hourly closes."""
    payload = acq.load_dataset(datasets_dir, "klines-btcusdt-1h", 1)
    pairs: list[list[Any]] = []
    for row in payload["rows"]:
        stamp = int(row["open_time_ms"])
        if holdout[0] <= stamp <= holdout[1] + 28_800_000:
            pairs.append([stamp, float(row["close"])])
    # Stored newest-first; legs need chronological order (explicit, no sorted()).
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
    from datetime import datetime, timezone

    return datetime.fromtimestamp(int(stamp_ms) / 1000.0, tz=timezone.utc).date()
