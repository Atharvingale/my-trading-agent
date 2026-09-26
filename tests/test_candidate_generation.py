"""Module 15 acceptance: menu gate, stricter bar, approval, providers, malformed."""

from __future__ import annotations

import json
import os
import pathlib
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from candidate_generation.generator import CandidateGenerator
from candidate_generation.hypothesis_menu import HypothesisMenu
from candidate_generation import multiple_testing
from candidate_generation.provider_client import propose_from_env, propose_hypothesis
from candidate_generation.review_queue import ReviewQueue
from edge_validation.acceptance_criteria import CRITERION_IDS, AcceptanceCriteria
from edge_validation.evidence import ExperimentEvidence
from edge_validation.registry import EdgeValidationRegistry, StrategyNotGatedError
from strategies.production_versions import ProductionVersionStore
from strategies.promotion import promote_candidate


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


def good_response(signal_class="funding-rate carry"):
    return {
        "signal_class": signal_class,
        "rationale": "Structurally different from price-action: earns carry while hedged.",
        "proposed_entry_exit_rules": {"enter": "funding > threshold", "exit": "funding < 0"},
    }


# -- 1. excluded signal class rejected before the gate --
def test_excluded_breakout_variant_rejected_before_gate(tmp_path):
    menu = HypothesisMenu()
    verdict = menu.check("Breakout 24/12/14 hourly")
    assert verdict["allowed"] is False
    assert "FALSIFIED" in str(verdict["excluded_because"])
    with pytest.raises(ValueError, match="FALSIFIED"):
        menu.require_allowed("breakout")
    generator = CandidateGenerator(tmp_path / "candidates.sqlite3", menu=menu, min_interval_seconds=0)
    hypothesis = generator.generate_from_response(
        good_response("Breakout"), provider_used="mock:unit"
    )
    assert hypothesis is not None
    assert hypothesis.excluded_because is not None
    registry = make_registry(tmp_path)
    with pytest.raises(ValueError, match="excluded candidate"):
        generator.preregister(
            hypothesis,
            registry,
            holdout_period=(date(2025, 1, 1), date(2025, 3, 31)),
            cost_and_tax_assumptions=assumptions(),
            strategy_id="breakout_repackaged_v1",
        )
    assert registry.list_records() == []
    logged = generator.list_logged(status="EXCLUDED")
    assert len(logged) == 1
    generator.close()
    registry.close()
    menu.close()


def test_new_signal_class_needs_human_signoff(tmp_path):
    menu = HypothesisMenu(tmp_path / "menu.sqlite3")
    assert menu.is_allowed("volatility carry") is False
    with pytest.raises(ValueError, match="approver"):
        menu.add_with_approval("volatility carry", "", "some reason")
    with pytest.raises(ValueError, match="rationale"):
        menu.add_with_approval("volatility carry", "atharva", "")
    menu.add_with_approval("volatility carry", "atharva", "new class, fresh holdout approved")
    assert menu.is_allowed("volatility carry") is True
    assert menu.require_allowed("volatility carry") == "volatility carry"
    with pytest.raises(ValueError, match="excluded"):
        menu.add_with_approval("breakout", "atharva", "trying to re-admit")
    menu.close()


# -- 2. multiple-testing bar stricter after 10 than after 1 --
def test_multiple_testing_stricter_after_ten_than_after_one():
    first = multiple_testing.required_significance(base_alpha=0.05, total_tested=1)
    tenth = multiple_testing.required_significance(base_alpha=0.05, total_tested=10)
    assert first == pytest.approx(0.05)
    assert tenth == pytest.approx(0.005)
    assert tenth < first


