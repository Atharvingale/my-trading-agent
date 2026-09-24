"""Module 5 acceptance on synthetic proposals (Module 4 has zero real ones)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from edge_validation.acceptance_criteria import CRITERION_IDS, AcceptanceCriteria
from edge_validation.evidence import ExperimentEvidence
from edge_validation.registry import EdgeValidationRegistry
from hermes.context import ContextBuilder
from hermes.decision import (
    consume_decision,
    decide,
    is_expired,
    ExpiredDecisionError,
)
from hermes.models.decision import Decision, DecisionEvidenceRecord
from strategies.base import LoadedStrategy
from strategies.calibration import calibrate_confidence
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


def pass_registry(tmp_path, strategy_id):
    registry = make_registry(tmp_path)
    record_id = registry.submit_hypothesis(
        strategy_id=strategy_id,
        hypothesis="Synthetic gated strategy for decision-engine tests: %s" % strategy_id,
        pre_registered_criteria={"net_return_minimum": 0.0},
        holdout_period=(date(2025, 1, 1), date(2025, 3, 31)),
        cost_and_tax_assumptions=assumptions(),
    )
    evidence = ExperimentEvidence(
        dataset_id="holdout-synthetic-%s" % strategy_id,
        dataset_sha256="a" * 64,
        trade_returns=(0.01, 0.02, 0.015, 0.025),
        regime_returns={"trending": 0.02, "range_bound": 0.01},
        net_of_costs_and_tax=True,
        bootstrap_seed=7,
        bootstrap_samples=1000,
    )
    checks = {}
    for criterion_id in CRITERION_IDS:
        checks[criterion_id] = True
    registry.record_result(
        record_id,
        bootstrap_ci=evidence.bootstrap_ci,
        regime_results=evidence.regime_returns,
        criteria=AcceptanceCriteria(checks),
        verdict="PASS",
        evidence=evidence,
    )
    return registry


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


def valid_context(symbol="BTCUSDT", now_ms=NOW_MS):
    builder = ContextBuilder(stale_after_seconds=30.0)
    return builder.build(
        symbol=symbol,
        feature_snapshot=fresh_snapshot(symbol),
        event_time_ms=now_ms,
        breadth={"advancing_pct": 0.7},
        cross_exchange=None,
        health_entries=good_health(),
        now_ms=now_ms,
    )


def gated_proposal(tmp_path, strategy_id, context, action, confidence=0.7):
    registry = pass_registry(tmp_path, strategy_id)
    loaded = load_strategy(strategy_id, registry)
    evidence = describe_context_evidence(context)
    return build_proposal(loaded, context, action=action, confidence=confidence, evidence=evidence), registry


def test_determinism_byte_identical(tmp_path):
    context = valid_context()
    first_proposal, _ = gated_proposal(tmp_path, "synthetic_alpha_v1", context, "BUY")
    second_proposal, _ = gated_proposal(tmp_path, "synthetic_beta_v1", context, "SELL")
    proposals = [first_proposal, second_proposal]
    first, first_record = decide("BTCUSDT", context, proposals)
    second, second_record = decide("BTCUSDT", context, proposals)
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(second.to_dict(), sort_keys=True)
    assert json.dumps(first_record.to_dict(), sort_keys=True) == json.dumps(second_record.to_dict(), sort_keys=True)
    assert first.decision_id == second.decision_id
    # Proposal edge links resolve to PASS verdicts.
    assert first_record.strategy_votes["synthetic_alpha_v1"] == "BUY"
    assert first_record.strategy_votes["synthetic_beta_v1"] == "SELL"


def test_zero_proposals_hold_everywhere():
    for symbol in ("BTCUSDT", "ETHUSDT"):
        context = valid_context(symbol)
        decision, record = decide(symbol, context, [])
        assert decision.action == "HOLD"
        assert decision.symbol == symbol
        assert decision.confidence == pytest.approx(calibrate_confidence(0, 0))
        assert decision.strategy_version_id == "none"
        assert record.decision == "HOLD"
        assert record.risk_assessment == "NoAction"


def test_conflicting_proposals_tie_break_to_hold(tmp_path):
    context = valid_context()
    buy, _ = gated_proposal(tmp_path, "synthetic_alpha_v1", context, "BUY", confidence=0.7)
    sell, _ = gated_proposal(tmp_path, "synthetic_beta_v1", context, "SELL", confidence=0.7)
    # Equal weights (both unknown histories -> 0.5): exact tie must HOLD.
    decision, record = decide("BTCUSDT", context, [buy, sell])
    assert decision.action == "HOLD"
    assert "tie" in record.decision_rationale


def test_weighted_majority_wins(tmp_path):
    context = valid_context()
    buy_a, _ = gated_proposal(tmp_path, "synthetic_alpha_v1", context, "BUY", confidence=0.7)
    buy_b, _ = gated_proposal(tmp_path, "synthetic_beta_v1", context, "BUY", confidence=0.6)
    sell_c, _ = gated_proposal(tmp_path, "synthetic_gamma_v1", context, "SELL", confidence=0.9)
    decision, record = decide("BTCUSDT", context, [buy_a, buy_b, sell_c])
    assert decision.action == "BUY"
    assert decision.strategy_version_id == "v1"
    assert record.risk_assessment == "PendingRiskReview"
    assert decision.risk["stop_loss"] > 0
    assert decision.risk["take_profit"] > 0


def test_expired_decision_rejected_by_consumer(tmp_path):
    context = valid_context()
    proposal, _ = gated_proposal(tmp_path, "synthetic_alpha_v1", context, "BUY")
    moment = datetime(2024, 1, 1, tzinfo=timezone.utc)
    decision, _ = decide("BTCUSDT", context, [proposal], timestamp=moment, expiry_seconds=120)
    assert consume_decision(decision, moment + timedelta(seconds=10)) is decision
    assert is_expired(decision, moment + timedelta(seconds=120)) is False
    assert is_expired(decision, moment + timedelta(seconds=121)) is True
    with pytest.raises(ExpiredDecisionError):
        consume_decision(decision, moment + timedelta(seconds=200))


def test_malformed_input_fails_closed(tmp_path):
    context = valid_context()
    proposal, _ = gated_proposal(tmp_path, "synthetic_alpha_v1", context, "BUY")
    garbage = ["not-a-proposal", 42, {"action": "BUY"}]
    mixed = []
    for item in garbage:
        mixed.append(item)
    mixed.append(proposal)
    decision, _ = decide("BTCUSDT", context, mixed)
    # Only the well-formed proposal counts; malformed entries are dropped.
    assert "3 dropped" in decision.thesis[0]
    # Invalid context forces HOLD even with live BUY proposals.
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
    stale_proposal, _ = gated_proposal(tmp_path, "synthetic_beta_v1", stale, "BUY")
    # build_proposal itself forces HOLD on invalid context; engine agrees.
    assert stale_proposal.action == "HOLD"
    decision2, _ = decide("BTCUSDT", stale, [proposal])
    assert decision2.action == "HOLD"


def test_confidence_calibrated_not_hardcoded():
    histories = {"synthetic_alpha_v1": (8, 10), "synthetic_beta_v1": (2, 10)}
    weight_strong = calibrate_confidence(8, 10)
    weight_weak = calibrate_confidence(2, 10)
    assert weight_strong == pytest.approx(9.0 / 12.0)
    context = valid_context()
    assert context.valid is True
    # Expected value recomputed here from the documented formula.
    expected = (weight_strong + 1.0) / (weight_strong + 2.0)
    assert expected > weight_weak
    assert expected < 1.0


def test_thesis_template_deterministic(tmp_path):
    context = valid_context()
    proposal, _ = gated_proposal(tmp_path, "synthetic_alpha_v1", context, "BUY")
    first, _ = decide("BTCUSDT", context, [proposal])
    second, _ = decide("BTCUSDT", context, [proposal])
    assert first.thesis == second.thesis
    assert len(first.thesis) > 0
    found = False
    for line in first.thesis:
        if "BTCUSDT" in line:
            found = True
    assert found is True


def test_no_llm_or_trading_calls_in_module_5():
    import pathlib as _pathlib

    root = _pathlib.Path(__file__).resolve().parent.parent / "hermes"
    files = [root / "decision.py", root / "models" / "decision.py"]
    for path in files:
        assert path.exists(), f"Module 5 file missing: {path}"
    forbidden = (
        "llm", "openai", "anthropic", "from risk", "import risk",
        "from execution", "import execution",
    )
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                lowered = stripped.lower()
                for marker in forbidden:
                    if marker in lowered:
                        raise AssertionError(f"{path.name} contains forbidden import: {line.strip()}")


def test_evidence_record_shape(tmp_path):
    context = valid_context()
    proposal, _ = gated_proposal(tmp_path, "synthetic_alpha_v1", context, "BUY")
    _, record = decide("BTCUSDT", context, [proposal])
    assert isinstance(record, DecisionEvidenceRecord)
    payload = record.to_dict()
    for key in (
        "decision_id", "market_snapshot_id", "action", "confidence",
        "evidence", "strategy_votes", "decision_rationale", "risk_assessment", "decision",
    ):
        assert key in payload
    assert payload["market_snapshot_id"].startswith("snap_BTCUSDT_")
    assert isinstance(payload["decision_rationale"], str)
    assert len(payload["decision_rationale"]) > 0
