"""Module 6 acceptance: every check, kill switch, quantity integrity."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from hermes.context import ContextBuilder
from hermes.models.decision import Decision
from risk.engine import RiskEngine, verify_integrity
from risk.limits import RiskLimits
from risk.position_sizing import calculate_quantity


NOW_MS = 1_700_000_000_000


def fresh_snapshot(symbol="BTCUSDT", bid_depth=500.0, ask_depth=500.0, spread_bps=2.0):
    return {
        "symbol": symbol,
        "event_time": "2024-01-01T00:00:00+00:00",
        "last_price": 100.0,
        "spread_bps": spread_bps,
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
        "depth_within_bps": {25: {"bid_qty": 400.0, "ask_qty": 400.0}},
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


def valid_context(symbol="BTCUSDT", now_ms=NOW_MS, **snapshot_kwargs):
    builder = ContextBuilder(stale_after_seconds=30.0)
    return builder.build(
        symbol=symbol,
        feature_snapshot=fresh_snapshot(symbol, **snapshot_kwargs),
        event_time_ms=now_ms,
        breadth={"advancing_pct": 0.7},
        cross_exchange=None,
        health_entries=good_health(),
        now_ms=now_ms,
    )


def stale_context(symbol="BTCUSDT"):
    builder = ContextBuilder(stale_after_seconds=30.0)
    return builder.build(
        symbol=symbol,
        feature_snapshot=fresh_snapshot(symbol),
        event_time_ms=NOW_MS - 300_000,
        breadth=None,
        cross_exchange=None,
        health_entries=good_health(),
        now_ms=NOW_MS,
    )


def make_decision(
    decision_id="dec-001",
    action="BUY",
    symbol="BTCUSDT",
    reference=100.0,
    stop=98.0,
    target=103.0,
    now_ms=NOW_MS,
):
    moment = datetime.fromtimestamp(now_ms / 1000.0, tz=timezone.utc)
    return Decision(
        decision_id=decision_id,
        timestamp=moment,
        symbol=symbol,
        action=action,
        confidence=0.7,
        entry={"symbol": symbol, "side": action, "reference_price": reference},
        position={"position_qty": 0.0, "exposure_notional": 0.0, "unrealized_pnl": 0.0, "realized_pnl": 0.0},
        risk={"stop_loss": stop, "take_profit": target, "risk_amount": 0.0},
        time_horizon="15m",
        thesis=["synthetic thesis"],
        strategy_version_id="v1",
        expiry_seconds=120,
    )


def base_account(**overrides):
    account = {
        "equity": 10000.0,
        "peak_equity": 10000.0,
        "daily_realized_pnl": 0.0,
        "open_notional": 0.0,
        "symbol_exposure": 0.0,
        "open_positions": 0,
        "now_ms": NOW_MS + 1000,
    }
    for key in overrides:
        account[key] = overrides[key]
    return account


def test_happy_path_approves_with_exact_quantity():
    engine = RiskEngine()
    decision = make_decision()
    context = valid_context()
    result = engine.evaluate(decision, context, **base_account())
    assert result.status == "APPROVED"
    assert result.approved_quantity > 0
    assert result.rejection_reason is None
    assert result.stop == pytest.approx(98.0)
    assert result.target == pytest.approx(103.0)
    assert verify_integrity(result) is True
    # Exposure math is exact, not rounded downstream.
    assert result.exposure_after["new_notional"] == pytest.approx(result.approved_quantity * 100.0)


def test_stale_context_rejected_regardless_of_confidence():
    engine = RiskEngine()
    decision = make_decision()
    context = stale_context()
    assert context.valid is False
    result = engine.evaluate(decision, context, **base_account())
    assert result.status == "REJECTED"
    assert result.approved_quantity == 0.0
    assert verify_integrity(result) is True


def test_hold_decision_needs_no_execution():
    engine = RiskEngine()
    decision = make_decision(decision_id="dec-hold", action="HOLD")
    context = valid_context()
    result = engine.evaluate(decision, context, **base_account())
    assert result.status == "REJECTED"
    assert "HOLD" in str(result.rejection_reason)


def test_quantity_integrity_tamper_detected():
    engine = RiskEngine()
    result = engine.evaluate(make_decision(), valid_context(), **base_account())
    assert result.status == "APPROVED"
    assert verify_integrity(result) is True
    tampered = dataclasses.replace(result, approved_quantity=result.approved_quantity + 1.0)
    assert verify_integrity(tampered) is False
    retargeted = dataclasses.replace(result, stop=result.stop + 5.0)
    assert verify_integrity(retargeted) is False


def test_kill_switch_blocks_until_manually_cleared():
    engine = RiskEngine()
    engine.activate_kill_switch("manual drill")
    assert engine.is_halted() is True
    first = engine.evaluate(make_decision("dec-k1"), valid_context(), **base_account())
    assert first.status == "REJECTED"
    assert "kill switch" in str(first.rejection_reason).lower()
    with pytest.raises(ValueError, match="approver"):
        engine.clear_kill_switch("", "reason")
    with pytest.raises(ValueError, match="rationale"):
        engine.clear_kill_switch("atharva", "")
    engine.clear_kill_switch("atharva", "drill complete")
    assert engine.is_halted() is False
    second = engine.evaluate(make_decision("dec-k2"), valid_context(), **base_account())
    assert second.status == "APPROVED"


def test_symbol_exposure_rejected():
    engine = RiskEngine()
    result = engine.evaluate(
        make_decision(), valid_context(), **base_account(symbol_exposure=990.0)
    )
    assert result.status == "REJECTED"
    assert "per-symbol" in str(result.rejection_reason)


def test_portfolio_exposure_rejected():
    engine = RiskEngine()
    result = engine.evaluate(
        make_decision(), valid_context(), **base_account(open_notional=2990.0)
    )
    assert result.status == "REJECTED"
    assert "portfolio" in str(result.rejection_reason).lower() or "notional" in str(result.rejection_reason).lower()


def test_concurrent_positions_rejected():
    engine = RiskEngine()
    result = engine.evaluate(make_decision(), valid_context(), **base_account(open_positions=3))
    assert result.status == "REJECTED"
    assert "max" in str(result.rejection_reason).lower()


def test_daily_loss_rejected():
    engine = RiskEngine()
    result = engine.evaluate(
        make_decision(), valid_context(), **base_account(daily_realized_pnl=-250.0)
    )
    assert result.status == "REJECTED"
    assert "loss limit" in str(result.rejection_reason).lower()


def test_drawdown_rejected():
    engine = RiskEngine()
    result = engine.evaluate(
        make_decision(), valid_context(), **base_account(equity=8900.0, peak_equity=10000.0)
    )
    assert result.status == "REJECTED"
    assert "drawdown" in str(result.rejection_reason).lower()


def test_leverage_rejected_with_tight_limit():
    engine = RiskEngine(RiskLimits(max_leverage=0.01))
    result = engine.evaluate(make_decision(), valid_context(), **base_account())
    assert result.status == "REJECTED"
    assert "leverage" in str(result.rejection_reason).lower()


def test_stop_distance_rejected():
    engine = RiskEngine()
    tight = make_decision(decision_id="dec-tight", stop=99.99, target=100.01)
    result = engine.evaluate(tight, valid_context(), **base_account())
    assert result.status == "REJECTED"
    assert "stop distance" in str(result.rejection_reason).lower()
    far = make_decision(decision_id="dec-far", stop=50.0, target=150.0)
    result2 = engine.evaluate(far, valid_context(), **base_account())
    assert result2.status == "REJECTED"
    assert "stop distance" in str(result2.rejection_reason).lower()


def test_wrong_side_stop_rejected():
    engine = RiskEngine()
    bad_buy = make_decision(action="BUY", stop=102.0, target=103.0)
    assert engine.evaluate(bad_buy, valid_context(), **base_account()).status == "REJECTED"
    bad_sell = make_decision(decision_id="dec-s2", action="SELL", stop=98.0, target=97.0)
    assert engine.evaluate(bad_sell, valid_context(), **base_account()).status == "REJECTED"


def test_duplicate_decision_rejected():
    engine = RiskEngine()
    first = engine.evaluate(make_decision("dec-dup"), valid_context(), **base_account())
    assert first.status == "APPROVED"
    second = engine.evaluate(make_decision("dec-dup"), valid_context(), **base_account())
    assert second.status == "REJECTED"
    assert "duplicate" in str(second.rejection_reason).lower()


def test_existing_position_blocks_new_entry():
    from hermes.models.market import PortfolioState

    engine = RiskEngine()
    context = valid_context()
    holding = PortfolioState(position_qty=1.0, exposure_notional=500.0, available=True)
    context_with_position = dataclasses.replace(context, portfolio=holding)
    result = engine.evaluate(make_decision(), context_with_position, **base_account())
    assert result.status == "REJECTED"
    assert "existing position" in str(result.rejection_reason).lower()


def test_cooldown_after_stopout():
    engine = RiskEngine()
    engine.note_stopout("BTCUSDT", NOW_MS)
    result = engine.evaluate(make_decision(), valid_context(), **base_account())
    assert result.status == "REJECTED"
    assert "cooldown" in str(result.rejection_reason).lower()


def test_liquidity_rejected_on_thin_book():
    engine = RiskEngine()
    thin = valid_context(bid_depth=0.01, ask_depth=0.01)
    result = engine.evaluate(make_decision(), thin, **base_account())
    assert result.status == "REJECTED"


def test_spread_rejected_when_wide():
    engine = RiskEngine()
    wide = valid_context(spread_bps=100.0)
    result = engine.evaluate(make_decision(), wide, **base_account())
    assert result.status == "REJECTED"
    assert "spread" in str(result.rejection_reason).lower()


def test_expired_decision_rejected():
    engine = RiskEngine()
    old = make_decision(now_ms=NOW_MS - 600_000)
    result = engine.evaluate(old, valid_context(), **base_account())
    assert result.status == "REJECTED"
    assert "expired" in str(result.rejection_reason).lower()


def test_symbol_mismatch_rejected():
    engine = RiskEngine()
    decision = make_decision(symbol="ETHUSDT")
    context = valid_context(symbol="BTCUSDT")
    result = engine.evaluate(decision, context, **base_account())
    assert result.status == "REJECTED"


def test_limits_are_config_driven():
    with pytest.raises(ValueError):
        RiskLimits(max_position_notional_per_symbol=-1.0)
    strict = RiskLimits(max_position_notional_per_symbol=1.0)
    engine = RiskEngine(strict)
    result = engine.evaluate(make_decision(), valid_context(), **base_account())
    assert result.status == "REJECTED"


def test_sizing_is_exact_and_capped():
    quantity = calculate_quantity(
        equity=10000.0,
        risk_per_trade=0.01,
        entry_price=100.0,
        stop_price=98.0,
        max_position_notional=100000.0,
        depth_notional=None,
    )
    assert quantity == pytest.approx(50.0)
    capped = calculate_quantity(
        equity=10000.0,
        risk_per_trade=0.01,
        entry_price=100.0,
        stop_price=98.0,
        max_position_notional=100.0,
        depth_notional=None,
    )
    assert capped == pytest.approx(1.0)
    with pytest.raises(ValueError):
        calculate_quantity(
            equity=10000.0,
            risk_per_trade=0.01,
            entry_price=100.0,
            stop_price=100.0,
            max_position_notional=1000.0,
        )


def test_no_llm_or_execution_imports_in_risk():
    import pathlib as _pathlib

    root = _pathlib.Path(__file__).resolve().parent.parent / "risk"
    for path in root.glob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                lowered = stripped.lower()
                assert "llm" not in lowered, str(path)
                assert "openai" not in lowered, str(path)
                assert "anthropic" not in lowered, str(path)
                assert "execution" not in lowered, str(path)
