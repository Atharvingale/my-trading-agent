"""Cycle-2 research: F4 anomaly class, frozen holdouts, ledger continuity."""

from __future__ import annotations

from datetime import date

import pytest

from candidate_generation import multiple_testing
from edge_validation.registry import EdgeValidationRegistry
from candidate_generation.review_queue import ReviewQueue
from research import dislocation as dis
from research import funding_carry as fund
from research import gate_run
from strategies.production_versions import ProductionVersionStore


COSTS = dict(gate_run.COSTS)


def anomaly_series(n=40, spike_last=None):
    observations: list[fund.FundingObservation] = []
    index = 0
    while index < n:
        rate = 0.0001
        if spike_last is not None and index == n - 1:
            rate = spike_last
        observations.append(fund.FundingObservation(
            "BTCUSDT", 1_000_000 + index * 28_800_000, rate, 100.0 + index * 0.1,
        ))
        index = index + 1
    return observations


def test_f4_freeze_record_is_stable_and_sensitive():
    first = fund.freeze_hypothesis(fund.F4)
    second = fund.freeze_hypothesis(fund.F4)
    assert first == second
    assert first["sha256"] and len(first["sha256"]) == 64
    altered = fund.AnomalyHypothesis("F4", "funding-rate carry", 30, 2.5, 1)
    assert fund.freeze_hypothesis(altered)["sha256"] != first["sha256"]
    assert fund.F4.lookback == 30
    assert fund.F4.z_threshold == 2.0
    assert fund.F4.holding_periods == 1


def test_f4_trades_are_deterministic():
    first = fund.generate_anomaly_trades(anomaly_series(), fund.F4)
    second = fund.generate_anomaly_trades(anomaly_series(), fund.F4)
    assert first == second


def test_f4_future_spike_cannot_trigger_entries():
    # Only the final rate spikes; trailing windows for completable entries
    # never include it, and the spike itself has no exit period after it.
    trades = fund.generate_anomaly_trades(anomaly_series(spike_last=0.009), fund.F4)
    assert trades == []


def test_f4_direction_fades_the_anomaly():
    observations: list[fund.FundingObservation] = []
    index = 0
    while index < 40:
        rate = 0.0001 if index < 35 else 0.002
        observations.append(fund.FundingObservation(
            "BTCUSDT", 1_000_000 + index * 28_800_000, rate, 100.0,
        ))
        index = index + 1
    trades = fund.generate_anomaly_trades(observations, fund.F4)
    assert len(trades) > 0
    for trade in trades:
        assert trade["direction"] == "SHORT"
        assert trade["z_score"] > 2.0
        assert trade["exit_time_ms"] > trade["entry_time_ms"]


def test_f4_zero_variance_windows_skip_safely():
    observations: list[fund.FundingObservation] = []
    index = 0
    while index < 40:
        observations.append(fund.FundingObservation(
            "BTCUSDT", 1_000_000 + index * 28_800_000, 0.0001, 100.0,
        ))
        index = index + 1
    assert fund.generate_anomaly_trades(observations, fund.F4) == []
    with pytest.raises(ValueError, match="lookback"):
        fund.generate_anomaly_trades(observations, fund.AnomalyHypothesis("FX", "x", 2, 2.0, 1))
    with pytest.raises(ValueError, match="z_threshold"):
        fund.generate_anomaly_trades(observations, fund.AnomalyHypothesis("FX", "x", 30, 0.0, 1))


def test_holdout_freeze_and_slice():
    grid: list[int] = []
    index = 0
    while index < 100:
        grid.append(1_000_000 + index * 28_800_000)
        index = index + 1
    frozen = gate_run.freeze_holdout(grid)
    assert frozen["frozen"] is True
    assert gate_run.freeze_holdout(grid)["hash"] == frozen["hash"]
    assert frozen["holdout"] == [grid[80], grid[99]]
    with pytest.raises(ValueError, match="before freeze"):
        gate_run.slice_holdout(anomaly_series(100), None)
    with pytest.raises(ValueError, match="before freeze"):
        gate_run.slice_holdout(anomaly_series(100), {"frozen": False})
    sliced = gate_run.slice_holdout(anomaly_series(100), frozen)
    assert len(sliced) == 20
    with pytest.raises(ValueError, match="holdout"):
        gate_run.freeze_holdout(grid, research_frac=0.7, validation_frac=0.4)


