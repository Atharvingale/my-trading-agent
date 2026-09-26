"""n8n webhook client: verified, signed, idempotent submission (Module 7).

Why this shape: n8n is an orchestration boundary, not a safety layer. This
module never re-derives risk parameters — quantity is copied verbatim from
the sealed RiskDecision and re-checked before submission. Webhook calls carry
an HMAC signature with timestamp/nonce replay protection, and every request
carries a stable idempotency key so retries cannot double-submit. Secrets are
never logged anywhere in this module.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4


ORDER_TYPES = ("MARKET", "LIMIT")
SIDES = ("BUY", "SELL")


class InvalidRequestError(ValueError):
    """Raised when a request fails independent boundary validation."""


class RequestExpiredError(ValueError):
    """Raised when an instruction is past expiry — never submitted late."""


class N8nUnavailableError(RuntimeError):
    """Raised when n8n cannot be reached — the request expires, never queues."""


@dataclass(frozen=True)
class ExecutionRequest:
    execution_id: str
    risk_decision_id: str
    symbol: str
    side: str
    quantity: float
    order_type: str
    protection: dict[str, Any]
    expiry: datetime
    idempotency_key: str


@dataclass(frozen=True)
class ExecutionConfig:
    webhook_url: str
    webhook_secret: str
    environment: str
    request_timeout_seconds: int = 15
    default_expiry_seconds: int = 120
    max_skew_seconds: int = 300

    def __post_init__(self) -> None:
        # Fail-closed construction: an ambiguous or incomplete execution
        # config raises here, never as a silent wrong-environment submit.
        if not self.webhook_url.strip():
            raise ValueError("webhook_url must be non-empty")
        if not self.webhook_secret.strip():
            raise ValueError("webhook_secret must be non-empty")
        if self.environment not in ("paper", "production"):
            raise ValueError("environment must be paper or production")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if self.default_expiry_seconds <= 0:
            raise ValueError("default_expiry_seconds must be positive")
        if self.max_skew_seconds <= 0:
            raise ValueError("max_skew_seconds must be positive")

    @staticmethod
    def from_environment() -> ExecutionConfig:
        """Load paper/production config; fail loudly on ambiguity.

        Exactly one credential pair may be present, matching HERMES_EXEC_ENV.
        Paper and production credentials live in separate variables so a
        misconfigured host cannot silently trade production.
        """
        env = str(os.environ.get("HERMES_EXEC_ENV", "")).strip().lower()
        if env not in ("paper", "production"):
            raise ValueError("HERMES_EXEC_ENV must be exactly paper or production")
        paper_url = str(os.environ.get("N8N_WEBHOOK_URL_PAPER", "")).strip()
        paper_secret = str(os.environ.get("N8N_WEBHOOK_SECRET_PAPER", "") or "")
        prod_url = str(os.environ.get("N8N_WEBHOOK_URL_PROD", "")).strip()
        prod_secret = str(os.environ.get("N8N_WEBHOOK_SECRET_PROD", "") or "")
        paper_present = bool(paper_url or paper_secret.strip())
        prod_present = bool(prod_url or prod_secret.strip())
        if paper_present and prod_present:
            raise ValueError("both paper and production n8n credentials are set: refusing to guess")
        if env == "paper":
            if not paper_url or not paper_secret.strip():
                raise ValueError("paper n8n webhook URL and secret must both be set")
            return ExecutionConfig(
                webhook_url=paper_url, webhook_secret=paper_secret, environment="paper"
            )
        if not prod_url or not prod_secret.strip():
            raise ValueError("production n8n webhook URL and secret must both be set")
        return ExecutionConfig(
            webhook_url=prod_url, webhook_secret=prod_secret, environment="production"
        )


def build_request(
    risk_decision: Any,
    *,
    symbol: str,
    side: str,
    now: datetime,
    expiry_seconds: int = 120,
    order_type: str = "MARKET",
) -> ExecutionRequest:
    """Seal a risk-approved decision into a submittable request.

    Quantity is copied exactly from the sealed decision — this function takes
    no quantity parameter so no caller can resize or round it.
    """
    from risk.engine import verify_integrity

    if verify_integrity(risk_decision) is False:
        raise InvalidRequestError("RiskDecision integrity check failed")
    if str(getattr(risk_decision, "status", "")) != "APPROVED":
        raise InvalidRequestError("risk decision is not APPROVED")
    token = str(symbol).strip().upper()
    if not token:
        raise InvalidRequestError("symbol must be non-empty")
    sealed_symbol = ""
    exposure = getattr(risk_decision, "exposure_after", None)
    if isinstance(exposure, dict) and "symbol" in exposure:
        sealed_symbol = str(exposure["symbol"]).strip().upper()
    if sealed_symbol and sealed_symbol != token:
        raise InvalidRequestError(
            "symbol %r does not match sealed decision symbol %r" % (token, sealed_symbol)
        )
    action = str(side).strip().upper()
    if action not in SIDES:
        raise InvalidRequestError("side must be BUY or SELL")
    quantity = getattr(risk_decision, "approved_quantity", None)
    if isinstance(quantity, bool) or not isinstance(quantity, (float, int)):
        raise InvalidRequestError("sealed quantity is not a number")
    if float(quantity) <= 0:
        raise InvalidRequestError("sealed quantity is not positive")
    kind = str(order_type).strip().upper()
    if kind not in ORDER_TYPES:
        raise InvalidRequestError("order_type must be MARKET or LIMIT")
    if not isinstance(now, datetime):
        raise InvalidRequestError("now must be a datetime")
    if expiry_seconds <= 0:
        raise InvalidRequestError("expiry_seconds must be positive")
    moment = now
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    expiry = moment + timedelta(seconds=int(expiry_seconds))
    execution_id = "exec_" + str(uuid4()).replace("-", "")[:16]
    protection: dict[str, Any] = {}
    protection["stop"] = float(getattr(risk_decision, "stop"))
    protection["target"] = float(getattr(risk_decision, "target"))
    return ExecutionRequest(
        execution_id=execution_id,
        risk_decision_id=str(getattr(risk_decision, "risk_decision_id")),
        symbol=token,
        side=action,
        quantity=float(quantity),
        order_type=kind,
        protection=protection,
        expiry=expiry,
        idempotency_key=execution_id,
    )


def assert_quantity_matches(request: ExecutionRequest, risk_decision: Any) -> None:
    """Defense in depth: the request must equal the sealed quantity exactly.

    No tolerance, no rounding — even 1e-9 of drift raises. Called by
    build_request implicitly (no quantity parameter exists) and re-checked on
    submit when the caller passes the sealed decision alongside.
    """
    sealed = getattr(risk_decision, "approved_quantity", None)
    if isinstance(sealed, bool) or not isinstance(sealed, (float, int)):
        raise InvalidRequestError("sealed quantity is not a number")
    if float(request.quantity) != float(sealed):
        raise InvalidRequestError(
            "request quantity %r does not exactly match sealed %r" % (
                float(request.quantity), float(sealed))
        )


def request_payload(request: ExecutionRequest, timestamp_ms: int, nonce: str) -> dict[str, Any]:
    """Render the signed webhook body; deterministic for a fixed timestamp."""
    body: dict[str, Any] = {}
    body["execution_id"] = request.execution_id
    body["risk_decision_id"] = request.risk_decision_id
    body["symbol"] = request.symbol
    body["side"] = request.side
    body["quantity"] = request.quantity
    body["order_type"] = request.order_type
    protection: dict[str, Any] = {}
    for key in request.protection:
        protection[key] = request.protection[key]
    body["protection"] = protection
    body["expiry"] = request.expiry.isoformat()
    body["idempotency_key"] = request.idempotency_key
    body["timestamp_ms"] = int(timestamp_ms)
    body["nonce"] = str(nonce)
    return body


def sign_payload(secret: str, timestamp_ms: int, nonce: str, payload: dict[str, Any]) -> str:
    """HMAC-SHA256 over the canonical body; the secret never leaves here."""
    canonical = "%d\n%s\n%s" % (
        int(timestamp_ms),
        str(nonce),
        json.dumps(payload, separators=(",", ":"), sort_keys=True, allow_nan=False),
    )
    digest = hmac.new(
        str(secret).encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return digest


def verify_webhook_signature(
    *,
    signature: str,
    secret: str,
    timestamp_ms: int,
    nonce: str,
    payload: dict[str, Any],
    now_ms: int,
    max_skew_seconds: int = 300,
    seen_nonces: set[str] | None = None,
) -> bool:
    """Check signature, freshness, and nonce reuse (replay protection)."""
    skew = abs(int(now_ms) - int(timestamp_ms)) / 1000.0
    if skew > float(max_skew_seconds):
        return False
    if seen_nonces is not None and str(nonce) in seen_nonces:
        return False
    expected = sign_payload(secret, int(timestamp_ms), str(nonce), payload)
    if hmac.compare_digest(str(signature), expected) is False:
        return False
    if seen_nonces is not None:
        seen_nonces.add(str(nonce))
    return True


Sender = Callable[[str, dict[str, Any], dict[str, str], int], dict[str, Any]]


def default_sender(
    url: str, payload: dict[str, Any], headers: dict[str, str], timeout_seconds: int
) -> dict[str, Any]:
    """Stdlib HTTPS POST; used only when tests do not inject a fake sender."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    http_request = urllib.request.Request(url, data=body, method="POST")
    for key in headers:
        http_request.add_header(key, headers[key])
    with urllib.request.urlopen(http_request, timeout=int(timeout_seconds)) as response:
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise N8nUnavailableError("n8n returned a non-object acknowledgement")
    return parsed


