"""Module 4 acceptance: gated proposals, ungated rejection, calibration."""

from __future__ import annotations

import pathlib
from datetime import date, datetime, timezone

import pytest

from edge_validation.acceptance_criteria import CRITERION_IDS, AcceptanceCriteria
from edge_validation.evidence import ExperimentEvidence
from edge_validation.registry import EdgeValidationRegistry, StrategyNotGatedError
from hermes.context import ContextBuilder
from strategies.base import LoadedStrategy
from strategies.calibration import calibrate_confidence, confidence_from_window_returns
from strategies.proposal import build_proposal, describe_context_evidence
from strategies.registry import load_strategy


NOW_MS = 1_700_000_000_000


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


def make_pass_registry(tmp_path, strategy_id="synthetic_momentum_v1"):
    registry = make_registry(tmp_path)
    record_id = registry.submit_hypothesis(
        strategy_id=strategy_id,
        hypothesis="Synthetic gated strategy earns PASS for layer tests",
        pre_registered_criteria={"net_return_minimum": 0.0},
        holdout_period=(date(2025, 1, 1), date(2025, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )
    evidence = ExperimentEvidence(
        dataset_id="holdout-synthetic",
        dataset_sha256="a" * 64,
        trade_returns=(0.01, 0.02, 0.015, 0.025),
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
    return registry, record_id


def fresh_snapshot(symbol="BTCUSDT"):
    return {
        "symbol": symbol,
        "event_time": "2024-01-01T00:00:00+00:00",
        "last_price": 100.0,
        "spread_bps": 2.0,
        "bid_depth": 5.0,
        "ask_depth": 5.0,
        "depth_within_bps": {25: {"bid_qty": 4.0, "ask_qty": 4.0}},
        "execution_quality": {"BUY": {"price_impact_rate": 0.0001, "status": "OK"}},
        "technical": {
            "1h": {
                "ema_fast": 101.0,
                "ema_slow": 100.0,
                "rsi": 55.0,
                "atr": 1.0,
                "vwap": 99.5,
                "bollinger_bandwidth": 0.04,
                "returns": 0.001,
            }
        },
        "multi_timeframe_alignment": {"state": "BULLISH", "confirmed_timeframes": 2},
        "trade_cvd": 10.0,
        "aggressive_buy_pct": 0.55,
        "large_trade_concentration": 0.1,
        "top_book_imbalance": 0.05,
        "depth_imbalance": 0.02,
        "trade_volume": 100.0,
    }


def good_health():
    return [
        {
            "component": "spot_websocket",
            "symbol": None,
            "status": "connected",
            "observed_time_ms": NOW_MS,
            "details": {},
        }
    ]


def valid_context():
    builder = ContextBuilder(stale_after_seconds=30.0)
    return builder.build(
        symbol="BTCUSDT",
        feature_snapshot=fresh_snapshot(),
        event_time_ms=NOW_MS,
        breadth={"advancing_pct": 0.7},
        cross_exchange=None,
        health_entries=good_health(),
        now_ms=NOW_MS,
    )


def test_gated_strategy_proposal_links_pass_record(tmp_path):
    registry, record_id = make_pass_registry(tmp_path)
    loaded = load_strategy("synthetic_momentum_v1", registry)
    assert loaded.edge_validation_record_id == record_id
    assert registry.get_verdict("synthetic_momentum_v1") == "PASS"
    context = valid_context()
    assert context.valid is True
    confidence = confidence_from_window_returns((0.02, 0.01, -0.005, 0.015))
    evidence = describe_context_evidence(context)
    assert len(evidence) > 0
    moment = datetime(2024, 1, 1, tzinfo=timezone.utc)
    first = build_proposal(
        loaded, context, action="BUY", confidence=confidence,
        evidence=evidence, timestamp=moment,
    )
    second = build_proposal(
        loaded, context, action="BUY", confidence=confidence,
        evidence=evidence, timestamp=moment,
    )
    assert first.edge_validation_record_id == record_id
    assert first.symbol == "BTCUSDT"
    assert first.action == "BUY"
    assert first.proposal_id == second.proposal_id
    assert 0.0 <= first.confidence <= 1.0


def test_breakout_and_scalping_raise_explicitly(tmp_path):
    registry = make_registry(tmp_path)
    with pytest.raises(StrategyNotGatedError, match="FALSIFIED"):
        load_strategy("breakout", registry)
    with pytest.raises(StrategyNotGatedError, match="FALSIFIED"):
        load_strategy("scalping", registry)
    with pytest.raises(StrategyNotGatedError):
        load_strategy("breakout_24_12_14_hourly", registry)


def test_ungated_and_failed_candidates_stay_blocked(tmp_path):
    registry = make_registry(tmp_path)
    with pytest.raises(StrategyNotGatedError):
        load_strategy("trend_following", registry)
    record_id = registry.submit_hypothesis(
        strategy_id="mean_reversion",
        hypothesis="Failed candidate stays blocked",
        pre_registered_criteria={"minimum": 1},
        holdout_period=(date(2024, 1, 1), date(2024, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )
    registry.record_result(
        record_id,
        bootstrap_ci=(-0.2, -0.01),
        regime_results={"trending": -0.1, "range_bound": -0.05},
        criteria=failed_criteria(),
        verdict="FAIL",
    )
    with pytest.raises(StrategyNotGatedError):
        load_strategy("mean_reversion", registry)


def test_confidence_is_calibrated_hit_rate_not_hardcoded():
    assert calibrate_confidence(8, 10) == pytest.approx(9.0 / 12.0)
    assert calibrate_confidence(2, 10) == pytest.approx(3.0 / 12.0)
    assert calibrate_confidence(8, 10) > calibrate_confidence(2, 10)
    assert calibrate_confidence(0, 0) == pytest.approx(0.5)
    assert confidence_from_window_returns((0.02, 0.01, -0.005, 0.015)) == pytest.approx(4.0 / 6.0)
    with pytest.raises(ValueError):
        calibrate_confidence(-1, 10)
    with pytest.raises(ValueError):
        calibrate_confidence(11, 10)


def test_invalid_context_fails_closed_to_hold(tmp_path):
    registry, record_id = make_pass_registry(tmp_path)
    loaded = load_strategy("synthetic_momentum_v1", registry)
    builder = ContextBuilder(stale_after_seconds=30.0)
    stale = builder.build(
        symbol="BTCUSDT",
        feature_snapshot=fresh_snapshot(),
        event_time_ms=NOW_MS - 300_000,
        breadth=None,
        cross_exchange=None,
        health_entries=good_health(),
        now_ms=NOW_MS,
    )
    assert stale.valid is False
    proposal = build_proposal(
        loaded, stale, action="BUY", confidence=0.8,
        evidence=describe_context_evidence(stale),
    )
    assert proposal.action == "HOLD"
    assert proposal.edge_validation_record_id == record_id


def test_proposal_rejects_bad_confidence_and_missing_link(tmp_path):
    registry, record_id = make_pass_registry(tmp_path)
    loaded = load_strategy("synthetic_momentum_v1", registry)
    context = valid_context()
    evidence = describe_context_evidence(context)
    _ = record_id
    for bad in (1.5, -0.1, True):
        with pytest.raises(ValueError, match="confidence"):
            build_proposal(loaded, context, action="BUY", confidence=bad, evidence=evidence)
    with pytest.raises(ValueError, match="evidence"):
        build_proposal(loaded, context, action="BUY", confidence=0.5, evidence=[])
    tampered = LoadedStrategy(
        strategy_id=loaded.strategy_id,
        edge_validation_record_id="",
        strategy_version=loaded.strategy_version,
    )
    with pytest.raises(ValueError, match="edge_validation_record_id"):
        build_proposal(tampered, context, action="BUY", confidence=0.5, evidence=evidence)


def test_no_ungated_strategy_files_wired(tmp_path):
    _ = tmp_path
    root = pathlib.Path(__file__).resolve().parent.parent / "strategies"
    names = []
    for path in root.glob("*.py"):
        names.append(path.stem)
    for forbidden in ("breakout", "scalping", "trend_following", "mean_reversion", "vwap_reversion", "order_flow"):
        assert forbidden not in names
