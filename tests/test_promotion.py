"""Module 1/4 promotion boundary: PASS + human approval + immutable version.

Covers the revised 01-edge-validation-gate.md and 04-strategy-layer.md
acceptance criteria without touching existing Module 4 tests.
"""

from __future__ import annotations

from datetime import date

import pytest

from candidate_generation.review_queue import ReviewQueue
from edge_validation.acceptance_criteria import CRITERION_IDS, AcceptanceCriteria
from edge_validation.evidence import ExperimentEvidence
from edge_validation.registry import EdgeValidationRegistry, StrategyNotGatedError
from strategies.production_versions import ProductionVersionStore
from strategies.promotion import promote_candidate
from strategies.registry import load_production_strategy, load_strategy


def make_registry(tmp_path):
    return EdgeValidationRegistry(
        tmp_path / "edge_validation.sqlite3",
        tmp_path / "EXPERIMENT_REGISTRY.md",
    )


def make_queues(tmp_path):
    reviews = ReviewQueue(tmp_path / "reviews.sqlite3")
    versions = ProductionVersionStore(tmp_path / "versions.sqlite3")
    return reviews, versions


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


def passing_record(registry, strategy_id="funding_carry_v1", **provenance):
    record_id = registry.submit_hypothesis(
        strategy_id=strategy_id,
        hypothesis="Provenance-carrying hypothesis for %s" % strategy_id,
        pre_registered_criteria={"net_return_minimum": 0.0},
        holdout_period=(date(2025, 1, 1), date(2025, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
        **provenance,
    )
    evidence = ExperimentEvidence(
        dataset_id="holdout-%s" % strategy_id,
        dataset_sha256="a" * 64,
        trade_returns=(0.02, 0.015, 0.025, 0.03),
        regime_returns={"trending": 0.02, "range_bound": 0.01},
        net_of_costs_and_tax=True,
        bootstrap_seed=7,
        bootstrap_samples=1000,
    )
    registry.record_result(
        record_id,
        bootstrap_ci=evidence.bootstrap_ci,
        regime_results=evidence.regime_returns,
        criteria=passed_criteria(),
        verdict="PASS",
        evidence=evidence,
    )
    return record_id


def test_module15_hypothesis_submits_like_human_and_retains_provenance(tmp_path):
    registry = make_registry(tmp_path)
    record_id = passing_record(
        registry,
        candidate_id="cand-001",
        parent_candidate_id="cand-000",
        hypothesis_id="hyp-001",
        signal_class="funding-rate carry",
        source="AI_RESEARCH",
        provider_used="mock-provider",
        multiple_testing_family="carry",
        multiple_testing_threshold=0.025,
    )
    provenance = registry.get_provenance(record_id)
    assert provenance["candidate_id"] == "cand-001"
    assert provenance["parent_candidate_id"] == "cand-000"
    assert provenance["source"] == "AI_RESEARCH"
    assert provenance["signal_class"] == "funding-rate carry"
    assert provenance["multiple_testing_threshold"] == pytest.approx(0.025)
    lineage = registry.trace_candidate("cand-001")
    found = False
    for member in lineage:
        if member.record_id == record_id:
            found = True
    assert found is True
    report = registry.report_path.read_text(encoding="utf-8")
    assert "cand-001" in report
    assert "AI_RESEARCH" in report


def test_failed_holdout_cannot_be_silently_retried(tmp_path):
    registry = make_registry(tmp_path)
    kwargs = {
        "strategy_id": "funding_carry_retry",
        "hypothesis": "First attempt",
        "pre_registered_criteria": {"minimum": 1},
        "holdout_period": (date(2025, 1, 1), date(2025, 3, 31)),
        "cost_and_tax_assumptions": assumptions(),
        "source": "AI_RESEARCH",
    }
    registry.submit_hypothesis(**kwargs)
    with pytest.raises(ValueError, match="holdout period overlaps"):
        registry.submit_hypothesis(
            **{**kwargs, "hypothesis": "Silent retry of same holdout"}
        )


def test_unapproved_candidate_cannot_be_loaded(tmp_path):
    registry = make_registry(tmp_path)
    reviews, versions = make_queues(tmp_path)
    record_id = passing_record(registry, strategy_id="unapproved_v1")
    # Low-level PASS check still sees the PASS (existing behavior preserved).
    assert load_strategy("unapproved_v1", registry).edge_validation_record_id == record_id
    # Production loader refuses without an approved immutable version.
    with pytest.raises(StrategyNotGatedError):
        load_production_strategy("unapproved_v1", registry, versions)
    reviews.close()
    versions.close()


def test_pass_without_human_approval_cannot_be_loaded(tmp_path):
    registry = make_registry(tmp_path)
    reviews, versions = make_queues(tmp_path)
    record_id = passing_record(registry, strategy_id="no_approval_v1")
    reviews.submit_for_review(record_id, "no_approval_v1", "PASS", source="AI_RESEARCH")
    assert reviews.is_approved(record_id) is False
    with pytest.raises(StrategyNotGatedError, match="no explicit human approval"):
        promote_candidate(
            strategy_id="no_approval_v1",
            edge_validation_record_id=record_id,
            registry=registry,
            reviews=reviews,
            versions=versions,
            approver="atharva",
            rationale="should still fail without review approval",
        )
    with pytest.raises(StrategyNotGatedError):
        load_production_strategy("no_approval_v1", registry, versions)
    reviews.close()
    versions.close()


def test_approved_immutable_version_can_be_loaded(tmp_path):
    registry = make_registry(tmp_path)
    reviews, versions = make_queues(tmp_path)
    record_id = passing_record(
        registry, strategy_id="approved_carry_v1", candidate_id="cand-9", source="AI_RESEARCH"
    )
    reviews.submit_for_review(record_id, "approved_carry_v1", "PASS", source="AI_RESEARCH")
    reviews.approve(record_id, "atharva", "funding class is new, evidence reviewed")
    produced = promote_candidate(
        strategy_id="approved_carry_v1",
        edge_validation_record_id=record_id,
        registry=registry,
        reviews=reviews,
        versions=versions,
        approver="atharva",
        rationale="human sign-off recorded",
    )
    assert produced.edge_validation_record_id == record_id
    loaded = load_production_strategy("approved_carry_v1", registry, versions)
    assert loaded.edge_validation_record_id == record_id
    assert loaded.strategy_id == "approved_carry_v1"
    reviews.close()
    versions.close()


def test_no_llm_in_proposal_path():
    import pathlib as _pathlib

    root = _pathlib.Path(__file__).resolve().parent.parent / "strategies"
    # Proposal path per 04: base, proposal, calibration, registry loaders.
    # promotion.py / production_versions.py are the explicit promotion adapter
    # and may reference the review queue, but never an LLM provider.
    proposal_files = ["base.py", "proposal.py", "calibration.py", "registry.py"]
    for name in proposal_files:
        path = root / name
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                lowered = stripped.lower()
                assert "candidate_generation" not in lowered, str(path)
                assert "openai" not in lowered, str(path)
                assert "anthropic" not in lowered, str(path)
                if "llm" in lowered:
                    raise AssertionError(f"{path.name} imports llm: {line.strip()}")
    adapter_files = ["promotion.py", "production_versions.py"]
    for name in adapter_files:
        path = root / name
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                lowered = stripped.lower()
                assert "openai" not in lowered, str(path)
                assert "anthropic" not in lowered, str(path)
                if "llm" in lowered:
                    raise AssertionError(f"{path.name} imports llm: {line.strip()}")