def submit_request(
    request: ExecutionRequest,
    *,
    config: ExecutionConfig,
    sender: Sender | None = None,
    now: datetime,
    kill_switch_active: bool = False,
    risk_decision: Any = None,
) -> dict[str, Any]:
    """Submit one request exactly once; fail closed on every abnormal path.

    Kill switch is checked first so trading halts even when the decision layer
    itself is hung — the caller passes the switch state independently rather
    than asking Hermes whether it feels healthy.
    """
    if kill_switch_active is True:
        raise InvalidRequestError("kill switch active: submission refused")
    if risk_decision is not None:
        from risk.engine import verify_integrity

        if verify_integrity(risk_decision) is False:
            raise InvalidRequestError("RiskDecision integrity check failed")
        assert_quantity_matches(request, risk_decision)
    moment = now
    if not isinstance(moment, datetime):
        raise InvalidRequestError("now must be a datetime")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    expiry = request.expiry
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if moment > expiry:
        raise RequestExpiredError("ExecutionRequest %s expired at %s" % (
            request.execution_id, request.expiry.isoformat()))
    _validate_fields(request)
    timestamp_ms = int(moment.timestamp() * 1000)
    nonce = "nonce_" + request.execution_id
    payload = request_payload(request, timestamp_ms, nonce)
    signature = sign_payload(config.webhook_secret, timestamp_ms, nonce, payload)
    headers: dict[str, str] = {}
    headers["Content-Type"] = "application/json"
    headers["X-Signature"] = signature
    headers["X-Timestamp"] = str(timestamp_ms)
    headers["X-Nonce"] = nonce
    headers["X-Idempotency-Key"] = request.idempotency_key
    deliver = sender if sender is not None else default_sender
    try:
        return deliver(config.webhook_url, payload, headers, config.request_timeout_seconds)
    except RequestExpiredError:
        raise
    except InvalidRequestError:
        raise
    except Exception as exc:
        raise N8nUnavailableError("n8n unreachable for %s" % request.execution_id) from exc


def _validate_fields(request: ExecutionRequest) -> None:
    # Independent boundary validation: never trust upstream checks alone.
    if not request.execution_id.strip():
        raise InvalidRequestError("execution_id must be non-empty")
    if not request.risk_decision_id.strip():
        raise InvalidRequestError("risk_decision_id must be non-empty")
    if not request.symbol.strip():
        raise InvalidRequestError("symbol must be non-empty")
    if request.side not in SIDES:
        raise InvalidRequestError("side must be BUY or SELL")
    if isinstance(request.quantity, bool) or not isinstance(request.quantity, (float, int)):
        raise InvalidRequestError("quantity must be a number")
    if float(request.quantity) <= 0:
        raise InvalidRequestError("quantity must be positive")
    if request.order_type not in ORDER_TYPES:
        raise InvalidRequestError("order_type must be MARKET or LIMIT")
    if not request.idempotency_key.strip():
        raise InvalidRequestError("idempotency_key must be non-empty")
    if request.idempotency_key != request.execution_id:
        raise InvalidRequestError("idempotency_key must equal execution_id")
    if not isinstance(request.expiry, datetime):
        raise InvalidRequestError("expiry must be a datetime")
