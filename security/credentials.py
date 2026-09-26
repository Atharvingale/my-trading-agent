"""Centralized credential loading with enforced separation (Module 13).

Why one loader: paper/testnet and production credentials live in disjoint
variable pairs, and any ambiguity — both pairs present, or keys without the
read-only scope attestation — fails loudly instead of silently picking one.
Binance keys additionally require the withdrawals-disabled attestation,
because minimum permissions (read-only, no withdrawals) are non-negotiable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BinanceCredentials:
    environment: str
    api_key: str | None
    withdrawals_disabled: bool
    scope: str

    def has_keys(self) -> bool:
        return self.api_key is not None and bool(self.api_key.strip())


def load_binance_credentials() -> BinanceCredentials:
    """Load exactly one Binance credential scope from the environment.

    HERMES_EXEC_ENV selects paper or production. Each scope has its own
    KEY/SECRET pair; both pairs present is ambiguity and raises. Keys without
    HERMES_BINANCE_KEY_SCOPE=read-only or without
    BINANCE_WITHDRAWALS_DISABLED=1 raise — withdrawals must be provably off.
    No keys at all is valid anonymous public-data mode.
    """
    env = str(os.environ.get("HERMES_EXEC_ENV", "")).strip().lower()
    if env not in ("paper", "production"):
        raise ValueError("HERMES_EXEC_ENV must be exactly paper or production")
    paper_key = str(os.environ.get("BINANCE_API_KEY_PAPER", "") or "").strip()
    paper_secret = str(os.environ.get("BINANCE_API_SECRET_PAPER", "") or "").strip()
    prod_key = str(os.environ.get("BINANCE_API_KEY_PROD", "") or "").strip()
    prod_secret = str(os.environ.get("BINANCE_API_SECRET_PROD", "") or "").strip()
    paper_present = bool(paper_key or paper_secret)
    prod_present = bool(prod_key or prod_secret)
    if paper_present and prod_present:
        raise ValueError("both paper and production Binance credentials are set: refusing to guess")
    if env == "paper":
        selected_key = paper_key or None
        selected_secret = paper_secret or None
    else:
        selected_key = prod_key or None
        selected_secret = prod_secret or None
    if not selected_key and not selected_secret:
        return BinanceCredentials(
            environment=env, api_key=None, withdrawals_disabled=True, scope="anonymous"
        )
    if bool(selected_key) != bool(selected_secret):
        raise ValueError("Binance API key and secret must be set together")
    scope = str(os.environ.get("HERMES_BINANCE_KEY_SCOPE", "")).strip().lower()
    if scope != "read-only":
        raise ValueError("HERMES_BINANCE_KEY_SCOPE must be read-only when keys are set")
    flag = str(os.environ.get("BINANCE_WITHDRAWALS_DISABLED", "")).strip().lower()
    if flag not in ("1", "true", "yes"):
        raise ValueError("BINANCE_WITHDRAWALS_DISABLED must attest withdrawals are off")
    return BinanceCredentials(
        environment=env, api_key=selected_key, withdrawals_disabled=True, scope="read-only"
    )


def audit_market_data_settings(settings: Any) -> list[str]:
    """Audit an existing market-data Settings object without changing it.

    Returns findings (empty means clean). Keys without scope attestation,
    non-loopback binds without token+TLS, and insecure-remote flags are each
    reported so operators fix config instead of shipping silent exposure.
    """
    findings: list[str] = []
    api_key = str(getattr(settings, "api_key", None) or "").strip()
    api_secret = str(getattr(settings, "api_secret", None) or "").strip()
    if bool(api_key) != bool(api_secret):
        findings.append("BINANCE_API_KEY and BINANCE_API_SECRET must be set together")
    if api_key or api_secret:
        scope = str(os.environ.get("HERMES_BINANCE_KEY_SCOPE", "")).strip().lower()
        if scope != "read-only":
            findings.append("keys present without HERMES_BINANCE_KEY_SCOPE=read-only")
        flag = str(os.environ.get("BINANCE_WITHDRAWALS_DISABLED", "")).strip().lower()
        if flag not in ("1", "true", "yes"):
            findings.append("keys present without BINANCE_WITHDRAWALS_DISABLED attestation")
    host = str(getattr(settings, "api_host", "127.0.0.1") or "127.0.0.1").strip().lower()
    loopback = host in ("127.0.0.1", "localhost", "::1")
    if loopback is False:
        token = str(getattr(settings, "api_token", None) or "").strip()
        if not token:
            findings.append("non-loopback bind without MARKET_DATA_API_TOKEN")
        cert = getattr(settings, "api_tls_certfile", None)
        key = getattr(settings, "api_tls_keyfile", None)
        insecure = bool(getattr(settings, "api_allow_insecure_remote", False))
        if (not cert or not key) and insecure is False:
            findings.append("non-loopback bind without TLS cert/key")
        if insecure:
            findings.append("insecure remote explicitly allowed; review before production")
    return findings
