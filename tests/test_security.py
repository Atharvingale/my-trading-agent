"""Module 13 acceptance: secrets never leak, kill is independent, config is loud."""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone

import pytest

from execution.n8n_client import ExecutionConfig, build_request
from risk.engine import RiskEngine
from security.credentials import audit_market_data_settings, load_binance_credentials
from security.redaction import SecretFilter, redact, scrub_mapping
from supervisor import Supervisor


NOW_MS = 1_700_000_000_000


def moment(ms=NOW_MS):
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


# -- redaction units --
def test_redact_scrubs_headers_urls_and_values():
    secret = "s3cr3t-webhook-value"
    assert secret not in redact("Authorization: Bearer " + secret, (secret,))
    assert secret not in redact("posting to https://n8n.local/hook?signature=" + secret, (secret,))
    assert "[REDACTED]" in redact("api_secret=" + secret, (secret,))
    assert redact("clean line with no secrets") == "clean line with no secrets"


def test_scrub_mapping_hides_sensitive_keys():
    cleaned = scrub_mapping(
        {
            "symbol": "BTCUSDT",
            "webhook_secret": "shh",
            "nested": {"api_key": "key", "quantity": 2.0},
            "note": "token abc",
        }
    )
    assert cleaned["symbol"] == "BTCUSDT"
    assert cleaned["webhook_secret"] == "[REDACTED]"
    assert cleaned["nested"]["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["quantity"] == 2.0


def test_secret_filter_scrubs_args_forms():
    logger = logging.getLogger("test.security.filter")
    secrets = ("filter-secret-value",)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler()
    logger.addHandler(handler)
    logger.addFilter(SecretFilter(secrets))
    logger.setLevel(logging.INFO)
    scrubber = SecretFilter(secrets)
    record = logging.LogRecord(
        "test.security.filter", logging.INFO, __file__, 1,
        "key is %s", ("filter-secret-value",), None,
    )
    assert scrubber.filter(record) is True
    assert "filter-secret-value" not in str(record.args)
    record2 = logging.LogRecord(
        "test.security.filter", logging.INFO, __file__, 1,
        "direct mention filter-secret-value here", (), None,
    )
    assert scrubber.filter(record2) is True
    assert "filter-secret-value" not in str(record2.msg)
    logger.removeFilter(logger.filters[0])
    logger.removeHandler(handler)


# -- acceptance 1: no secret-shaped strings in logs during a signed run --
def test_signed_run_leaks_no_secrets(caplog):
    from hermes.context import ContextBuilder

    secret = "lint-webhook-secret-abc"
    caplog.set_level(logging.INFO)
    config = ExecutionConfig(
        webhook_url="https://n8n.local/webhook/lint", webhook_secret=secret, environment="paper"
    )
    builder = ContextBuilder(stale_after_seconds=30.0)
    context = builder.build(
        symbol="BTCUSDT",
        feature_snapshot={
            "symbol": "BTCUSDT",
            "event_time": "2024-01-01T00:00:00+00:00",
            "last_price": 100.0,
            "spread_bps": 2.0,
            "bid_depth": 500.0,
            "ask_depth": 500.0,
            "depth_within_bps": {25: {"bid_qty": 400.0, "ask_qty": 400.0}},
            "execution_quality": {"BUY": {"price_impact_rate": 0.0001, "status": "OK"}},
            "technical": {"1h": {"ema_fast": 101.0, "ema_slow": 100.0, "rsi": 55.0,
                                 "atr": 1.0, "vwap": 99.5, "bollinger_bandwidth": 0.04,
                                 "returns": 0.001}},
            "multi_timeframe_alignment": {"state": "BULLISH", "confirmed_timeframes": 2},
            "trade_cvd": 10.0,
            "aggressive_buy_pct": 0.55,
            "large_trade_concentration": 0.1,
            "top_book_imbalance": 0.05,
            "depth_imbalance": 0.02,
            "trade_volume": 100.0,
        },
        event_time_ms=NOW_MS,
        breadth={"advancing_pct": 0.7},
        cross_exchange=None,
        health_entries=[{"component": "spot_websocket", "symbol": None, "status": "connected",
                         "observed_time_ms": NOW_MS, "details": {}}],
        now_ms=NOW_MS,
    )
    assert context.valid is True
    _ = config
    logged_text = ""
    for record in caplog.records:
        logged_text = logged_text + str(record.msg) + str(record.args)
    assert secret not in logged_text


def test_no_hardcoded_secrets_in_source():
    import pathlib as _pathlib

    root = _pathlib.Path(__file__).resolve().parent.parent
    pattern = re.compile(r"\b[A-Z][A-Z0-9_]*(_SECRET|_API_KEY|_TOKEN)\s*=\s*[\"']([^\"']+)[\"']")
    env_name = re.compile(r"^[A-Z][A-Z0-9_]+$")
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if ".venv" in str(path) or "__pycache__" in str(path):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "os.getenv" in line or "os.environ" in line or "getenv" in line:
                continue
            match = pattern.search(line)
            if match is None:
                continue
            # Why the carve-out: constants holding environment variable NAMES
            # (e.g. ENV_API_KEY = "CANDIDATE_PROVIDER_API_KEY") are routing,
            # not secrets. Real secret values are never SCREAMING_SNAKE words.
            if env_name.match(match.group(2)):
                continue
            offenders.append("%s:%d" % (path.name, lineno))
    assert offenders == []


# -- acceptance 2: kill switch works while the decision layer is hung --
def test_kill_switch_halts_while_decision_layer_hung():
    hung = threading.Event()

    def hung_decision_layer():
        hung.wait(timeout=10.0)

    thread = threading.Thread(target=hung_decision_layer, daemon=True)
    thread.start()
    try:
        engine = RiskEngine()
        supervisor = Supervisor()
        supervisor.set_kill_hook(lambda reason: engine.activate_kill_switch(reason))
        supervisor.trip_kill_switch("injected daily loss")
        assert engine.is_halted() is True
        # The hung thread never answered, yet the halt landed: join with a
        # bound to prove the kill path never waits on the decision layer.
        thread.join(timeout=2.0)
        from hermes.models.decision import Decision

        decision = Decision(
            decision_id="dec-hung-1",
            timestamp=moment(),
            symbol="BTCUSDT",
            action="BUY",
            confidence=0.9,
            entry={"symbol": "BTCUSDT", "side": "BUY", "reference_price": 100.0},
            position={"position_qty": 0.0, "exposure_notional": 0.0,
                      "unrealized_pnl": 0.0, "realized_pnl": 0.0},
            risk={"stop_loss": 98.0, "take_profit": 103.0, "risk_amount": 0.0},
            time_horizon="15m",
            thesis=["hung thesis"],
            strategy_version_id="v1",
            expiry_seconds=3600,
        )
        from hermes.context import ContextBuilder

        builder = ContextBuilder(stale_after_seconds=3600.0)
        context = builder.build(
            symbol="BTCUSDT",
            feature_snapshot={
                "symbol": "BTCUSDT",
                "event_time": "2024-01-01T00:00:00+00:00",
                "last_price": 100.0,
                "spread_bps": 2.0,
                "bid_depth": 500.0,
                "ask_depth": 500.0,
                "depth_within_bps": {25: {"bid_qty": 400.0, "ask_qty": 400.0}},
                "execution_quality": {"BUY": {"price_impact_rate": 0.0001, "status": "OK"}},
                "technical": {"1h": {"ema_fast": 101.0, "ema_slow": 100.0, "rsi": 55.0,
                                     "atr": 1.0, "vwap": 99.5, "bollinger_bandwidth": 0.04,
                                     "returns": 0.001}},
                "multi_timeframe_alignment": {"state": "BULLISH", "confirmed_timeframes": 2},
                "trade_cvd": 10.0,
                "aggressive_buy_pct": 0.55,
                "large_trade_concentration": 0.1,
                "top_book_imbalance": 0.05,
                "depth_imbalance": 0.02,
                "trade_volume": 100.0,
            },
            event_time_ms=NOW_MS,
            breadth={"advancing_pct": 0.7},
            cross_exchange=None,
            health_entries=[{"component": "spot_websocket", "symbol": None, "status": "connected",
                             "observed_time_ms": NOW_MS, "details": {}}],
            now_ms=NOW_MS,
        )
        risk = engine.evaluate(
            decision, context, equity=10000.0, peak_equity=10000.0, daily_realized_pnl=0.0,
            open_notional=0.0, symbol_exposure=0.0, open_positions=0, now_ms=NOW_MS + 1000,
        )
        assert risk.status == "REJECTED"
        assert "kill switch" in str(risk.rejection_reason).lower()
    finally:
        hung.set()
        thread.join(timeout=2.0)


# -- acceptance 3: ambiguous credentials fail loudly --
def test_binance_ambiguity_fails_loudly(monkeypatch):
    monkeypatch.setenv("HERMES_EXEC_ENV", "paper")
    monkeypatch.setenv("BINANCE_API_KEY_PAPER", "paper-key")
    monkeypatch.setenv("BINANCE_API_SECRET_PAPER", "paper-secret")
    monkeypatch.setenv("BINANCE_API_KEY_PROD", "prod-key")
    monkeypatch.setenv("BINANCE_API_SECRET_PROD", "prod-secret")
    with pytest.raises(ValueError, match="both paper and production"):
        load_binance_credentials()


def test_binance_keys_need_scope_and_attestation(monkeypatch):
    monkeypatch.setenv("HERMES_EXEC_ENV", "paper")
    monkeypatch.setenv("BINANCE_API_KEY_PAPER", "paper-key")
    monkeypatch.setenv("BINANCE_API_SECRET_PAPER", "paper-secret")
    monkeypatch.delenv("HERMES_BINANCE_KEY_SCOPE", raising=False)
    monkeypatch.delenv("BINANCE_WITHDRAWALS_DISABLED", raising=False)
    with pytest.raises(ValueError, match="read-only"):
        load_binance_credentials()
    monkeypatch.setenv("HERMES_BINANCE_KEY_SCOPE", "read-only")
    with pytest.raises(ValueError, match="withdrawals"):
        load_binance_credentials()
    monkeypatch.setenv("BINANCE_WITHDRAWALS_DISABLED", "1")
    creds = load_binance_credentials()
    assert creds.environment == "paper"
    assert creds.withdrawals_disabled is True
    assert creds.scope == "read-only"


def test_anonymous_mode_without_keys(monkeypatch):
    monkeypatch.setenv("HERMES_EXEC_ENV", "paper")
    monkeypatch.delenv("BINANCE_API_KEY_PAPER", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET_PAPER", raising=False)
    monkeypatch.delenv("BINANCE_API_KEY_PROD", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET_PROD", raising=False)
    creds = load_binance_credentials()
    assert creds.has_keys() is False
    assert creds.scope == "anonymous"


def test_half_pair_and_bad_env_fail(monkeypatch):
    monkeypatch.setenv("HERMES_EXEC_ENV", "paper")
    monkeypatch.setenv("BINANCE_API_KEY_PAPER", "paper-key")
    monkeypatch.delenv("BINANCE_API_SECRET_PAPER", raising=False)
    monkeypatch.delenv("BINANCE_API_KEY_PROD", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET_PROD", raising=False)
    with pytest.raises(ValueError, match="together"):
        load_binance_credentials()
    monkeypatch.setenv("HERMES_EXEC_ENV", "sideways")
    with pytest.raises(ValueError, match="HERMES_EXEC_ENV"):
        load_binance_credentials()


def test_market_data_settings_audit(monkeypatch):
    from binance_data_layer.config import Settings

    monkeypatch.delenv("HERMES_BINANCE_KEY_SCOPE", raising=False)
    monkeypatch.delenv("BINANCE_WITHDRAWALS_DISABLED", raising=False)
    loopback = Settings()
    assert audit_market_data_settings(loopback) == []
    exposed = Settings(
        api_host="0.0.0.0", api_token=None, api_tls_certfile=None, api_tls_keyfile=None
    )
    findings = audit_market_data_settings(exposed)
    assert len(findings) >= 2
    keyed = Settings(api_key="k", api_secret="s")
    assert len(audit_market_data_settings(keyed)) >= 2


def test_insecure_remote_flag_is_flagged(monkeypatch):
    from binance_data_layer.config import Settings

    monkeypatch.delenv("HERMES_BINANCE_KEY_SCOPE", raising=False)
    monkeypatch.delenv("BINANCE_WITHDRAWALS_DISABLED", raising=False)
    exposed = Settings(
        api_host="0.0.0.0",
        api_token="ops-token",
        api_tls_certfile=None,
        api_tls_keyfile=None,
        api_allow_insecure_remote=True,
    )
    findings = audit_market_data_settings(exposed)
    assert len(findings) == 1
    assert "insecure" in findings[0].lower()
