"""n8n execution boundary (Module 7).

Orchestration boundary, never a safety layer: risk-approved decisions are
submitted verbatim to n8n, which validates schema and forwards to Binance.
Quantity is copied exactly from the sealed RiskDecision and verified, never
recalculated. Fail-closed on expiry, tampering, or n8n outage.
"""

from execution.n8n_client import (
    ExecutionConfig,
    ExecutionRequest,
    InvalidRequestError,
    N8nUnavailableError,
    RequestExpiredError,
    assert_quantity_matches,
    build_request,
    submit_request,
    verify_webhook_signature,
)
from execution.order_manager import ExecutionOrderManager
from execution.reconciliation import reconcile

__all__ = [
    "ExecutionConfig",
    "ExecutionRequest",
    "ExecutionOrderManager",
    "InvalidRequestError",
    "N8nUnavailableError",
    "RequestExpiredError",
    "assert_quantity_matches",
    "build_request",
    "reconcile",
    "submit_request",
    "verify_webhook_signature",
]
