"""Module 7 acceptance: verified, signed, idempotent, fail-closed execution."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from execution.n8n_client import (
    ExecutionConfig,
    InvalidRequestError,
    N8nUnavailableError,
    RequestExpiredError,
    assert_quantity_matches,
    build_request,
    request_payload,
    sign_payload,
    submit_request,
    verify_webhook_signature,
)
from execution.order_manager import ExecutionOrderManager
from execution.reconciliation import reconcile
from hermes.context import ContextBuilder
from hermes.models.decision import Decision
from hermes.models.market import PortfolioState
from risk.engine import RiskEngine


NOW_MS = 1_700_000_000_000


def moment(ms=NOW_MS):
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


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


def valid_context(symbol="BTCUSDT", now_ms=NOW_MS, portfolio=None):
    builder = ContextBuilder(stale_after_seconds=30.0)
    context = builder.build(
        symbol=symbol,
        feature_snapshot=fresh_snapshot(symbol),
        event_time_ms=now_ms,
        breadth={"advancing_pct": 0.7},
        cross_exchange=None,
        health_entries=good_health(),
        now_ms=now_ms,
    )
    if portfolio is not None:
        context = dataclasses.replace(context, portfolio=portfolio)
    return context


def make_decision(decision_id="dec-001", action="BUY", symbol="BTCUSDT", now_ms=NOW_MS):
    return Decision(
        decision_id=decision_id,
        timestamp=moment(now_ms),
        symbol=symbol,
        action=action,
        confidence=0.7,
        entry={"symbol": symbol, "side": action, "reference_price": 100.0},
        position={"position_qty": 0.0, "exposure_notional": 0.0, "unrealized_pnl": 0.0, "realized_pnl": 0.0},
        risk={"stop_loss": 98.0, "take_profit": 103.0, "risk_amount": 0.0},
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


def approved_decision(decision_id="dec-001", action="BUY"):
    engine = RiskEngine()
    risk = engine.evaluate(make_decision(decision_id, action), valid_context(), **base_account())
    assert risk.status == "APPROVED"
    return risk


def make_config():
    return ExecutionConfig(
        webhook_url="https://n8n.local/webhook/test",
        webhook_secret="unit-secret",
        environment="paper",
    )


# -- unit: request construction --
def test_build_copies_exact_quantity():
    risk = approved_decision()
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    assert request.quantity == risk.approved_quantity
    assert request.risk_decision_id == risk.risk_decision_id
    assert request.idempotency_key == request.execution_id
    assert request.protection["stop"] == pytest.approx(risk.stop)
    assert request.protection["target"] == pytest.approx(risk.target)


def test_build_rejects_tampered_decision():
    risk = approved_decision()
    tampered = dataclasses.replace(risk, approved_quantity=risk.approved_quantity + 1.0)
    with pytest.raises(InvalidRequestError, match="integrity"):
        build_request(tampered, symbol="BTCUSDT", side="BUY", now=moment())


def test_build_rejects_non_approved():
    engine = RiskEngine()
    rejected = engine.evaluate(make_decision("dec-hold", "HOLD"), valid_context(), **base_account())
    assert rejected.status == "REJECTED"
    with pytest.raises(InvalidRequestError, match="not APPROVED"):
        build_request(rejected, symbol="BTCUSDT", side="BUY", now=moment())


def test_build_rejects_symbol_mismatch_and_bad_side():
    risk = approved_decision()
    with pytest.raises(InvalidRequestError, match="does not match sealed"):
        build_request(risk, symbol="ETHUSDT", side="BUY", now=moment())
    with pytest.raises(InvalidRequestError, match="side"):
        build_request(risk, symbol="BTCUSDT", side="HOLD", now=moment())
    with pytest.raises(InvalidRequestError, match="order_type"):
        build_request(risk, symbol="BTCUSDT", side="BUY", now=moment(), order_type="STOP")


def test_quantity_mismatch_rejected_before_submission():
    risk = approved_decision()
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    calls: list[dict] = []

    def sender(url, payload, headers, timeout):
        calls.append(payload)
        return {"order_id": "ord-1"}

    drifted = dataclasses.replace(request, quantity=request.quantity + 1e-9)
    with pytest.raises(InvalidRequestError, match="exactly match"):
        assert_quantity_matches(drifted, risk)
    with pytest.raises(InvalidRequestError, match="exactly match"):
        submit_request(drifted, config=make_config(), sender=sender, now=moment(), risk_decision=risk)
    assert calls == []
    rounded = dataclasses.replace(request, quantity=round(request.quantity, 2))
    if rounded.quantity != request.quantity:
        with pytest.raises(InvalidRequestError, match="exactly match"):
            submit_request(rounded, config=make_config(), sender=sender, now=moment(), risk_decision=risk)
        assert calls == []


# -- unit: expiry (clock injection) --
def test_expired_request_never_submitted():
    risk = approved_decision()
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment(), expiry_seconds=60)
    calls: list[dict] = []

    def sender(url, payload, headers, timeout):
        calls.append(payload)
        return {"order_id": "ord-1"}

    late = datetime.fromtimestamp((NOW_MS + 61_000) / 1000.0, tz=timezone.utc)
    with pytest.raises(RequestExpiredError, match="expired"):
        submit_request(request, config=make_config(), sender=sender, now=late)
    assert calls == []
    # Boundary instant itself is still valid.
    exact = datetime.fromtimestamp((NOW_MS + 60_000) / 1000.0, tz=timezone.utc)
    ack = submit_request(request, config=make_config(), sender=sender, now=exact)
    assert ack["order_id"] == "ord-1"
    assert len(calls) == 1


# -- unit: kill switch independent of decision layer --
def test_kill_switch_halts_even_healthy_decisions():
    risk = approved_decision()
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    calls: list[dict] = []

    def sender(url, payload, headers, timeout):
        calls.append(payload)
        return {"order_id": "ord-1"}

    with pytest.raises(InvalidRequestError, match="kill switch"):
        submit_request(
            request, config=make_config(), sender=sender, now=moment(), kill_switch_active=True
        )
    assert calls == []


# -- unit: auth, replay protection, secrets --
def test_signature_roundtrip_and_replay_protection():
    risk = approved_decision()
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    payload = request_payload(request, NOW_MS, "nonce_1")
    signature = sign_payload("unit-secret", NOW_MS, "nonce_1", payload)
    seen: set[str] = set()
    assert verify_webhook_signature(
        signature=signature, secret="unit-secret", timestamp_ms=NOW_MS,
        nonce="nonce_1", payload=payload, now_ms=NOW_MS, seen_nonces=seen,
    ) is True
    # Replay of the same nonce is refused.
    assert verify_webhook_signature(
        signature=signature, secret="unit-secret", timestamp_ms=NOW_MS,
        nonce="nonce_1", payload=payload, now_ms=NOW_MS, seen_nonces=seen,
    ) is False
    # Tampered body fails.
    tampered = dict(payload)
    tampered["quantity"] = float(payload["quantity"]) + 1.0
    assert verify_webhook_signature(
        signature=signature, secret="unit-secret", timestamp_ms=NOW_MS,
        nonce="nonce_2", payload=tampered, now_ms=NOW_MS,
    ) is False
    # Stale timestamp fails.
    assert verify_webhook_signature(
        signature=signature, secret="unit-secret", timestamp_ms=NOW_MS,
        nonce="nonce_3", payload=payload, now_ms=NOW_MS + 600_000,
    ) is False
    # Wrong secret fails.
    assert verify_webhook_signature(
        signature=signature, secret="other-secret", timestamp_ms=NOW_MS,
        nonce="nonce_4", payload=payload, now_ms=NOW_MS,
    ) is False


def test_secrets_never_appear_in_wire_or_source():
    import pathlib as _pathlib

    risk = approved_decision()
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    payload = request_payload(request, NOW_MS, "nonce_9")
    signature = sign_payload("super-secret-value", NOW_MS, "nonce_9", payload)
    headers = {"X-Signature": signature, "X-Timestamp": str(NOW_MS)}
    assert "super-secret-value" not in str(payload)
    assert "super-secret-value" not in str(headers)
    source = (_pathlib.Path(__file__).resolve().parent.parent / "execution" / "n8n_client.py").read_text(
        encoding="utf-8"
    )
    assert "super-secret-value" not in source
    assert "print(" not in source
    assert "logging" not in source


def test_config_separates_paper_and_production(monkeypatch):
    monkeypatch.setenv("HERMES_EXEC_ENV", "paper")
    monkeypatch.setenv("N8N_WEBHOOK_URL_PAPER", "https://n8n.local/paper")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET_PAPER", "paper-secret")
    monkeypatch.delenv("N8N_WEBHOOK_URL_PROD", raising=False)
    monkeypatch.delenv("N8N_WEBHOOK_SECRET_PROD", raising=False)
    config = ExecutionConfig.from_environment()
    assert config.environment == "paper"
    # Ambiguity fails loudly instead of guessing.
    monkeypatch.setenv("N8N_WEBHOOK_URL_PROD", "https://n8n.local/prod")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET_PROD", "prod-secret")
    with pytest.raises(ValueError, match="both paper and production"):
        ExecutionConfig.from_environment()
    monkeypatch.setenv("HERMES_EXEC_ENV", "sideways")
    with pytest.raises(ValueError, match="HERMES_EXEC_ENV"):
        ExecutionConfig.from_environment()


# -- contract: independent boundary validation + webhook schema --
def test_boundary_validates_every_field_independently():
    risk = approved_decision()
    good = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    calls: list[dict] = []

    def sender(url, payload, headers, timeout):
        calls.append(payload)
        return {"order_id": "ord-1"}

    bad_symbol = dataclasses.replace(good, symbol="  ")
    with pytest.raises(InvalidRequestError):
        submit_request(bad_symbol, config=make_config(), sender=sender, now=moment())
    bad_side = dataclasses.replace(good, side="HOLD")
    with pytest.raises(InvalidRequestError):
        submit_request(bad_side, config=make_config(), sender=sender, now=moment())
    bad_qty = dataclasses.replace(good, quantity=0.0)
    with pytest.raises(InvalidRequestError):
        submit_request(bad_qty, config=make_config(), sender=sender, now=moment())
    bad_type = dataclasses.replace(good, order_type="STOP")
    with pytest.raises(InvalidRequestError):
        submit_request(bad_type, config=make_config(), sender=sender, now=moment())
    bad_key = dataclasses.replace(good, idempotency_key="other-key")
    with pytest.raises(InvalidRequestError):
        submit_request(bad_key, config=make_config(), sender=sender, now=moment())
    assert calls == []


def test_webhook_schema_has_contract_fields():
    risk = approved_decision()
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    payload = request_payload(request, NOW_MS, "nonce_schema")
    for field in (
        "execution_id", "risk_decision_id", "symbol", "side", "quantity",
        "order_type", "protection", "expiry", "idempotency_key",
        "timestamp_ms", "nonce",
    ):
        assert field in payload
    assert payload["idempotency_key"] == request.execution_id
    assert payload["quantity"] == request.quantity


# -- unit: order manager state + idempotency --
def test_duplicate_delivery_does_not_double_submit(tmp_path):
    risk = approved_decision()
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    manager = ExecutionOrderManager(tmp_path / "exec.sqlite3")
    calls: list[dict] = []

    def sender(url, payload, headers, timeout):
        calls.append(payload)
        return {"order_id": "ord-100"}

    first = manager.submit_once(request, config=make_config(), sender=sender, now=moment())
    assert first["duplicate_suppressed"] is False
    second = manager.submit_once(request, config=make_config(), sender=sender, now=moment())
    assert second["duplicate_suppressed"] is True
    assert len(calls) == 1
    assert manager.get(request.execution_id)["state"] == "ACKED"
    manager.close()


def test_state_lifecycle_and_no_delete(tmp_path):
    import sqlite3

    risk = approved_decision()
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    manager = ExecutionOrderManager(tmp_path / "exec.sqlite3")
    manager.register(request)
    assert manager.get(request.execution_id)["state"] == "PENDING"
    manager.mark_acked(request.execution_id, "ord-7")
    assert manager.get(request.execution_id)["state"] == "ACKED"
    manager.mark_filled(request.execution_id)
    assert manager.get(request.execution_id)["state"] == "FILLED"
    assert manager.list_by_state("FILLED")[0]["execution_id"] == request.execution_id
    with pytest.raises(KeyError):
        manager.get("exec-missing")
    with pytest.raises(sqlite3.IntegrityError):
        manager.connection.execute(
            "DELETE FROM execution_requests WHERE execution_id = ?", (request.execution_id,)
        )
    manager.close()


# -- unit: reconciliation --
def test_reconcile_matched_and_missing():
    report = reconcile(
        [{"order_id": "ord-1", "quantity": 2.0, "status": "SUBMITTED"}],
        [{"order_id": "ord-1", "quantity": 2.0, "status": "SUBMITTED"}],
    )
    assert report["action"] == "ok"
    assert len(report["matched"]) == 1
    report2 = reconcile(
        [{"order_id": "ord-2", "quantity": 1.0, "status": "SUBMITTED"}],
        [],
    )
    assert report2["action"] == "ok"
    assert len(report2["missing_on_exchange"]) == 1


def test_reconcile_freezes_on_unknown_or_mismatch():
    report = reconcile([], [{"order_id": "ord-X", "quantity": 1.0, "status": "FILLED"}])
    assert report["action"] == "freeze_new_entries"
    assert len(report["unknown_locally"]) == 1
    report2 = reconcile(
        [{"order_id": "ord-1", "quantity": 2.0, "status": "SUBMITTED"}],
        [{"order_id": "ord-1", "quantity": 5.0, "status": "SUBMITTED"}],
    )
    assert report2["action"] == "freeze_new_entries"
    assert len(report2["mismatched"]) == 1


# -- integration: full entry flow --
def test_full_entry_flow_to_matched_reconciliation(tmp_path):
    engine = RiskEngine()
    risk = engine.evaluate(make_decision("dec-flow"), valid_context(), **base_account())
    assert risk.status == "APPROVED"
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    manager = ExecutionOrderManager(tmp_path / "exec.sqlite3")

    def sender(url, payload, headers, timeout):
        assert payload["quantity"] == risk.approved_quantity
        assert payload["idempotency_key"] == request.execution_id
        assert headers["X-Idempotency-Key"] == request.execution_id
        return {"order_id": "ord-flow", "status": "ACKED"}

    outcome = manager.submit_once(
        request, config=make_config(), sender=sender, now=moment(), risk_decision=risk
    )
    assert outcome["state"] == "ACKED"
    manager.mark_filled(request.execution_id)
    local = [
        {
            "order_id": "ord-flow",
            "execution_id": request.execution_id,
            "quantity": risk.approved_quantity,
            "status": "FILLED",
        }
    ]
    exchange = [{"order_id": "ord-flow", "quantity": risk.approved_quantity, "status": "FILLED"}]
    report = reconcile(local, exchange)
    assert report["action"] == "ok"
    assert len(report["matched"]) == 1
    manager.close()


def test_n8n_outage_expires_without_queueing(tmp_path):
    risk = approved_decision("dec-outage")
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment())
    manager = ExecutionOrderManager(tmp_path / "exec.sqlite3")
    calls: list[dict] = []

    def dead_sender(url, payload, headers, timeout):
        calls.append(payload)
        raise OSError("connection refused")

    with pytest.raises(N8nUnavailableError):
        manager.submit_once(request, config=make_config(), sender=dead_sender, now=moment())
    assert manager.get(request.execution_id)["state"] == "EXPIRED"
    # Retry returns the cached EXPIRED outcome without resending.
    cached = manager.submit_once(request, config=make_config(), sender=dead_sender, now=moment())
    assert cached["state"] == "EXPIRED"
    assert cached["duplicate_suppressed"] is True
    assert len(calls) == 1
    manager.close()


# -- integration probe: Module 6 existing-position semantics (no code change) --
def test_close_intent_while_holding_is_currently_rejected():
    # Characterization of the open Module 6 question: risk currently rejects
    # ANY decision while position_qty != 0, including a SELL that would close
    # a long. Module 8's lifecycle (entry vs close/reduce) must resolve whether
    # close orders bypass, narrow, or keep this rule. This test pins current
    # behavior so the resolution is a deliberate contract change, not drift.
    engine = RiskEngine()
    holding = PortfolioState(position_qty=2.0, exposure_notional=200.0, available=True)
    context = valid_context(portfolio=holding)
    close_intent = make_decision("dec-close", action="SELL")
    result = engine.evaluate(close_intent, context, **base_account())
    assert result.status == "REJECTED"
    assert "existing position" in str(result.rejection_reason).lower()
    # Control: the same SELL while flat is evaluated on its own merits.
    flat = engine.evaluate(make_decision("dec-close-flat", action="SELL"), valid_context(), **base_account())
    assert flat.status in ("APPROVED", "REJECTED")
    assert "existing position" not in str(flat.rejection_reason or "").lower()


def test_no_llm_or_sizing_in_execution():
    import pathlib as _pathlib

    root = _pathlib.Path(__file__).resolve().parent.parent / "execution"
    for path in root.glob("*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                lowered = stripped.lower()
                assert "llm" not in lowered, str(path)
                assert "openai" not in lowered, str(path)
                assert "anthropic" not in lowered, str(path)
                assert "strategies" not in lowered, str(path)
        body = "\n".join(lines).lower()
        assert "risk_per_trade" not in body, str(path)
        assert "calculate_quantity" not in body, str(path)
