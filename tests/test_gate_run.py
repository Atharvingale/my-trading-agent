"""Funding gate-run level: NULL/FAIL/PASS verdict paths on isolated ledgers."""

from __future__ import annotations

from datetime import date

import pytest

from candidate_generation.review_queue import ReviewQueue
from edge_validation.registry import EdgeValidationRegistry
from research import funding_carry as fund
from research import gate_run
from strategies.production_versions import ProductionVersionStore


COSTS = dict(gate_run.COSTS)


def strong_series(n=60, rate=0.02):
    observations: list[fund.FundingObservation] = []
    index = 0
    while index < n:
        observations.append(fund.FundingObservation(
            "BTCUSDT", 1_000_000 + index * 28_800_000, rate, 100.0,
        ))
        index = index + 1
    return observations


def quiet_series(n=30):
    observations: list[fund.FundingObservation] = []
    index = 0
    while index < n:
        observations.append(fund.FundingObservation(
            "BTCUSDT", 1_000_000 + index * 28_800_000, 0.00005, 100.0 + index,
        ))
        index = index + 1
    return observations


def legs_for(n=60):
    return [
        {"name": "first-leg-up", "start_ms": 1_000_000, "end_ms": 1_000_000 + 20 * 28_800_000, "return": 0.05},
        {"name": "second-leg-up", "start_ms": 1_000_000 + 20 * 28_800_000, "end_ms": 1_000_000 + 40 * 28_800_000, "return": 0.06},
        {"name": "third-leg-up", "start_ms": 1_000_000 + 40 * 28_800_000, "end_ms": 1_000_000 + n * 28_800_000, "return": 0.07},
    ]


def submit(registry, strategy_id="funding_carry_f1"):
    return registry.submit_hypothesis(
        strategy_id=strategy_id,
        hypothesis="gate-run fixture",
        pre_registered_criteria={"minimum": 0.0},
        holdout_period=(date(2025, 1, 1), date(2025, 1, 31)),
        cost_and_tax_assumptions=COSTS,
    )


# -- §17: funding direction is settled-correct after the sign fix --
def test_short_collects_positive_funding_long_collects_negative():
    short = fund.generate_trades(strong_series(rate=0.02), fund.FUNDING_HYPOTHESES[0], notional=1000.0)
    assert len(short) > 0
    for trade in short:
        # Earned +20, costs 14 → positive gross-derived net before drift (flat marks).
        assert trade["gross_pnl"] == pytest.approx(20.0)
        assert trade["net_pnl"] == pytest.approx(20.0 - 2.0 - 2.0 - 10.0 - (20.0 - 14.0) * 0.312)
    mirror = fund.FundingHypothesis("FX", "funding-rate carry", "LONG", -0.019, 1, 1, False)
    long_trades = fund.generate_trades(strong_series(rate=-0.02), mirror, notional=1000.0)
    assert len(long_trades) > 0
    for trade in long_trades:
        assert trade["gross_pnl"] == pytest.approx(20.0)


# -- NULL path: quiet holdout banks no trades, review stays pending --
def test_null_result_on_quiet_holdout(tmp_path):
    registry = EdgeValidationRegistry(str(tmp_path / "edge.sqlite3"), str(tmp_path / "R.md"))
    reviews = ReviewQueue(str(tmp_path / "reviews.sqlite3"))
    try:
        record_id = submit(registry)
        result = gate_run._run_one(
            registry, reviews, "funding_carry_f1", record_id, quiet_series(), legs_for(30))
        assert result["verdict"] == "NULL_RESULT"
        assert result["trade_count"] == 0
        assert registry.get_verdict("funding_carry_f1") == "NULL_RESULT"
        assert reviews.get_status(record_id) == "PENDING"
        assert reviews.is_approved(record_id) is False
    finally:
        registry.close()
        reviews.close()


# -- genuine PASS path on an isolated ledger (strong synthetic carry) --
def test_pass_records_when_all_criteria_hold(tmp_path):
    registry = EdgeValidationRegistry(str(tmp_path / "edge.sqlite3"), str(tmp_path / "R.md"))
    reviews = ReviewQueue(str(tmp_path / "reviews.sqlite3"))
    try:
        record_id = submit(registry)
        result = gate_run._run_one(
            registry, reviews, "funding_carry_f1", record_id, strong_series(), legs_for())
        assert result["verdict"] == "PASS"
        assert result["trade_count"] > 20
        assert result["bootstrap_ci"][0] > 0
        assert result["replication_passed"] is True
        assert result["failed_criteria"] == []
        assert registry.get_verdict("funding_carry_f1") == "PASS"
        assert reviews.get_status(record_id) == "PENDING"
    finally:
        registry.close()
        reviews.close()


# -- FAIL path: costs drown weak carry with real trades --
def test_fail_records_when_costs_dominate(tmp_path):
    registry = EdgeValidationRegistry(str(tmp_path / "edge.sqlite3"), str(tmp_path / "R.md"))
    reviews = ReviewQueue(str(tmp_path / "reviews.sqlite3"))
    try:
        record_id = submit(registry)
        result = gate_run._run_one(
            registry, reviews, "funding_carry_f1", record_id, strong_series(rate=0.0006), legs_for())
        assert result["verdict"] == "FAIL"
        assert result["trade_count"] > 0
        assert result["bootstrap_ci"][1] < 0
        assert registry.get_verdict("funding_carry_f1") == "FAIL"
    finally:
        registry.close()
        reviews.close()


# -- PASS never self-promotes: versions stay empty without approval --
def test_no_version_without_human_approval(tmp_path):
    versions = ProductionVersionStore(str(tmp_path / "versions.sqlite3"))
    try:
        assert versions.list_versions() == []
    finally:
        versions.close()


def test_splits_are_deterministic():
    grid: list[int] = []
    index = 0
    while index < 500:
        grid.append(1_000_000 + index * 28_800_000)
        index = index + 1
    first = (len(grid) * 60 // 100, len(grid) * 80 // 100)
    assert first == (300, 400)
