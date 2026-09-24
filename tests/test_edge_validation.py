from datetime import date
import sqlite3

import pytest

from edge_validation.acceptance_criteria import CRITERION_IDS, AcceptanceCriteria
from edge_validation.evidence import ExperimentEvidence
from edge_validation.experiment import (
    Candle,
    backtest_mean_reversion,
    backtest_order_flow,
    backtest_trend_following,
    backtest_vwap_reversion,
    evaluate_acceptance,
)
from edge_validation.registry import EdgeValidationRegistry, StrategyNotGatedError
from edge_validation.replication_check import check_replication


def make_registry(tmp_path):
    return EdgeValidationRegistry(
        tmp_path / "edge_validation.sqlite3",
        tmp_path / "EXPERIMENT_REGISTRY.md",
    )


def assumptions():
    return {
        "fee_rate": 0.001,
        "slippage_rate": 0.001,
        "tax_rate": 0.312,
        "tds_rate": 0.01,
        "loss_offset_allowed": False,
        "tds_is_cash_flow_drag": True,
    }


def passed_criteria():
    checks = {}
    for criterion_id in CRITERION_IDS:
        checks[criterion_id] = True
    return AcceptanceCriteria(checks)


def failed_criteria():
    checks = {}
    for criterion_id in CRITERION_IDS:
        checks[criterion_id] = False
    return AcceptanceCriteria(checks)


def test_unregistered_strategy_cannot_pass_gate(tmp_path):
    registry = make_registry(tmp_path)

    assert registry.get_verdict("trend_following") == "NOT_TESTED"
    with pytest.raises(StrategyNotGatedError):
        registry.require_pass("trend_following")


def test_falsified_strategy_families_are_seeded_as_fail(tmp_path):
    registry = make_registry(tmp_path)

    assert registry.get_verdict("Breakout") == "FAIL"
    assert registry.get_verdict("breakout_24_12_14_hourly") == "FAIL"
    assert registry.get_verdict("Scalping") == "FAIL"


def test_falsified_family_cannot_be_hidden_behind_an_alternate_family_name(tmp_path):
    registry = make_registry(tmp_path)

    with pytest.raises(ValueError, match="cannot be reclassified"):
        registry.submit_hypothesis(
            strategy_id="breakout_24_12_14_hourly",
            strategy_family="trend_following",
            hypothesis="Try to bypass the falsified family gate",
            pre_registered_criteria={"minimum": 1},
            holdout_period=(date(2024, 1, 1), date(2024, 3, 31)),
            cost_and_tax_assumptions=assumptions(),
        )


def test_custom_strategy_cannot_claim_another_strategy_family(tmp_path):
    registry = make_registry(tmp_path)

    with pytest.raises(ValueError, match="cannot be reclassified"):
        registry.submit_hypothesis(
            strategy_id="unapproved_strategy",
            strategy_family="trend_following",
            hypothesis="Attempt to inherit another strategy's gate",
            pre_registered_criteria={"minimum": 1},
            holdout_period=(date(2024, 1, 1), date(2024, 3, 31)),
            cost_and_tax_assumptions=assumptions(),
        )


