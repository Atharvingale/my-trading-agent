"""Secret redaction for logs and diagnostics (Module 13).

Why a shared scrubber: no module may log API secrets, signed URLs, or auth
headers, so every value crossing a log boundary passes through here. Patterns
cover raw secret values, Bearer signatures, and signed-URL query parameters.
"""

from __future__ import annotations

import logging
import re
from typing import Any


REDACTED = "[REDACTED]"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Authorization headers and bearer tokens.
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/=]{8,}"),
    # Signed-URL query parameters (Binance signature, generic sig/token).
    re.compile(r"(?i)([?&](signature|sig|api[_-]?secret|token|key)=)[^&\s]*"),
    # Labeled secret assignments in free text.
    re.compile(r"(?i)((?:api[_-]?secret|webhook[_-]?secret|secret[_-]?key)\s*[:=]\s*)[^\s,;]+"),
    # Long hex/base64 blobs that look like keys (64+ chars).
    re.compile(r"\b[A-Fa-f0-9]{64,}\b"),
)

_SENSITIVE_KEYS = (
    "api_secret",
    "apisecret",
    "webhook_secret",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "token",
    "signature",
    "password",
)


def _scrub_match(match: re.Match[str]) -> str:
    # Why a function: some patterns have no capture group, so a fixed "\1"
    # replacement crashes on them. Keep the label prefix when present.
    prefix = match.group(1) if match.lastindex else ""
    return prefix + REDACTED


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Scrub patterns plus every known secret value from free text."""
    cleaned = str(text)
    for pattern in _PATTERNS:
        cleaned = pattern.sub(_scrub_match, cleaned)
    for secret in secrets:
        value = str(secret or "").strip()
        if len(value) >= 4 and value in cleaned:
            cleaned = cleaned.replace(value, REDACTED)
    return cleaned


def scrub_mapping(mapping: dict[str, Any], secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    """Return a copy with sensitive keys and secret values scrubbed."""
    cleaned: dict[str, Any] = {}
    for key in mapping:
        value = mapping[key]
        lowered = str(key).strip().lower().replace("-", "_")
        sensitive = False
        for marker in _SENSITIVE_KEYS:
            if marker in lowered:
                sensitive = True
        if sensitive:
            cleaned[key] = REDACTED
            continue
        if isinstance(value, str):
            cleaned[key] = redact(value, secrets)
        elif isinstance(value, dict):
            nested: dict[str, Any] = {}
            for inner in value:
                nested[inner] = value[inner]
            cleaned[key] = scrub_mapping(nested, secrets)
        else:
            cleaned[key] = value
    return cleaned


class SecretFilter(logging.Filter):
    """Logging filter scrubbing secrets from every record it touches."""

    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        known: list[str] = []
        for secret in secrets:
            value = str(secret or "").strip()
            if len(value) >= 4:
                known.append(value)
        self.secrets = tuple(known)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg), self.secrets)
        args = record.args
        if isinstance(args, dict):
            scrubbed: dict[str, Any] = {}
            for key in args:
                value = args[key]
                if isinstance(value, str):
                    scrubbed[key] = redact(value, self.secrets)
                else:
                    scrubbed[key] = value
            record.args = scrubbed
        elif isinstance(args, tuple):
            scrubbed_args: list[Any] = []
            for value in args:
                if isinstance(value, str):
                    scrubbed_args.append(redact(value, self.secrets))
                else:
                    scrubbed_args.append(value)
            record.args = tuple(scrubbed_args)
        return True
