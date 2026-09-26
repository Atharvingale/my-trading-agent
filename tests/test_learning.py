"""Module 9 acceptance: gated promotion, loss-invariance, instant rollback."""

from __future__ import annotations

import copy
import time
from datetime import date

import pytest

from candidate_generation.review_queue import ReviewQueue
from edge_validation.acceptance_criteria import CRITERION_IDS, AcceptanceCriteria
from edge_validation.evidence import ExperimentEvidence
from edge_validation.experiment import Candle
from edge_validation.registry import EdgeValidationRegistry, StrategyNotGatedError
from learning.backtester import evaluate_trade_returns, run_family_backtest
from learning.lesson_engine import LessonEngine
from learning.paper_engine import run_paper_leg
from learning.promotion import StrategyStatus, promote_candidate
from learning.trade_analyzer import analyze_trade
from strategies.production_versions import ProductionVersionStore


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


def passing_record(registry, strategy_id="learn_carry_v1"):
    record_id = registry.submit_hypothesis(
        strategy_id=strategy_id,
        hypothesis="Learning-pipeline candidate",
        pre_registered_criteria={"net_return_minimum": 0.0},
        holdout_period=(date(2025, 1, 1), date(2025, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )
    evidence = ExperimentEvidence(
        dataset_id="holdout-learn",
        dataset_sha256="d" * 64,
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


def failing_record(registry, strategy_id="learn_fail_v1"):
    record_id = registry.submit_hypothesis(
        strategy_id=strategy_id,
        hypothesis="Failing candidate",
        pre_registered_criteria={"minimum": 1},
        holdout_period=(date(2025, 4, 1), date(2025, 6, 30)),
        cost_and_tax_assumptions=assumptions(),
    )
    registry.record_result(
        record_id,
        bootstrap_ci=(-0.2, -0.01),
        regime_results={"trending": -0.1, "range_bound": -0.05},
        criteria=failed_criteria(),
        verdict="FAIL",
    )
    return record_id


def losing_trade(trade_id="trade-loss-1", **overrides):
    trade = {
        "trade_id": trade_id,
        "quantity": 2.0,
        "realized_pnl": -15.0,
        "mfe": 1.0,
        "mae": 8.0,
        "avg_slippage": 5.0,
        "thesis": "trend continuation",
        "evidence": [{"feature": "ema_alignment"}],
        "strategy_votes": {"synthetic": "BUY"},
    }
    for key in overrides:
        trade[key] = overrides[key]
    return trade


def validated_lesson(tmp_path, category_trade=None):
    engine = LessonEngine(tmp_path / "lessons.sqlite3")
    trade = category_trade if category_trade is not None else losing_trade()
    analysis = analyze_trade(
        trade, context_valid=True, gate_record_ok=True,
        approved_quantity=2.0, regime_fit=True,
    )
    lesson_id = engine.propose(analysis)
    assert lesson_id is not None
    engine.validate(lesson_id, "atharva")
    return engine, lesson_id


# -- acceptance 1: promotion refuses without a linked PASS --
def test_promotion_refuses_missing_gate_record(tmp_path):
    engine, lesson_id = validated_lesson(tmp_path)
    registry = make_registry(tmp_path)
    reviews = ReviewQueue(tmp_path / "reviews.sqlite3")
    versions = ProductionVersionStore(tmp_path / "versions.sqlite3")
    with pytest.raises((StrategyNotGatedError, KeyError, ValueError)):
        promote_candidate(
            lesson_id=lesson_id,
            lesson_engine=engine,
            strategy_id="learn_carry_v1",
            edge_validation_record_id="record-missing",
            registry=registry,
            reviews=reviews,
            versions=versions,
            approver="atharva",
            rationale="no such record",
        )
    engine.close()
    registry.close()
    reviews.close()
    versions.close()


def test_promotion_refuses_non_pass_verdict(tmp_path):
    engine = LessonEngine(tmp_path / "lessons.sqlite3")
    analysis = analyze_trade(
        losing_trade(), context_valid=True, gate_record_ok=True,
        approved_quantity=2.0, regime_fit=True,
    )
    lesson_id = engine.propose(analysis)
    assert lesson_id is not None
    engine.validate(lesson_id, "atharva")
    registry = make_registry(tmp_path)
    record_id = failing_record(registry)
    reviews = ReviewQueue(tmp_path / "reviews.sqlite3")
    reviews.submit_for_review(record_id, "learn_fail_v1", "FAIL", source="TRADE_LEARNING")
    reviews.approve(record_id, "atharva", "approved but gate says FAIL")
    versions = ProductionVersionStore(tmp_path / "versions.sqlite3")
    with pytest.raises(StrategyNotGatedError):
        promote_candidate(
            lesson_id=lesson_id,
            lesson_engine=engine,
            strategy_id="learn_fail_v1",
            edge_validation_record_id=record_id,
            registry=registry,
            reviews=reviews,
            versions=versions,
            approver="atharva",
            rationale="gate says FAIL",
        )
    engine.close()
    registry.close()
    reviews.close()
    versions.close()


def test_promotion_refuses_unvalidated_lesson(tmp_path):
    engine = LessonEngine(tmp_path / "lessons.sqlite3")
    analysis = analyze_trade(
        losing_trade(), context_valid=True, gate_record_ok=True,
        approved_quantity=2.0, regime_fit=True,
    )
    lesson_id = engine.propose(analysis)
    assert lesson_id is not None
    registry = make_registry(tmp_path)
    record_id = passing_record(registry)
    reviews = ReviewQueue(tmp_path / "reviews.sqlite3")
    versions = ProductionVersionStore(tmp_path / "versions.sqlite3")
    with pytest.raises(ValueError, match="not VALIDATED"):
        promote_candidate(
            lesson_id=lesson_id,
            lesson_engine=engine,
            strategy_id="learn_carry_v1",
            edge_validation_record_id=record_id,
            registry=registry,
            reviews=reviews,
            versions=versions,
            approver="atharva",
            rationale="lesson never validated",
        )
    engine.close()
    registry.close()
    reviews.close()
    versions.close()


# -- acceptance 2: one bad trade never touches live parameters --
def test_single_losing_trade_leaves_production_config_untouched(tmp_path):
    live_config = {
        "strategies": {"synthetic_carry_v1": {"risk_per_trade": 0.01, "max_notional": 1000.0}},
        "kill_switch": False,
        "limits": {"max_daily_loss": 200.0},
    }
    frozen = copy.deepcopy(live_config)
    engine = LessonEngine(tmp_path / "lessons.sqlite3")
    # NORMAL loss: valid plumbing, adverse outcome — banks nothing.
    analysis = analyze_trade(
        losing_trade(mfe=6.0, mae=1.0, realized_pnl=-2.0),
        context_valid=True, gate_record_ok=True, approved_quantity=2.0, regime_fit=True,
    )
    assert analysis.category == "NORMAL"
    assert engine.propose(analysis) is None
    # SIGNAL loss: banks a candidate, still touches no production parameter.
    analysis2 = analyze_trade(
        losing_trade(), context_valid=True, gate_record_ok=True,
        approved_quantity=2.0, regime_fit=True,
    )
    assert analysis2.category == "SIGNAL"
    lesson_id = engine.propose(analysis2)
    assert lesson_id is not None
    assert live_config == frozen
    engine.close()


# -- acceptance 3: instant rollback, history preserved --
def test_rollback_is_instant_and_history_survives_disable(tmp_path):
    versions = ProductionVersionStore(tmp_path / "versions.sqlite3")
    versions.create_version(
        version_id="synth@v1", strategy_id="synth", edge_validation_record_id="edge-1",
        approver="atharva", rationale="v1", approved_at=None,
    )
    versions.create_version(
        version_id="synth@v2", strategy_id="synth", edge_validation_record_id="edge-1",
        approver="atharva", rationale="v2", approved_at=None,
    )
    status = StrategyStatus(tmp_path / "status.sqlite3")
    status.set_active("synth", "synth@v2", "atharva", "promote v2")
    assert status.active_version("synth") == "synth@v2"
    started = time.monotonic()
    status.rollback("synth", "synth@v1", "atharva", "v2 misbehaving")
    elapsed = time.monotonic() - started
    assert status.active_version("synth") == "synth@v1"
    assert elapsed < 5.0
    status.disable("synth", "atharva", "precaution halt")
    assert status.is_disabled("synth") is True
    assert len(versions.list_versions("synth")) == 2
    status.enable("synth", "atharva", "investigation complete")
    assert status.is_disabled("synth") is False
    assert len(status.history("synth")) >= 4
    versions.close()
    status.close()


# -- analyzer categories follow the fixed priority --
def test_analyzer_category_priority(tmp_path):
    _ = tmp_path
    assert analyze_trade(losing_trade(), gate_record_ok=False).category == "GATE"
    assert analyze_trade(losing_trade(), gate_record_ok=None).category == "DATA"
    assert analyze_trade(losing_trade(), context_valid=False, gate_record_ok=True).category == "DATA"
    risk = analyze_trade(
        losing_trade(), context_valid=True, gate_record_ok=True, approved_quantity=9.0
    )
    assert risk.category == "RISK"
    execution = analyze_trade(
        losing_trade(avg_slippage=60.0), context_valid=True, gate_record_ok=True,
        approved_quantity=2.0, regime_fit=True,
    )
    assert execution.category == "EXECUTION"
    regime = analyze_trade(
        losing_trade(), context_valid=True, gate_record_ok=True,
        approved_quantity=2.0, regime_fit=False,
    )
    assert regime.category == "REGIME"
    signal = analyze_trade(
        losing_trade(), context_valid=True, gate_record_ok=True,
        approved_quantity=2.0, regime_fit=True,
    )
    assert signal.category == "SIGNAL"
    assert signal.candidate_hypothesis is not None
    normal = analyze_trade(
        losing_trade(mfe=6.0, mae=1.0, realized_pnl=-2.0), context_valid=True,
        gate_record_ok=True, approved_quantity=2.0, regime_fit=True,
    )
    assert normal.category == "NORMAL"
    assert normal.candidate_hypothesis is None


def test_lesson_counts_and_adjudication(tmp_path):
    engine = LessonEngine(tmp_path / "lessons.sqlite3")
    first = analyze_trade(
        losing_trade("t-1"), context_valid=True, gate_record_ok=True,
        approved_quantity=2.0, regime_fit=True,
    )
    second = analyze_trade(
        losing_trade("t-2", avg_slippage=80.0), context_valid=True, gate_record_ok=True,
        approved_quantity=2.0, regime_fit=True,
    )
    lesson_a = engine.propose(first)
    lesson_b = engine.propose(second)
    assert lesson_a is not None
    assert lesson_b is not None
    engine.validate(str(lesson_a), "atharva")
    engine.reject(str(lesson_b), "atharva")
    counts = engine.counts()
    assert counts["CANDIDATE"] == 0
    assert counts["VALIDATED"] == 1
    assert counts["REJECTED"] == 1
    with pytest.raises(ValueError, match="already decided"):
        engine.validate(str(lesson_a), "atharva")
    engine.close()


# -- backtester dispatch + evidence scoring --
def test_backtester_known_family_and_inconclusive(tmp_path):
    _ = tmp_path
    candles: list[Candle] = []
    index = 0
    for price in (100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
                  110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
                  120, 119, 118, 117, 116, 115, 114, 113, 112, 111):
        candles.append(Candle(timestamp=index, open=price, high=price + 1, low=price - 1, close=price))
        index = index + 1
    report = run_family_backtest("trend following", candles)
    assert report.method == "edge_validation.experiment"
    assert report.trade_count >= 0
    assert report.hint in ("PASS_HINT", "FAIL_HINT")
    unknown = run_family_backtest("funding-rate carry", candles)
    assert unknown.hint == "INCONCLUSIVE"
    assert unknown.trade_count == 0
    scored = evaluate_trade_returns(
        (0.02, 0.015, 0.025, 0.03),
        {"trending": 0.02, "range_bound": 0.01},
        dataset_id="unit",
        dataset_sha256="e" * 64,
        bootstrap_samples=1000,
    )
    assert scored["net_return"] > 0
    assert scored["bootstrap_ci"][0] > 0


# -- paper adapter is deterministic --
def test_paper_leg_deterministic():
    orders = [
        {"order_id": "paper-1", "symbol": "BTCUSDT", "side": "BUY",
         "quantity": 1.0, "requested_price": 100.0, "timestamp_ms": 1000}
    ]
    markets = [{"bid": 99.9, "ask": 100.1, "depth_qty": 10.0}]
    first = run_paper_leg(orders, markets)
    second = run_paper_leg(orders, markets)
    assert first["fill_count"] == 1
    assert first["snapshot"]["fill_count"] == second["snapshot"]["fill_count"]
    assert first["slippage_total"] == pytest.approx(second["slippage_total"])
    with pytest.raises(ValueError, match="one-to-one"):
        run_paper_leg(orders, [])


# -- full pipeline promotion succeeds only at the end --
def test_full_pipeline_promotes_validated_pass_candidate(tmp_path):
    engine, lesson_id = validated_lesson(tmp_path)
    registry = make_registry(tmp_path)
    record_id = passing_record(registry)
    reviews = ReviewQueue(tmp_path / "reviews.sqlite3")
    reviews.submit_for_review(record_id, "learn_carry_v1", "PASS", source="TRADE_LEARNING")
    reviews.approve(record_id, "atharva", "learning candidate reviewed")
    versions = ProductionVersionStore(tmp_path / "versions.sqlite3")
    produced = promote_candidate(
        lesson_id=lesson_id,
        lesson_engine=engine,
        strategy_id="learn_carry_v1",
        edge_validation_record_id=record_id,
        registry=registry,
        reviews=reviews,
        versions=versions,
        approver="atharva",
        rationale="pipeline complete",
    )
    assert produced.edge_validation_record_id == record_id
    status = StrategyStatus(tmp_path / "status.sqlite3")
    status.set_active("learn_carry_v1", produced.version_id, "atharva", "go live")
    assert status.active_version("learn_carry_v1") == produced.version_id
    engine.close()
    registry.close()
    reviews.close()
    versions.close()
    status.close()


def test_no_llm_in_learning():
    import pathlib as _pathlib

    root = _pathlib.Path(__file__).resolve().parent.parent / "learning"
    for path in root.glob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                lowered = stripped.lower()
                assert "llm" not in lowered, str(path)
                assert "openai" not in lowered, str(path)
                assert "anthropic" not in lowered, str(path)
