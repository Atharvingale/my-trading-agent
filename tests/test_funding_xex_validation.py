"""Module 1 research validation: funding carry + dislocation INCONCLUSIVE track."""

from __future__ import annotations

import pytest

from candidate_generation import multiple_testing
from candidate_generation.generator import CandidateGenerator
from candidate_generation.hypothesis_menu import HypothesisMenu
from research import dislocation as dis
from research import funding_carry as fund


def funding_series(n=12, rate=0.0002, mark=100.0, last_spike=None):
    observations: list[fund.FundingObservation] = []
    index = 0
    while index < n:
        current_rate = rate
        current_mark = mark + float(index)
        if last_spike is not None and index == n - 1:
            current_rate = last_spike
            current_mark = mark + 500.0
        observations.append(fund.FundingObservation(
            symbol="BTCUSDT", funding_time_ms=1_000_000 + index * 28_800_000,
            rate=current_rate, mark_price=current_mark,
        ))
        index = index + 1
    return observations


def xex_series(n=10, disagreement=3.0, last_spike=None):
    observations: list[dis.DislocationObservation] = []
    index = 0
    while index < n:
        current = disagreement
        if last_spike is not None and index == n - 1:
            current = last_spike
        observations.append(dis.DislocationObservation(
            symbol="BTCUSDT", timestamp_ms=2_000_000 + index * 60_000,
            reference_price=85000.0, disagreement_bps=current,
            source_count=4, status="CONFIRMED",
        ))
        index = index + 1
    return observations


# -- registration through the existing framework --
def test_both_signal_classes_are_menu_approved(tmp_path):
    menu = HypothesisMenu(str(tmp_path / "menu.sqlite3"))
    try:
        assert menu.is_allowed("funding-rate carry") is True
        assert menu.is_allowed("cross-exchange dislocation") is True
        assert menu.require_allowed("funding-rate carry") == "funding-rate carry"
    finally:
        menu.close()


def test_bounded_hypothesis_sets_are_registered(tmp_path):
    assert len(fund.FUNDING_HYPOTHESES) == 3
    assert len(dis.DISLOCATION_HYPOTHESES) == 3
    menu = HypothesisMenu()
    generator = CandidateGenerator(str(tmp_path / "cand.sqlite3"), menu=menu, min_interval_seconds=0)
    try:
        count = 0
        for hypothesis in fund.FUNDING_HYPOTHESES:
            assert menu.is_allowed(hypothesis.signal_class) is True
            count = count + 1
        for hypothesis in dis.DISLOCATION_HYPOTHESES:
            assert menu.is_allowed(hypothesis.signal_class) is True
            count = count + 1
        assert count == 6
    finally:
        generator.close()
        menu.close()


# -- funding: determinism, no look-ahead, costs --
def test_funding_trades_are_deterministic():
    first = fund.generate_trades(funding_series(), fund.FUNDING_HYPOTHESES[0])
    second = fund.generate_trades(funding_series(), fund.FUNDING_HYPOTHESES[0])
    assert first == second
    assert fund.dataset_hash(funding_series()) == fund.dataset_hash(funding_series())


def test_funding_future_spike_cannot_trigger_entries():
    # Base rates sit below the F1 threshold; only the final period spikes.
    # Trailing windows for completable entries never see it, so zero trades
    # is the causal result — the future cannot reach back into entries.
    trades = fund.generate_trades(
        funding_series(rate=0.00005, last_spike=0.009), fund.FUNDING_HYPOTHESES[0]
    )
    assert trades == []
    calm = fund.generate_trades(funding_series(), fund.FUNDING_HYPOTHESES[0])
    for trade in calm:
        assert trade["exit_time_ms"] > trade["entry_time_ms"]


