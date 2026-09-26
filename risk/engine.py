"""Deterministic risk engine: the hard safety boundary (Module 6).

Why this shape: every BUY/SELL decision passes the same fixed rule order, so
a rejection always names the first failed check. HOLD never reaches execution
(it returns REJECTED with quantity zero as an auditable no-action record).
The approved quantity is sealed with a SHA-256 hash so Module 7 verifies the
exact bytes instead of trusting or rounding them. No LLM, no network, no
imports from strategies beyond types, nothing from execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from risk.limits import (
    RiskLimits,
    check_cooldown,
    check_concurrent_positions,
    check_daily_loss,
    check_drawdown,
    check_leverage,
    check_liquidity,
    check_portfolio_exposure,
    check_stop_distance,
    check_symbol_exposure,
)
from risk.position_sizing import calculate_quantity


@dataclass(frozen=True)
class RiskDecision:
    risk_decision_id: str
    decision_id: str
    status: str
    approved_quantity: float
    stop: float
    target: float
    exposure_after: dict[str, Any]
    rejection_reason: str | None
    integrity_hash: str = ""


def verify_integrity(decision: RiskDecision) -> bool:
    """Recompute the seal; True only when nothing was altered in transit."""
    return decision.integrity_hash == _seal(
        decision.risk_decision_id,
        decision.decision_id,
        decision.status,
        decision.approved_quantity,
        decision.stop,
        decision.target,
        decision.exposure_after,
        decision.rejection_reason,
    )


class RiskEngine:
    """Stateful boundary: kill switch, duplicate orders, stop-out cooldowns."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits if limits is not None else RiskLimits()
        self._halted = False
        self._halt_reason: str | None = None
        self._seen: set[str] = set()
        self._stopouts: dict[str, int] = {}

    # -- kill switch --
    def is_halted(self) -> bool:
        return self._halted

    def activate_kill_switch(self, reason: str) -> None:
        why = str(reason).strip()
        if not why:
            raise ValueError("kill-switch reason must be non-empty")
        self._halted = True
        self._halt_reason = why

    def clear_kill_switch(self, approver: str, rationale: str) -> None:
        who = str(approver).strip()
        if not who:
            raise ValueError("approver must be non-empty: no anonymous resume")
        why = str(rationale).strip()
        if not why:
            raise ValueError("rationale must be non-empty: no unexplained resume")
        self._halted = False
        self._halt_reason = None

    def note_stopout(self, symbol: str, timestamp_ms: int) -> None:
        token = str(symbol).strip().upper()
        if not token:
            raise ValueError("symbol must be non-empty")
        self._stopouts[token] = int(timestamp_ms)

    def evaluate(
        self,
        decision: Any,
        context: Any,
        *,
        equity: float,
        peak_equity: float,
        daily_realized_pnl: float,
        open_notional: float,
        symbol_exposure: float,
        open_positions: int,
        now_ms: int,
    ) -> RiskDecision:
        """Approve or reject one decision with the full fixed rule order."""
        decision_id = str(getattr(decision, "decision_id", "")).strip()
        if not decision_id:
            return self._reject("unknown", "malformed decision: missing decision_id")
        action = str(getattr(decision, "action", "")).strip().upper()
        symbol = str(getattr(decision, "symbol", "")).strip().upper()
        if self._halted:
            return self._reject(
                decision_id, "kill switch active: %s" % (self._halt_reason or "halted")
            )
        if action == "HOLD" or action == "":
            return self._reject(decision_id, "HOLD requires no execution")
        if action not in ("BUY", "SELL"):
            return self._reject(decision_id, "unknown action %r" % action)
        # Stale or incomplete context rejects regardless of confidence.
        if bool(getattr(context, "valid", False)) is False:
            reasons = getattr(context, "invalid_reasons", ())
            detail = "stale or incomplete context"
            if reasons:
                detail = "%s: %s" % (detail, "; ".join(str(item) for item in reasons))
            return self._reject(decision_id, detail)
        context_symbol = str(getattr(context, "symbol", "")).strip().upper()
        if not context_symbol or context_symbol != symbol:
            return self._reject(
                decision_id, "context symbol %r does not match decision %r" % (context_symbol, symbol)
            )
        if self._is_expired(decision, int(now_ms)):
            return self._reject(decision_id, "decision expired before risk review")
        if decision_id in self._seen:
            return self._reject(decision_id, "duplicate decision already reviewed")
        portfolio = getattr(context, "portfolio", None)
        if portfolio is not None and bool(getattr(portfolio, "cooldown_active", False)) is True:
            return self._reject(decision_id, "portfolio cooldown flag is active")
        last_stop = self._stopouts.get(symbol)
        ok, reason = check_cooldown(self.limits, int(now_ms), last_stop)
        if ok is False:
            return self._reject(decision_id, str(reason))
        if portfolio is not None:
            try:
                held = float(getattr(portfolio, "position_qty", 0.0) or 0.0)
            except (TypeError, ValueError):
                held = 0.0
            if held != 0.0:
                return self._reject(
                    decision_id, "existing position %.4f blocks a new entry" % held
                )
        reference = self._reference_price(decision, context)
        if reference is None:
            return self._reject(decision_id, "no reference price for sizing")
        stop, target = self._stops(decision)
        if stop is None or target is None:
            return self._reject(decision_id, "missing stop-loss or take-profit levels")
        if action == "BUY" and not (stop < reference < target or (stop < reference and target <= 0)):
            if not stop < reference:
                return self._reject(decision_id, "BUY stop %.2f must be below reference %.2f" % (stop, reference))
        if action == "SELL" and not (target < reference < stop or (reference < stop and target <= 0)):
            if not reference < stop:
                return self._reject(decision_id, "SELL stop %.2f must be above reference %.2f" % (stop, reference))
        ok, reason = check_stop_distance(self.limits, reference, stop)
        if ok is False:
            return self._reject(decision_id, str(reason))
        depth, spread = self._liquidity(context)
        try:
            quantity = calculate_quantity(
                equity=float(equity),
                risk_per_trade=float(self.limits.risk_per_trade),
                entry_price=reference,
                stop_price=stop,
                max_position_notional=float(self.limits.max_position_notional_per_symbol),
                depth_notional=depth,
                max_depth_fraction=float(self.limits.max_depth_fraction),
            )
        except ValueError as exc:
            return self._reject(decision_id, "sizing failed: %s" % exc)
        new_notional = quantity * reference
        # Why a floor: depth-capped sizing must not dribble dust into a thin
        # book. An order below minimum notional is rejected, not rounded up.
        if new_notional < float(self.limits.min_order_notional):
            return self._reject(
                decision_id,
                "order notional %.2f below minimum %.2f" % (
                    new_notional, float(self.limits.min_order_notional)),
            )
        ok, reason = check_symbol_exposure(self.limits, float(symbol_exposure), new_notional)
        if ok is False:
            return self._reject(decision_id, str(reason))
        ok, reason = check_portfolio_exposure(self.limits, float(open_notional), new_notional)
        if ok is False:
            return self._reject(decision_id, str(reason))
        ok, reason = check_concurrent_positions(self.limits, int(open_positions))
        if ok is False:
            return self._reject(decision_id, str(reason))
        ok, reason = check_daily_loss(self.limits, float(daily_realized_pnl))
        if ok is False:
            return self._reject(decision_id, str(reason))
        ok, reason = check_drawdown(self.limits, float(equity), float(peak_equity))
        if ok is False:
            return self._reject(decision_id, str(reason))
        ok, reason = check_leverage(
            self.limits, float(open_notional) + new_notional, float(equity)
        )
        if ok is False:
            return self._reject(decision_id, str(reason))
        ok, reason = check_liquidity(self.limits, new_notional, depth, spread)
        if ok is False:
            return self._reject(decision_id, str(reason))
        exposure_after: dict[str, Any] = {}
        exposure_after["symbol"] = symbol
        exposure_after["exposure_before"] = float(symbol_exposure)
        exposure_after["new_notional"] = new_notional
        exposure_after["exposure_after_symbol"] = float(symbol_exposure) + new_notional
        exposure_after["open_notional_after"] = float(open_notional) + new_notional
        approved = self._approve(decision_id, quantity, stop, target, exposure_after)
        self._seen.add(decision_id)
        return approved

    # -- internals --
    def _reject(self, decision_id: str, reason: str) -> RiskDecision:
        rid = "risk_" + str(uuid4()).replace("-", "")[:16]
        exposure: dict[str, Any] = {}
        seal = _seal(rid, decision_id, "REJECTED", 0.0, 0.0, 0.0, exposure, reason)
        if decision_id != "unknown":
            self._seen.add(decision_id)
        return RiskDecision(
            risk_decision_id=rid,
            decision_id=decision_id,
            status="REJECTED",
            approved_quantity=0.0,
            stop=0.0,
            target=0.0,
            exposure_after=exposure,
            rejection_reason=reason,
            integrity_hash=seal,
        )

    def _approve(
        self,
        decision_id: str,
        quantity: float,
        stop: float,
        target: float,
        exposure_after: dict[str, Any],
    ) -> RiskDecision:
        rid = "risk_" + str(uuid4()).replace("-", "")[:16]
        copied: dict[str, Any] = {}
        for key in exposure_after:
            copied[key] = exposure_after[key]
        seal = _seal(rid, decision_id, "APPROVED", float(quantity), float(stop), float(target), copied, None)
        return RiskDecision(
            risk_decision_id=rid,
            decision_id=decision_id,
            status="APPROVED",
            approved_quantity=float(quantity),
            stop=float(stop),
            target=float(target),
            exposure_after=copied,
            rejection_reason=None,
            integrity_hash=seal,
        )

    def _is_expired(self, decision: Any, now_ms: int) -> bool:
        try:
            stamp = getattr(decision, "timestamp")
            expiry = int(getattr(decision, "expiry_seconds"))
        except (TypeError, ValueError, AttributeError):
            return True
        if stamp is None or expiry <= 0:
            return True
        if not isinstance(stamp, datetime):
            return True
        moment = stamp
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        now = datetime.fromtimestamp(float(now_ms) / 1000.0, tz=timezone.utc)
        return now > moment + timedelta(seconds=expiry)

    def _reference_price(self, decision: Any, context: Any) -> float | None:
        entry = getattr(decision, "entry", None)
        if isinstance(entry, dict):
            raw = entry.get("reference_price")
            try:
                if raw is not None and not isinstance(raw, bool):
                    price = float(raw)
                    if price > 0:
                        return price
            except (TypeError, ValueError):
                pass
        trend = getattr(context, "trend", None)
        if trend is None:
            return None
        try:
            price = float(getattr(trend, "last_price"))
        except (TypeError, ValueError, AttributeError):
            return None
        if price <= 0:
            return None
        return price

    def _stops(self, decision: Any) -> tuple[float | None, float | None]:
        risk = getattr(decision, "risk", None)
        if not isinstance(risk, dict):
            return None, None
        try:
            stop = float(risk.get("stop_loss"))
            target = float(risk.get("take_profit"))
        except (TypeError, ValueError):
            return None, None
        if stop <= 0:
            return None, None
        if target < 0:
            return None, None
        return stop, target

    def _liquidity(self, context: Any) -> tuple[float | None, float | None]:
        liquidity = getattr(context, "liquidity", None)
        if liquidity is None:
            return None, None
        try:
            bid = float(getattr(liquidity, "bid_depth") or 0.0)
        except (TypeError, ValueError):
            bid = 0.0
        try:
            ask = float(getattr(liquidity, "ask_depth") or 0.0)
        except (TypeError, ValueError):
            ask = 0.0
        depth = bid + ask
        if depth <= 0:
            return None, None
        try:
            spread_raw = getattr(liquidity, "spread_bps")
            spread = float(spread_raw) if spread_raw is not None else None
        except (TypeError, ValueError):
            spread = None
        # Depth is in base-asset units here; convert with the reference price
        # at the call site? No: depth_notional needs a price, so approximate
        # with trend last_price when available.
        trend = getattr(context, "trend", None)
        price = None
        if trend is not None:
            try:
                price = float(getattr(trend, "last_price"))
            except (TypeError, ValueError, AttributeError):
                price = None
        if price is None or price <= 0:
            return depth, spread
        return depth * price, spread


def _seal(
    risk_decision_id: str,
    decision_id: str,
    status: str,
    approved_quantity: float,
    stop: float,
    target: float,
    exposure_after: dict[str, Any],
    rejection_reason: str | None,
) -> str:
    # Why canonical JSON: the hash must be stable across processes so Module 7
    # can recompute it byte-for-byte instead of trusting the quantity.
    canonical = json.dumps(
        {
            "risk_decision_id": risk_decision_id,
            "decision_id": decision_id,
            "status": status,
            "approved_quantity": repr(float(approved_quantity)),
            "stop": repr(float(stop)),
            "target": repr(float(target)),
            "exposure_after": dict(exposure_after),
            "rejection_reason": rejection_reason,
        },
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