def test_adjusted_threshold_reads_live_ledger(tmp_path):
    registry = make_registry(tmp_path)
    empty = multiple_testing.adjusted_threshold(registry=registry)
    assert empty["total_tested_including_current"] == 1
    assert empty["method"] == "bonferroni"
    record_id = registry.submit_hypothesis(
        strategy_id="probe_v1",
        hypothesis="Seed one attempt",
        pre_registered_criteria={"minimum": 1},
        holdout_period=(date(2025, 1, 1), date(2025, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )
    _ = record_id
    grown = multiple_testing.adjusted_threshold(registry=registry)
    assert grown["total_tested_including_current"] == 2
    assert grown["required_alpha"] < empty["required_alpha"]
    registry.close()


# -- 3. PASS alone never wires a strategy --
def test_pass_without_approval_does_not_wire_strategy(tmp_path):
    menu = HypothesisMenu()
    generator = CandidateGenerator(tmp_path / "candidates.sqlite3", menu=menu, min_interval_seconds=0)
    registry = make_registry(tmp_path)
    reviews = ReviewQueue(tmp_path / "reviews.sqlite3")
    versions = ProductionVersionStore(tmp_path / "versions.sqlite3")
    hypothesis = generator.generate_from_response(good_response(), provider_used="mock:unit")
    assert hypothesis is not None
    assert hypothesis.excluded_because is None
    record_id = generator.preregister(
        hypothesis,
        registry,
        holdout_period=(date(2025, 1, 1), date(2025, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
        strategy_id="funding_carry_v1",
    )
    assert registry.get_provenance(record_id)["source"] == "AI_RESEARCH"
    evidence = ExperimentEvidence(
        dataset_id="holdout-funding",
        dataset_sha256="b" * 64,
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
    reviews.submit_for_review(record_id, "funding_carry_v1", "PASS", source="AI_RESEARCH")
    with pytest.raises(StrategyNotGatedError):
        promote_candidate(
            strategy_id="funding_carry_v1",
            edge_validation_record_id=record_id,
            registry=registry,
            reviews=reviews,
            versions=versions,
            approver="atharva",
            rationale="should fail: review still pending",
        )
    root = pathlib.Path(__file__).resolve().parent.parent / "strategies"
    names: list[str] = []
    for path in root.glob("*.py"):
        names.append(path.stem)
    assert "funding_carry_v1" not in names
    reviews.approve(record_id, "atharva", "evidence reviewed, funding class is new")
    produced = promote_candidate(
        strategy_id="funding_carry_v1",
        edge_validation_record_id=record_id,
        registry=registry,
        reviews=reviews,
        versions=versions,
        approver="atharva",
        rationale="human sign-off recorded",
    )
    assert produced.edge_validation_record_id == record_id
    generator.close()
    registry.close()
    reviews.close()
    versions.close()
    menu.close()


# -- 4. provider swap is env-only: two mock endpoints, same code --
class _MockHandlerA(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        _ = self.rfile.read(length)
        body = json.dumps({"ok": True, "which": "A"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return None


class _MockHandlerB(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        _ = self.rfile.read(length)
        body = json.dumps({"ok": True, "which": "B"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return None


def _serve(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_provider_swap_requires_no_code_change(monkeypatch):
    server_a = _serve(_MockHandlerA)
    server_b = _serve(_MockHandlerB)
    try:
        url_a = "http://127.0.0.1:%d/" % server_a.server_address[1]
        url_b = "http://127.0.0.1:%d/" % server_b.server_address[1]
        monkeypatch.setenv("CANDIDATE_PROVIDER_URL", url_a)
        monkeypatch.setenv("CANDIDATE_PROVIDER_API_KEY", "key-a")
        monkeypatch.setenv("CANDIDATE_PROVIDER_MODEL", "mock-a")
        first = propose_from_env("prompt one")
        assert first["which"] == "A"
        # Same function, only environment changes.
        monkeypatch.setenv("CANDIDATE_PROVIDER_URL", url_b)
        monkeypatch.setenv("CANDIDATE_PROVIDER_API_KEY", "key-b")
        monkeypatch.setenv("CANDIDATE_PROVIDER_MODEL", "mock-b")
        second = propose_from_env("prompt two")
        assert second["which"] == "B"
        # Direct call form works identically against either endpoint.
        third = propose_hypothesis("hi", url_a, "key-a", "mock-a")
        assert third["which"] == "A"
    finally:
        server_a.shutdown()
        server_b.shutdown()


def test_provider_config_never_hardcoded(monkeypatch):
    monkeypatch.delenv("CANDIDATE_PROVIDER_URL", raising=False)
    with pytest.raises(ValueError, match="CANDIDATE_PROVIDER_URL"):
        propose_from_env("prompt")


# -- 5. malformed provider output logged as rejected, never coerced --
def test_malformed_output_logged_as_rejected(tmp_path):
    menu = HypothesisMenu()
    generator = CandidateGenerator(tmp_path / "candidates.sqlite3", menu=menu, min_interval_seconds=0)
    bad_payloads: list[dict] = []
    bad_payloads.append({})
    bad_payloads.append({"signal_class": "funding-rate carry"})
    bad_payloads.append({"signal_class": "", "rationale": "x", "proposed_entry_exit_rules": {"a": 1}})
    bad_payloads.append(
        {"signal_class": "funding-rate carry", "rationale": "x", "proposed_entry_exit_rules": {}}
    )
    for bad in bad_payloads:
        assert generator.generate_from_response(bad, provider_used="mock:unit") is None
    assert generator.generate_from_response("not-a-dict", provider_used="mock:unit") is None
    rejections = generator.list_rejections()
    assert len(rejections) == 5
    assert generator.list_logged(status="GENERATED") == []
    generator.close()
    menu.close()


def test_schedule_and_budget_are_respected(tmp_path):
    menu = HypothesisMenu()
    generator = CandidateGenerator(
        tmp_path / "candidates.sqlite3", menu=menu, min_interval_seconds=999999, max_candidates=10
    )
    first = generator.generate_from_response(good_response(), provider_used="mock:unit")
    assert first is not None
    assert generator.should_run() is False
    with pytest.raises(ValueError, match="schedule not due"):
        generator.run_once("prompt", "http://127.0.0.1:9/", "k", "m")
    generator.close()
    menu.close()
    capped = CandidateGenerator(
        tmp_path / "capped.sqlite3", menu=HypothesisMenu(), min_interval_seconds=0, max_candidates=1
    )
    only = capped.generate_from_response(good_response(), provider_used="mock:unit")
    assert only is not None
    assert capped.should_run() is False
    capped.close()


def test_every_generation_is_audited(tmp_path):
    menu = HypothesisMenu()
    generator = CandidateGenerator(tmp_path / "candidates.sqlite3", menu=menu, min_interval_seconds=0)
    ok = generator.generate_from_response(good_response(), provider_used="mock:unit")
    assert ok is not None
    blocked = generator.generate_from_response(good_response("Scalping"), provider_used="mock:unit")
    assert blocked is not None
    assert generator.generate_from_response({}, provider_used="mock:unit") is None
    assert len(generator.list_logged()) == 2
    assert len(generator.list_logged(status="GENERATED")) == 1
    assert len(generator.list_logged(status="EXCLUDED")) == 1
    assert len(generator.list_rejections()) == 1
    generator.close()
    menu.close()


def test_no_strategy_wiring_imports_in_generator():
    import pathlib as _pathlib

    root = _pathlib.Path(__file__).resolve().parent.parent / "candidate_generation"
    names: list[str] = []
    names.append("generator.py")
    names.append("hypothesis_menu.py")
    names.append("multiple_testing.py")
    names.append("provider_client.py")
    for name in names:
        lines = (root / name).read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                lowered = stripped.lower()
                assert "from strategies" not in lowered, name
                assert "import strategies" not in lowered, name
                assert "from risk" not in lowered, name
                assert "from execution" not in lowered, name
    review_lines = (root / "review_queue.py").read_text(encoding="utf-8").splitlines()
    for line in review_lines:
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            lowered = stripped.lower()
            assert "strategies" not in lowered
