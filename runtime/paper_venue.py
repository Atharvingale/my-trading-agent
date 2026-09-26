"""In-process paper venue behind the real n8n boundary (integration).

Why a stub transport, not a stub boundary: HMAC signing, replay protection,
idempotency, expiry, and exact-quantity checks all execute for real. Only the
last hop — HTTPS to an n8n server — is replaced by a direct call into a
verifier that routes approved quantities into a PaperEngine. No live Binance
path exists anywhere in this file.
"""

from __future__ import annotations

from typing import Any, Mapping

from execution.n8n_client import verify_webhook_signature
from paper_trading.engine import PaperEngine
from paper_trading.simulator import PaperOrder


class PaperN8nServer:
    """Verifying paper endpoint: signature, replay, idempotency, then fills."""

    def __init__(self, paper: PaperEngine | None = None, *, max_skew_seconds: int = 300) -> None:
        self.paper = paper if paper is not None else PaperEngine()
        self.max_skew_seconds = int(max_skew_seconds)
        self.seen_nonces: set[str] = set()
        self.seen_idempotency: dict[str, dict[str, Any]] = {}
        self.quotes: dict[str, dict[str, float]] = {}

    def set_quote(self, symbol: str, bid: float, ask: float, depth_qty: float) -> None:
        token = str(symbol).strip().upper()
        if bid <= 0 or ask < bid or depth_qty < 0:
            raise ValueError("invalid paper quote")
        self.quotes[token] = {"bid": float(bid), "ask": float(ask), "depth_qty": float(depth_qty)}

    def handle(
        self, payload: Mapping[str, Any], headers: Mapping[str, str], secret: str, now_ms: int
    ) -> dict[str, Any]:
        """Verify then fill; duplicates return the cached ack without refilling."""
        body: dict[str, Any] = {}
        for key in payload:
            body[key] = payload[key]
        key = str(body.get("idempotency_key", "")).strip()
        if key and key in self.seen_idempotency:
            cached: dict[str, Any] = {}
            for cached_key in self.seen_idempotency[key]:
                cached[cached_key] = self.seen_idempotency[key][cached_key]
            cached["duplicate_suppressed"] = True
            return cached
        ok = verify_webhook_signature(
            signature=str(headers.get("X-Signature", "")),
            secret=secret,
            timestamp_ms=int(headers.get("X-Timestamp", "0")),
            nonce=str(headers.get("X-Nonce", "")),
            payload=body,
            now_ms=int(now_ms),
            max_skew_seconds=self.max_skew_seconds,
            seen_nonces=self.seen_nonces,
        )
        if ok is False:
            raise ValueError("paper venue rejected the webhook signature")
        symbol = str(body.get("symbol", "")).strip().upper()
        quote = self.quotes.get(symbol)
        if quote is None:
            raise ValueError("paper venue has no quote for %s" % symbol)
        order = PaperOrder(
            order_id=str(body.get("execution_id")),
            symbol=symbol,
            side=str(body.get("side")),
            quantity=float(body.get("quantity", 0.0)),
            requested_price=None,
            timestamp_ms=int(body.get("timestamp_ms", 0)),
        )
        market = {"bid": quote["bid"], "ask": quote["ask"], "depth_qty": quote["depth_qty"]}
        report = self.paper.submit(order, market)
        ack: dict[str, Any] = {}
        ack["order_id"] = order.order_id
        ack["status"] = "ACKED"
        ack["filled_quantity"] = float(report.get("filled_quantity", 0.0))
        ack["fill_count"] = len(self.paper.fills)
        if key:
            stored: dict[str, Any] = {}
            for ack_key in ack:
                stored[ack_key] = ack[ack_key]
            self.seen_idempotency[key] = stored
        return ack


def make_paper_sender(server: PaperN8nServer, secret: str, now_ms: int):
    """Adapt the venue to the Module 7 Sender signature for paper runs."""

    def send(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
        _ = url
        _ = timeout
        return server.handle(payload, headers, secret, now_ms)

    return send