def test_ledger_m_preserved_and_incremented(tmp_path):
    before = multiple_testing.count_hypotheses(
        database_path="D:/my-trading-app/research/runtime_edge_validation.sqlite3")
    assert before >= 8
    registry = EdgeValidationRegistry(str(tmp_path / "edge.sqlite3"), str(tmp_path / "R.md"))
    try:
        assert multiple_testing.count_hypotheses(registry=registry) == 0
        registry.submit_hypothesis(
            strategy_id="probe_v1",
            hypothesis="ledger increment probe",
            pre_registered_criteria={"minimum": 0.0},
            holdout_period=(date(2025, 1, 1), date(2025, 1, 31)),
            cost_and_tax_assumptions=COSTS,
        )
        assert multiple_testing.count_hypotheses(registry=registry) == 1
        assert multiple_testing.required_significance(base_alpha=0.05, total_tested=9) == pytest.approx(0.05 / 9)
    finally:
        registry.close()


def test_prior_experiments_immutable():
    import sqlite3 as _sqlite3

    connection = _sqlite3.connect("D:/my-trading-app/research/runtime_edge_validation.sqlite3")
    try:
        rows = connection.execute(
            "SELECT strategy_id, verdict FROM edge_validation_records"
            " WHERE strategy_family LIKE 'funding_carry_f%' ORDER BY rowid").fetchall()
    finally:
        connection.close()
    verdicts: list[str] = []
    for strategy_id, verdict in rows:
        verdicts.append("%s:%s" % (strategy_id, verdict))
    assert "funding_carry_f1:NULL_RESULT" in verdicts
    assert "funding_carry_f2:NULL_RESULT" in verdicts
    assert "funding_carry_f3:NULL_RESULT" in verdicts


def test_anomaly_null_without_promotion(tmp_path):
    registry = EdgeValidationRegistry(str(tmp_path / "edge.sqlite3"), str(tmp_path / "R.md"))
    reviews = ReviewQueue(str(tmp_path / "reviews.sqlite3"))
    versions = ProductionVersionStore(str(tmp_path / "versions.sqlite3"))
    try:
        record_id = registry.submit_hypothesis(
            strategy_id="funding_carry_f4",
            hypothesis="F4 fixture",
            pre_registered_criteria={"minimum": 0.0},
            holdout_period=(date(2025, 2, 1), date(2025, 2, 28)),
            cost_and_tax_assumptions=COSTS,
        )
        legs = [{"name": "leg", "start_ms": 1_000_000, "end_ms": 2_000_000, "return": 0.0}]
        result = gate_run.run_anomaly(
            registry, reviews, "funding_carry_f4", record_id, anomaly_series(35), legs, fund.F4)
        assert result["verdict"] == "NULL_RESULT"
        assert reviews.is_approved(record_id) is False
        assert versions.list_versions() == []
    finally:
        registry.close()
        reviews.close()
        versions.close()


def test_bootstrap_pvalue_deterministic_and_sided():
    gains: list[float] = []
    index = 0
    while index < 20:
        gains.append(0.01)
        index = index + 1
    losses: list[float] = []
    index = 0
    while index < 20:
        losses.append(-0.01)
        index = index + 1
    assert gate_run.bootstrap_pvalue(gains) == gate_run.bootstrap_pvalue(gains)
    assert gate_run.bootstrap_pvalue(gains) == pytest.approx(0.0)
    assert gate_run.bootstrap_pvalue(losses) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="non-empty"):
        gate_run.bootstrap_pvalue([])


def test_xex_quote_legs_and_fees():
    observations: list[dis.DislocationObservation] = []
    index = 0
    while index < 10:
        observations.append(dis.DislocationObservation(
            "BTCUSDT", 1_000_000 + index * 60_000, 85000.0, 8.0, 4, "CONFIRMED",
            venue_a="binance", bid_a=84990.0, ask_a=85000.0, depth_a=2.0,
            venue_b="coinbase", bid_b=85070.0, ask_b=85080.0, depth_b=2.0,
        ))
        index = index + 1
    verdict = dis.check_executability(observations, fee_bps=20.0)
    assert verdict["quotable_observations"] == 10
    assert verdict["fee_bps"] == pytest.approx(20.0)
    assert verdict["executable"] is False  # 10 < 500 minimum
    assert "latency" in " ".join(verdict["missing"])


def test_xex_insufficient_quotes_stay_inconclusive():
    assert dis.evaluate_sufficiency([], ["leg"])["verdict"] == "INCONCLUSIVE"
    assert dis.evaluate_sufficiency([], [])["reasons"] != []


def test_no_llm_in_cycle2_code():
    import pathlib as _pathlib

    for name in ("funding_carry.py", "gate_run.py"):
        lines = (_pathlib.Path(__file__).resolve().parent.parent / "research" / name).read_text(
            encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                lowered = stripped.lower()
                assert "llm" not in lowered, name
                assert "openai" not in lowered, name
                assert "anthropic" not in lowered, name
