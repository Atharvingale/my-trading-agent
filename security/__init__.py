"""Cross-cutting security bar (Module 13).

Centralized credential loading with paper/production separation, secret
redaction for every log line, and an audit helper for existing settings
objects. Secrets live in the environment, never in source or logs.
"""

from security.credentials import BinanceCredentials, audit_market_data_settings, load_binance_credentials
from security.redaction import SecretFilter, redact, scrub_mapping

__all__ = [
    "BinanceCredentials",
    "SecretFilter",
    "audit_market_data_settings",
    "load_binance_credentials",
    "redact",
    "scrub_mapping",
]