def test_funding_direction_and_costs_are_exact():
    assert fund.apply_costs(100.0, 1000.0) == pytest.approx(59.168)
    assert fund.apply_costs(-50.0, 1000.0) == pytest.approx(-64.0)
    trades = fund.generate_trades(funding_series(), fund.FUNDING_HYPOTHESES[0], notional=1000.0)
    assert len(trades) > 0
    for trade in trades:
        assert trade["net_pnl"] < trade["gross_pnl"]
        assert trade["direction"] == "SHORT"


def test_funding_quality_gate_flags_defects():
    good = fund.quality_gate(funding_series(30))
    assert good["ok"] is True
    assert good["duplicates"] == 0
    assert fund.quality_gate([])["ok"] is False
    doubled = funding_series(10) + funding_series(10)
    assert fund.quality_gate(doubled)["duplicates"] > 0
    bad_rate = funding_series(10)
    bad_rate.append(fund.FundingObservation("BTCUSDT", 99_999_999, 0.05, 100.0))
    assert fund.quality_gate(bad_rate)["unrealistic_rates"] == 1
    no_mark = funding_series(10)
    no_mark.append(fund.FundingObservation("BTCUSDT", 99_999_999, 0.0001, 0.0))
    assert fund.quality_gate(no_mark)["missing_marks"] == 1


# -- dislocation: sync, crossings, executability, no look-ahead --
def test_dislocation_crossings_count_past_streaks_only():
    hypothesis = dis.DISLOCATION_HYPOTHESES[0]
    result = dis.describe_crossings(xex_series(10, disagreement=8.0), hypothesis)
    assert result["crossings"] == 1
    # A spike confined to the final observation never completes a streak.
    spike_only = dis.describe_crossings(xex_series(10, disagreement=1.0, last_spike=50.0), hypothesis)
    assert spike_only["crossings"] == 0
    assert dis.describe_crossings(xex_series(10, disagreement=8.0), hypothesis) == result


def test_dislocation_executability_names_missing_legs():
    verdict = dis.check_executability(xex_series(10))
    assert verdict["executable"] is False
    assert len(verdict["missing"]) == 6
    assert verdict["usable_confirmations"] == 10


def test_dislocation_quality_gate():
    good = dis.quality_gate(xex_series(30))
    assert good["ok"] is True
    assert good["unavailable"] == 0
    assert dis.quality_gate([])["ok"] is False
    doubled = xex_series(10) + xex_series(10)
    assert dis.quality_gate(doubled)["duplicates"] > 0
    absurd = xex_series(10)
    absurd.append(dis.DislocationObservation("BTCUSDT", 99_999_999, 85000.0, 900.0, 4, "CONFIRMED"))
    assert dis.quality_gate(absurd)["impossible_spreads"] == 1


def test_loaders_dedup_repolled_rows(tmp_path):
    import json
    import sqlite3

    db = str(tmp_path / "mini.sqlite3")
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE market_events (symbol TEXT, event_time_ms INTEGER, event_type TEXT, payload_json TEXT)")
    funding_payload = json.dumps({"items": [
        {"symbol": "BTCUSDT", "fundingTime": 1000, "fundingRate": "0.0001", "markPrice": "100.0"},
    ]})
    xex_payload = json.dumps({"reference_price": 85000.0, "disagreement_bps": 3.0,
                              "source_count": 4, "confirmation_status": "CONFIRMED"})
    connection.execute("INSERT INTO market_events VALUES (?, ?, ?, ?)",
                       ("BTCUSDT", 1, "futuresFundingRate", funding_payload))
    connection.execute("INSERT INTO market_events VALUES (?, ?, ?, ?)",
                       ("BTCUSDT", 2, "futuresFundingRate", funding_payload))
    connection.execute("INSERT INTO market_events VALUES (?, ?, ?, ?)",
                       ("BTCUSDT", 10, "crossExchangeConfirmation", xex_payload))
    connection.execute("INSERT INTO market_events VALUES (?, ?, ?, ?)",
                       ("BTCUSDT", 10, "crossExchangeConfirmation", xex_payload))
    connection.commit()
    connection.close()
    assert len(fund.load_from_market_db(db)) == 1
    assert len(dis.load_from_market_db(db)) == 1