def test_pending_new_attempt_keeps_strategy_blocked_after_prior_failure(tmp_path):
    registry = make_registry(tmp_path)
    first_id = registry.submit_hypothesis(
        strategy_id="trend_following",
        hypothesis="First disjoint validation",
        pre_registered_criteria={"net_return_minimum": 0.0},
        holdout_period=(date(2024, 1, 1), date(2024, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )
    registry.record_result(
        first_id,
        bootstrap_ci=(-0.12, -0.01),
        regime_results={"trending": -0.08, "range_bound": -0.02},
        criteria=failed_criteria(),
        verdict="FAIL",
    )
    registry.submit_hypothesis(
        strategy_id="trend_following",
        hypothesis="Second untouched validation",
        pre_registered_criteria={"net_return_minimum": 0.0},
        holdout_period=(date(2024, 4, 1), date(2024, 6, 30)),
        cost_and_tax_assumptions=assumptions(),
    )

    assert registry.get_verdict("trend_following") == "PENDING"
    with pytest.raises(StrategyNotGatedError):
        registry.require_pass("trend_following")


def test_realistic_cost_assumptions_cannot_be_negligible(tmp_path):
    invalid = assumptions()
    invalid["fee_rate"] = 0.0001

    with pytest.raises(ValueError, match="at least 0.10%"):
        make_registry(tmp_path).submit_hypothesis(
            strategy_id="trend_following",
            hypothesis="Sub-realistic fee assumption",
            pre_registered_criteria={"minimum": 1},
            holdout_period=(date(2024, 1, 1), date(2024, 3, 31)),
            cost_and_tax_assumptions=invalid,
        )


def test_hypothesis_is_preregistered_and_unverified_pass_is_blocked(tmp_path):
    registry = make_registry(tmp_path)
    record_id = registry.submit_hypothesis(
        strategy_id="trend_following",
        hypothesis="Fixed trend filter produces positive net return in untouched period",
        pre_registered_criteria={"net_return_minimum": 0.0},
        holdout_period=(date(2024, 1, 1), date(2024, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )
    with pytest.raises(ValueError, match="independently verified experiment evidence"):
        registry.record_result(
            record_id,
            bootstrap_ci=(0.01, 0.12),
            regime_results={"trending": 0.08, "range_bound": 0.02},
            criteria=passed_criteria(),
            verdict="PASS",
        )

    assert registry.get_verdict("trend_following") == "PENDING"
    with pytest.raises(StrategyNotGatedError):
        registry.require_pass("trend_following")


def test_holdout_overlap_and_duplicate_hypothesis_are_rejected(tmp_path):
    registry = make_registry(tmp_path)
    kwargs = {
        "strategy_id": "mean_reversion",
        "hypothesis": "A preregistered hypothesis",
        "pre_registered_criteria": {"minimum": 1},
        "holdout_period": (date(2024, 1, 1), date(2024, 3, 31)),
        "cost_and_tax_assumptions": assumptions(),
    }
    registry.submit_hypothesis(**kwargs)

    with pytest.raises(ValueError, match="holdout period overlaps"):
        registry.submit_hypothesis(**kwargs)
    with pytest.raises(ValueError, match="holdout period overlaps"):
        registry.submit_hypothesis(
            **{**kwargs, "hypothesis": "Different hypothesis, same used period"}
        )


def test_criteria_and_cost_tax_assumptions_are_validated(tmp_path):
    registry = make_registry(tmp_path)
    record_id = registry.submit_hypothesis(
        strategy_id="vwap_reversion",
        hypothesis="Test VWAP reversion",
        pre_registered_criteria={"minimum": 1},
        holdout_period=(date(2024, 1, 1), date(2024, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )

    with pytest.raises(ValueError, match="all seven"):
        AcceptanceCriteria({"criterion_1": True})
    with pytest.raises(ValueError, match="positive bootstrap confidence interval"):
        registry.record_result(
            record_id,
            bootstrap_ci=(-0.1, 0.2),
            regime_results={"trending": 0.1, "range_bound": 0.05},
            criteria=passed_criteria(),
            verdict="PASS",
        )
    bad_assumptions = assumptions()
    bad_assumptions["loss_offset_allowed"] = True
    with pytest.raises(ValueError, match="loss_offset_allowed"):
        registry.submit_hypothesis(
            strategy_id="order_flow",
            hypothesis="No loss offset",
            pre_registered_criteria={"minimum": 1},
            holdout_period=(date(2024, 4, 1), date(2024, 6, 30)),
            cost_and_tax_assumptions=bad_assumptions,
        )


def test_null_result_is_recorded_and_does_not_gate_strategy(tmp_path):
    registry = make_registry(tmp_path)
    record_id = registry.submit_hypothesis(
        strategy_id="order_flow",
        hypothesis="Null is final",
        pre_registered_criteria={"minimum": 1},
        holdout_period=(date(2024, 1, 1), date(2024, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )
    registry.record_result(
        record_id,
        bootstrap_ci=(-0.02, 0.03),
        regime_results={"trending": 0.01, "range_bound": -0.01},
        criteria=failed_criteria(),
        verdict="NULL_RESULT",
    )

    assert registry.get_verdict("order_flow") == "NULL_RESULT"
    with pytest.raises(StrategyNotGatedError):
        registry.require_pass("order_flow")


def test_records_are_append_only_at_repository_and_sqlite_layers(tmp_path):
    registry = make_registry(tmp_path)
    record_id = registry.submit_hypothesis(
        strategy_id="trend_following",
        hypothesis="Append-only record",
        pre_registered_criteria={"minimum": 1},
        holdout_period=(date(2024, 1, 1), date(2024, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )

    with pytest.raises(ValueError, match="append-only"):
        registry.delete_record(record_id)
    with pytest.raises(sqlite3.IntegrityError):
        registry.connection.execute(
            "UPDATE edge_validation_records SET verdict = 'PASS' WHERE record_id = ?",
            (record_id,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        registry.connection.execute(
            "DELETE FROM edge_validation_records WHERE record_id = ?", (record_id,)
        )


def test_replication_requires_disjoint_periods_and_positive_improvement():
    result = check_replication(
        primary_period=(date(2024, 1, 1), date(2024, 3, 31)),
        replication_period=(date(2024, 4, 1), date(2024, 6, 30)),
        primary_net_return=0.08,
        replication_net_return=0.04,
        baseline_replication_net_return=0.01,
    )

    assert result.passed is True
    assert result.improvement_over_baseline == pytest.approx(0.03)
    with pytest.raises(ValueError, match="disjoint"):
        check_replication(
            primary_period=(date(2024, 1, 1), date(2024, 3, 31)),
            replication_period=(date(2024, 3, 31), date(2024, 6, 30)),
            primary_net_return=0.08,
            replication_net_return=0.04,
        )


def test_replication_does_not_pass_without_positive_net_return():
    result = check_replication(
        primary_period=(date(2024, 1, 1), date(2024, 3, 31)),
        replication_period=(date(2024, 4, 1), date(2024, 6, 30)),
        primary_net_return=0.08,
        replication_net_return=-0.01,
    )

    assert result.passed is False


def test_report_preregistration_precedes_result_and_attempt_cannot_be_retried(tmp_path):
    report_path = tmp_path / "EXPERIMENT_REGISTRY.md"
    registry = make_registry(tmp_path)
    record_id = registry.submit_hypothesis(
        strategy_id="trend_following",
        hypothesis="Preregister before result",
        pre_registered_criteria={"minimum": 1},
        holdout_period=(date(2024, 1, 1), date(2024, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )
    registry.record_result(
        record_id,
        bootstrap_ci=(-0.01, 0.02),
        regime_results={"trending": 0.01, "range_bound": -0.005},
        criteria=failed_criteria(),
        verdict="NULL_RESULT",
    )
    report = report_path.read_text(encoding="utf-8")

    assert report.index("Preregistered hypothesis") < report.index("## Result")
    with pytest.raises(ValueError, match="already recorded"):
        registry.record_result(
            record_id,
            bootstrap_ci=(0.01, 0.02),
            regime_results={"trending": 0.01, "range_bound": 0.02},
            criteria=passed_criteria(),
            verdict="PASS",
        )


def test_computed_evidence_can_open_gate_and_is_persisted(tmp_path):
    registry = make_registry(tmp_path)
    record_id = registry.submit_hypothesis(
        strategy_id="trend_following",
        hypothesis="Computed evidence opens the gate",
        pre_registered_criteria={"net_return_minimum": 0.0},
        holdout_period=(date(2025, 1, 1), date(2025, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )
    evidence = ExperimentEvidence(
        dataset_id="holdout-2025-q1",
        dataset_sha256="a" * 64,
        trade_returns=(0.01, 0.02, 0.015, 0.025),
        regime_returns={"trending": 0.02, "range_bound": 0.01},
        net_of_costs_and_tax=True,
        bootstrap_seed=7,
        bootstrap_samples=1000,
    )
    result = registry.record_result(
        record_id,
        bootstrap_ci=evidence.bootstrap_ci,
        regime_results=evidence.regime_returns,
        criteria=passed_criteria(),
        verdict="PASS",
        evidence=evidence,
    )

    assert result.verdict == "PASS"
    assert registry.get_verdict("trend_following") == "PASS"
    assert registry.require_pass("trend_following").record_id == record_id
    assert evidence.fingerprint() in registry.report_path.read_text(encoding="utf-8")


def test_pass_rejects_caller_supplied_results_that_do_not_match_evidence(tmp_path):
    registry = make_registry(tmp_path)
    record_id = registry.submit_hypothesis(
        strategy_id="vwap_reversion",
        hypothesis="Evidence values are independently computed",
        pre_registered_criteria={"net_return_minimum": 0.0},
        holdout_period=(date(2025, 4, 1), date(2025, 6, 30)),
        cost_and_tax_assumptions=assumptions(),
    )
    evidence = ExperimentEvidence(
        dataset_id="holdout-2025-q2",
        dataset_sha256="b" * 64,
        trade_returns=(0.01, 0.02, 0.015),
        regime_returns={"trending": 0.015, "range_bound": 0.01},
        net_of_costs_and_tax=True,
        bootstrap_samples=1000,
    )

    with pytest.raises(ValueError, match="match the computed evidence"):
        registry.record_result(
            record_id,
            bootstrap_ci=(0.001, 0.02),
            regime_results=evidence.regime_returns,
            criteria=passed_criteria(),
            verdict="PASS",
            evidence=evidence,
        )


def test_evidence_requires_provenance_and_net_cost_treatment():
    with pytest.raises(ValueError, match="SHA-256"):
        ExperimentEvidence(
            dataset_id="holdout",
            dataset_sha256="not-a-hash",
            trade_returns=(0.01,),
            regime_returns={"trend": 0.01, "range": 0.01},
            net_of_costs_and_tax=True,
        )
    with pytest.raises(ValueError, match="net of costs"):
        ExperimentEvidence(
            dataset_id="holdout",
            dataset_sha256="c" * 64,
            trade_returns=(0.01,),
            regime_returns={"trend": 0.01, "range": 0.01},
            net_of_costs_and_tax=False,
        )


def test_trend_following_backtest_applies_costs_tax_and_stop_before_signal():
    candles = tuple(
        Candle(timestamp=index, open=price, high=price + 1, low=price - 1, close=price)
        for index, price in enumerate((100, 100, 100, 110, 108, 90, 91))
    )
    result = backtest_trend_following(
        candles, fee_rate=0.001, slippage_rate=0.001, fast_period=2, slow_period=3
    )

    assert result.trades
    assert result.trades[0].exit_reason == "STOP_LOSS"
    assert result.trades[0].tax == 0.0
    assert result.trades[0].tds > 0.0
    assert result.net_return < result.gross_return


def test_mean_reversion_backtest_applies_costs_tax_and_stop_before_signal():
    candles = tuple(
        Candle(timestamp=index, open=price, high=price + 2, low=price - 2, close=price)
        for index, price in enumerate((100, 100, 100, 92, 93, 80, 81))
    )
    result = backtest_mean_reversion(
        candles, fee_rate=0.001, slippage_rate=0.001, lookback=3, zscore=1.0
    )

    assert result.trades
    assert result.trades[0].exit_reason == "STOP_LOSS"
    assert result.trades[0].tds > 0.0
    assert result.net_return < result.gross_return


def test_vwap_reversion_backtest_applies_costs_tax_and_stop_before_signal():
    candles = tuple(
        Candle(
            timestamp=index,
            open=price,
            high=price + 2,
            low=price - 2,
            close=price,
            volume=10.0,
        )
        for index, price in enumerate((100, 100, 100, 90, 91, 70, 71))
    )
    result = backtest_vwap_reversion(
        candles, fee_rate=0.001, slippage_rate=0.001, lookback=3, deviation=0.02
    )

    assert result.trades
    assert result.trades[0].exit_reason == "STOP_LOSS"
    assert result.trades[0].tds > 0.0
    assert result.net_return < result.gross_return


def test_order_flow_backtest_applies_costs_tax_and_stop_before_signal():
    candles = tuple(
        Candle(
            timestamp=index,
            open=price,
            high=price + 1,
            low=price - 1,
            close=price,
            volume=volume,
        )
        for index, (price, volume) in enumerate(
            ((100, 1), (101, 1), (102, 1), (110, 20), (111, 1), (90, 1), (91, 1))
        )
    )
    result = backtest_order_flow(
        candles, fee_rate=0.001, slippage_rate=0.001, lookback=3, volume_multiple=2.0
    )

    assert result.trades
    assert result.trades[0].exit_reason == "STOP_LOSS"
    assert result.trades[0].tds > 0.0
    assert result.net_return < result.gross_return


def test_acceptance_evaluation_requires_all_four_windows_and_cost_stress():
    result = evaluate_acceptance(
        window_returns=(0.02, 0.01, -0.01, 0.015),
        aggregate_return=0.035,
        bootstrap_ci=(0.005, 0.06),
        risk_free_return=0.0,
        stress_return=0.004,
        trade_count=80,
    )

    assert result.passed is False
    assert "three_of_four_windows" not in result.failed_criteria
    assert "stress_costs" not in result.failed_criteria


def test_report_is_rebuilt_from_database_after_it_is_lost(tmp_path):
    report_path = tmp_path / "EXPERIMENT_REGISTRY.md"
    registry = make_registry(tmp_path)
    record_id = registry.submit_hypothesis(
        strategy_id="trend_following",
        hypothesis="Recoverable preregistration",
        pre_registered_criteria={"minimum": 1},
        holdout_period=(date(2024, 1, 1), date(2024, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )
    registry.record_result(
        record_id,
        bootstrap_ci=(-0.01, 0.02),
        regime_results={"trending": 0.01, "range_bound": -0.005},
        criteria=failed_criteria(),
        verdict="NULL_RESULT",
    )
    registry.close()
    report_path.unlink()

    recovered_registry = EdgeValidationRegistry(
        tmp_path / "edge_validation.sqlite3", report_path
    )
    report = report_path.read_text(encoding="utf-8")

    assert f"Record ID: `{record_id}`" in report
    assert f"Preregistration record ID: `{record_id}`" in report
    assert recovered_registry.get_verdict("trend_following") == "NULL_RESULT"
