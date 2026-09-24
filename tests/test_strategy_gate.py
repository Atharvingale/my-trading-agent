from datetime import date

import pytest

from edge_validation.registry import EdgeValidationRegistry, StrategyNotGatedError
from strategies.registry import load_strategy


def make_registry(tmp_path):
    return EdgeValidationRegistry(
        tmp_path / "edge_validation.sqlite3",
        tmp_path / "EXPERIMENT_REGISTRY.md",
    )


def test_module_4_cannot_load_strategy_without_registry_entry(tmp_path):
    registry = make_registry(tmp_path)

    with pytest.raises(StrategyNotGatedError):
        load_strategy("trend_following", registry)


def test_module_4_cannot_load_falsified_breakout_or_scalping(tmp_path):
    registry = make_registry(tmp_path)

    with pytest.raises(StrategyNotGatedError):
        load_strategy("breakout", registry)
    with pytest.raises(StrategyNotGatedError):
        load_strategy("scalping", registry)


def test_module_4_cannot_load_failed_candidate(tmp_path):
    registry = make_registry(tmp_path)
    record_id = registry.submit_hypothesis(
        strategy_id="mean_reversion",
        hypothesis="Failed candidate stays blocked",
        pre_registered_criteria={"minimum": 1},
        holdout_period=(date(2024, 1, 1), date(2024, 3, 31)),
        cost_and_tax_assumptions={
            "fee_rate": 0.001,
            "slippage_rate": 0.001,
            "tax_rate": 0.312,
            "tds_rate": 0.01,
            "loss_offset_allowed": False,
            "tds_is_cash_flow_drag": True,
        },
    )
    from edge_validation.acceptance_criteria import CRITERION_IDS, AcceptanceCriteria

    checks = {}
    for criterion_id in CRITERION_IDS:
        checks[criterion_id] = False
    registry.record_result(
        record_id,
        bootstrap_ci=(-0.2, -0.01),
        regime_results={"trending": -0.1, "range_bound": -0.05},
        criteria=AcceptanceCriteria(checks),
        verdict="FAIL",
    )

    with pytest.raises(StrategyNotGatedError):
        load_strategy("mean_reversion", registry)
