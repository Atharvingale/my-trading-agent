"""Module 12 enforcement: every level has coverage, every module has a level.

This file makes the testing-strategy rule executable: if coverage for any
spec level is deleted, or a module loses its mapped level, this test fails.
It imports nothing under test — it audits the suite itself.
"""

from __future__ import annotations

import pathlib


# Spec level → test files proving it (relative to tests/).
LEVEL_COVERAGE: dict[str, tuple[str, ...]] = {
    "edge_validation": (
        "test_edge_validation.py",
        "test_funding_xex_validation.py",
        "test_gate_run.py",
        "test_acquisition.py",
        "test_research_cycle2.py",
    ),
    "unit": (
        "test_risk_engine.py",
        "test_strategy_layer.py",
        "test_lifecycle.py",
        "test_features.py",
        "test_paper_trading.py",
    ),
    "contract": (
        "test_execution_boundary.py",
        "test_api.py",
        "test_decision_engine.py",
    ),
    "integration": (
        "test_soak.py",
        "test_lifecycle.py",
        "test_observer_context.py",
        "test_runtime_integration.py",
    ),
    "execution_integration": (
        "test_venue_integration.py",
        "test_paper_trading.py",
    ),
    "lifecycle": ("test_lifecycle.py",),
    "reconciliation": (
        "test_lifecycle.py",
        "test_memory_model.py",
        "test_execution_boundary.py",
    ),
    "learning": (
        "test_learning.py",
        "test_candidate_generation.py",
    ),
    "soak": (
        "test_soak.py",
        "test_market_data_hardening.py",
    ),
    "failure_injection": (
        "test_failure_injection.py",
        "test_supervisor.py",
    ),
    "backtest_validation": ("test_backtest_validation.py",),
}

# Module → levels relevant to its acceptance bar.
MODULE_LEVELS: dict[str, tuple[str, ...]] = {
    "01": ("edge_validation", "backtest_validation"),
    "02": ("unit", "contract", "soak"),
    "03": ("unit", "contract", "integration"),
    "04": ("unit",),
    "05": ("unit", "contract", "integration"),
    "06": ("unit",),
    "07": ("unit", "contract", "execution_integration", "failure_injection"),
    "08": ("unit", "lifecycle", "reconciliation", "integration"),
    "09": ("unit", "learning"),
    "10": ("unit", "reconciliation"),
    "11": ("unit", "integration", "failure_injection", "soak"),
    "15": ("unit", "learning"),
}


def test_all_levels_have_covering_files():
    root = pathlib.Path(__file__).resolve().parent
    expected_levels = (
        "edge_validation",
        "unit",
        "contract",
        "integration",
        "execution_integration",
        "lifecycle",
        "reconciliation",
        "learning",
        "soak",
        "failure_injection",
        "backtest_validation",
    )
    for level in expected_levels:
        assert level in LEVEL_COVERAGE, "level missing from registry: %s" % level
    for level in LEVEL_COVERAGE:
        assert len(LEVEL_COVERAGE[level]) > 0, "level has no covering file: %s" % level
        for filename in LEVEL_COVERAGE[level]:
            assert (root / filename).exists(), "covering file missing for %s: %s" % (level, filename)


def test_every_module_has_a_mapped_level():
    for module in ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "15"):
        assert module in MODULE_LEVELS, "module missing from matrix: %s" % module
        assert len(MODULE_LEVELS[module]) > 0, "module has no level: %s" % module
        for level in MODULE_LEVELS[module]:
            assert level in LEVEL_COVERAGE, "module %s maps to unknown level %s" % (module, level)