# -- sufficiency verdicts: READY only with real evidence-grade data --
def test_sufficiency_ready_only_when_data_qualifies():
    observations: list[fund.FundingObservation] = []
    index = 0
    while index < 200:
        observations.append(fund.FundingObservation(
            "BTCUSDT", 1_000_000 + index * 28_800_000, 0.0002, 100.0 + index * 0.1,
        ))
        index = index + 1
    verdict = fund.evaluate_sufficiency(observations, regime_legs=["bull-leg", "bear-leg"])
    assert verdict["verdict"] == "READY"
    assert verdict["hypotheses_tested"] == 0
    thin = fund.evaluate_sufficiency(funding_series(30), regime_legs=["single-leg"])
    assert thin["verdict"] == "INCONCLUSIVE"
    assert thin["hypotheses_tested"] == 0
    xex = dis.evaluate_sufficiency(xex_series(30), regime_legs=["single-leg"])
    assert xex["verdict"] == "INCONCLUSIVE"
    assert len(xex["reasons"]) >= 3


# -- multiple-testing accounting: registered is not tested --
def test_multiple_testing_counts_only_tested():
    assert multiple_testing.required_significance(base_alpha=0.05, total_tested=1) == pytest.approx(0.05)
    assert multiple_testing.required_significance(base_alpha=0.05, total_tested=7) == pytest.approx(0.05 / 7)
    assert multiple_testing.count_hypotheses(database_path="nonexistent-ledger.sqlite3") == 0


def test_research_registration_touches_no_gate_holdout(tmp_path):
    import sqlite3

    ledger = str(tmp_path / "gate.sqlite3")
    connection = sqlite3.connect(ledger)
    connection.execute("CREATE TABLE edge_validation_records (event_type TEXT)")
    connection.commit()
    before = multiple_testing.count_hypotheses(database_path=ledger)
    menu = HypothesisMenu()
    generator = CandidateGenerator(str(tmp_path / "cand.sqlite3"), menu=menu, min_interval_seconds=0)
    try:
        logged = 0
        for candidate in (
            {"signal_class": "funding-rate carry", "rationale": "audit probe",
             "proposed_entry_exit_rules": {"hypothesis": "F1"}},
            {"signal_class": "cross-exchange dislocation", "rationale": "audit probe",
             "proposed_entry_exit_rules": {"hypothesis": "D1"}},
        ):
            hypothesis = generator.generate_from_response(dict(candidate), provider_used="audit")
            assert hypothesis is not None
            assert hypothesis.excluded_because is None
            logged = logged + 1
        assert logged == 2
        assert len(generator.list_logged(status="GENERATED")) == 2
    finally:
        generator.close()
        menu.close()
    connection.close()
    assert multiple_testing.count_hypotheses(database_path=ledger) == before


# -- production stays blocked --
def test_production_blocked_without_pass(tmp_path):
    from edge_validation.registry import EdgeValidationRegistry, StrategyNotGatedError
    from strategies.registry import load_strategy

    registry = EdgeValidationRegistry(tmp_path / "edge.sqlite3", tmp_path / "R.md")
    try:
        with pytest.raises(StrategyNotGatedError):
            load_strategy("funding_carry_v1", registry)
        with pytest.raises(StrategyNotGatedError):
            registry.require_pass("xex_dislocation_v1")
    finally:
        registry.close()


def test_no_llm_or_gate_writes_in_research():
    import pathlib as _pathlib

    root = _pathlib.Path(__file__).resolve().parent.parent / "research"
    for name in ("funding_carry.py", "dislocation.py", "run_validation.py"):
        lines = (root / name).read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                lowered = stripped.lower()
                assert "llm" not in lowered, name
                assert "openai" not in lowered, name
                assert "anthropic" not in lowered, name
