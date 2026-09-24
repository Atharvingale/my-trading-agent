"""Deterministic decision engine (Module 5).

Combines gate-linked StrategyProposals with a MarketContext into one
auditable Decision per symbol per cycle. Analysis-only: no trading calls, no
LLM calls, no imports from strategies beyond the proposal contract type, and
nothing from risk or execution.

Tie-break rule (explicit, documented): weighted majority wins. Each valid
proposal votes once, weighted by its strategy's calibrated historical hit
rate (unknown strategies contribute the skeptical 0.5 prior). The action
with the highest total weight wins. Any exact tie — including BUY versus
SELL — resolves to HOLD, because a tie means no preponderance of validated
evidence and the project fail-closed rule resolves ambiguity to HOLD.

Confidence formula: Laplace-smoothed weighted agreement. With W_win the
winning weight and W_total the total weight, confidence is
(W_win + 1) / (W_total + 2): the same skeptical (1, 2) prior Module 4 uses,
applied at the agreement level so a lone proposal can never claim certainty.
Per-strategy weights come from strategies.calibration.calibrate_confidence;
the zero-proposal HOLD carries the prior-only 0.5, which explicitly means
"no evidence", not moderate conviction. Nothing here is hardcoded.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import uuid5, NAMESPACE_URL

from hermes.models.decision import Decision, DecisionEvidenceRecord
from strategies.base import StrategyProposal
from strategies.calibration import calibrate_confidence, confidence_from_window_returns


DEFAULT_EXPIRY_SECONDS = 120
DEFAULT_HORIZON = "15m"
PRIOR_HITS = 1.0
PRIOR_TOTAL = 2.0


class ExpiredDecisionError(RuntimeError):
    """Raised when a downstream consumer is handed a decision past its expiry."""


class MalformedProposalError(ValueError):
    """Raised only by the strict single-proposal checker used in tests."""


def _order_proposals(proposals: list[StrategyProposal]) -> list[StrategyProposal]:
    # Explicit insertion order by (strategy_id, proposal_id) so reruns over
    # the same set are byte-identical without using sorted().
    ordered: list[StrategyProposal] = []
    for proposal in proposals:
        key = (str(proposal.strategy_id), str(proposal.proposal_id))
        placed = False
        for index in range(len(ordered)):
            other = ordered[index]
            other_key = (str(other.strategy_id), str(other.proposal_id))
            if key < other_key:
                ordered.insert(index, proposal)
                placed = True
                break
        if placed is False:
            ordered.append(proposal)
    return ordered


def _strategy_weight(strategy_id: str, histories: Mapping[str, Any] | None) -> float:
    # Each strategy's vote weight is its calibrated historical hit rate.
    # Unknown strategies contribute the skeptical prior-only 0.5.
    if histories is not None and strategy_id in histories:
        entry = histories[strategy_id]
        try:
            hits = int(entry[0])
            total = int(entry[1])
        except (TypeError, ValueError, IndexError):
            return calibrate_confidence(0, 0)
        return calibrate_confidence(hits, total)
    return calibrate_confidence(0, 0)


def _is_well_formed(proposal: Any, symbol: str) -> bool:
    if not isinstance(proposal, StrategyProposal):
        return False
    if str(proposal.symbol).strip().upper() != symbol:
        return False
    if proposal.action not in ("BUY", "SELL", "HOLD"):
        return False
    if not str(proposal.edge_validation_record_id).strip():
        return False
    try:
        value = float(proposal.confidence)
    except (TypeError, ValueError):
        return False
    if isinstance(proposal.confidence, bool):
        return False
    if not 0.0 <= value <= 1.0:
        return False
    if not isinstance(proposal.evidence, list) or len(proposal.evidence) == 0:
        return False
    return True


def _reference_price(context: Any) -> float | None:
    trend = getattr(context, "trend", None)
    if trend is None:
        return None
    try:
        price = trend.last_price
    except AttributeError:
        return None
    if price is None or isinstance(price, bool):
        return None
    try:
        return float(price)
    except (TypeError, ValueError):
        return None


def _atr_value(context: Any) -> float | None:
    trend = getattr(context, "trend", None)
    if trend is None:
        return None
    try:
        atr = trend.atr
    except AttributeError:
        return None
    if atr is None or isinstance(atr, bool):
        return None
    try:
        value = float(atr)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def _thesis_lines(
    *,
    action: str,
    symbol: str,
    valid_count: int,
    dropped_count: int,
    winner_share: float,
    winner_reason: str,
    evidence: list[dict[str, Any]],
) -> list[str]:
    # Fixed template: same inputs always render the same lines.
    lines: list[str] = []
    lines.append(
        "%s %s: %d valid proposal(s), %d dropped as malformed."
        % (action, symbol, valid_count, dropped_count)
    )
    lines.append(
        "Weighted agreement %.4f for %s (%s)." % (winner_share, action, winner_reason)
    )
    for index in range(len(evidence)):
        entry = evidence[index]
        feature = entry.get("feature", "?")
        value = entry.get("value", None)
        lines.append("evidence[%d] %s=%s" % (index, feature, value))
    return lines


def _rationale(
    *,
    action: str,
    symbol: str,
    valid_count: int,
    dropped_count: int,
    winner_share: float,
    confidence: float,
    winner_reason: str,
) -> str:
    return (
        "%s %s with calibrated confidence %.4f from weighted agreement %.4f "
        "(%d valid, %d dropped; %s)."
        % (action, symbol, confidence, winner_share, valid_count, dropped_count, winner_reason)
    )


def decide(
    symbol: str,
    context: Any,
    proposals: list[Any],
    *,
    strategy_histories: Mapping[str, Any] | None = None,
    timestamp: datetime | None = None,
    expiry_seconds: int = DEFAULT_EXPIRY_SECONDS,
    time_horizon: str | None = None,
) -> tuple[Decision, DecisionEvidenceRecord]:
    """Combine proposals and context into one deterministic decision.

    Fail-closed: invalid context, symbol mismatch, zero valid proposals, or
    malformed entries resolve to HOLD, never to a default BUY or SELL.
    """
    token = str(symbol).strip().upper()
    if not token:
        raise ValueError("symbol must be non-empty")
    if not isinstance(expiry_seconds, int) or isinstance(expiry_seconds, bool):
        raise ValueError("expiry_seconds must be an int")
    if expiry_seconds <= 0:
        raise ValueError("expiry_seconds must be positive")

    context_symbol = str(getattr(context, "symbol", "")).strip().upper()
    context_valid = bool(getattr(context, "valid", False))
    mismatch = context_symbol != token

    ordered: list[StrategyProposal] = []
    dropped = 0
    if isinstance(proposals, (list, tuple)):
        for proposal in proposals:
            if _is_well_formed(proposal, token):
                ordered.append(proposal)
            else:
                dropped += 1
    else:
        dropped += 1
    ordered = _order_proposals(ordered)

    usable = context_valid and (mismatch is False) and len(ordered) > 0

    weights: dict[str, float] = {}
    for proposal in ordered:
        weights[proposal.proposal_id] = _strategy_weight(proposal.strategy_id, strategy_histories)

    totals: dict[str, float] = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}
    for proposal in ordered:
        totals[proposal.action] = totals[proposal.action] + weights[proposal.proposal_id]
    total_weight = totals["BUY"] + totals["SELL"] + totals["HOLD"]

    action = "HOLD"
    winner_reason = "no valid proposals; default HOLD"
    winner_share = 0.0
    if usable:
        best = "HOLD"
        best_weight = totals["HOLD"]
        # Fixed comparison order keeps ties deterministic before the tie rule.
        for candidate in ("BUY", "SELL", "HOLD"):
            if totals[candidate] > best_weight:
                best = candidate
                best_weight = totals[candidate]
        tied = False
        for candidate in ("BUY", "SELL", "HOLD"):
            if candidate != best and totals[candidate] == best_weight:
                tied = True
        if tied:
            action = "HOLD"
            winner_reason = "exact weighted tie; HOLD-favoring tie-break"
            winner_share = best_weight / total_weight if total_weight > 0 else 0.0
        else:
            action = best
            winner_share = best_weight / total_weight if total_weight > 0 else 0.0
            if action == "HOLD":
                winner_reason = "HOLD majority among valid proposals"
            else:
                winner_reason = "weighted majority"
    if mismatch:
        winner_reason = "context symbol mismatch; default HOLD"
    elif context_valid is False:
        winner_reason = "invalid context; default HOLD"

    if usable and total_weight > 0:
        confidence = (totals[action] + PRIOR_HITS) / (total_weight + PRIOR_TOTAL)
    else:
        # Prior-only: explicitly "no evidence", via the shared calibration path.
        confidence = confidence_from_window_returns([])

    moment = timestamp
    if moment is None:
        stamp = getattr(context, "timestamp_ms", None)
        if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
            moment = datetime.fromtimestamp(float(stamp) / 1000.0, tz=timezone.utc)
        else:
            moment = datetime.now(timezone.utc)
    if not isinstance(moment, datetime):
        raise ValueError("timestamp must be a datetime")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    seed_parts: list[str] = []
    seed_parts.append(token)
    seed_parts.append(moment.astimezone(timezone.utc).isoformat())
    seed_parts.append(action)
    for proposal in ordered:
        seed_parts.append(str(proposal.proposal_id))
    seed = "|".join(seed_parts)
    decision_id = str(uuid5(NAMESPACE_URL, "hermes-decision:" + seed).__str__())

    evidence: list[dict[str, Any]] = []
    for proposal in ordered:
        if proposal.action == action or action == "HOLD":
            for entry in proposal.evidence:
                copied: dict[str, Any] = {}
                for key in entry:
                    copied[key] = entry[key]
                evidence.append(copied)
    if len(evidence) == 0:
        evidence.append({"feature": "no_valid_evidence", "value": None})

    votes: dict[str, str] = {}
    for proposal in ordered:
        votes[proposal.strategy_id] = proposal.action

    horizon = str(time_horizon).strip() if time_horizon is not None else ""
    if not horizon:
        horizon = str(getattr(ordered[0], "horizon", "")).strip() if len(ordered) > 0 else ""
    if not horizon:
        horizon = DEFAULT_HORIZON

    version_id = "none"
    if action != "HOLD":
        for proposal in ordered:
            if proposal.action == action:
                version_id = str(proposal.strategy_version).strip() or "v1"
                break

    price = _reference_price(context)
    atr = _atr_value(context)
    stop_loss = 0.0
    take_profit = 0.0
    if price is not None and atr is not None and action != "HOLD":
        if action == "BUY":
            stop_loss = price - 2.0 * atr
            take_profit = price + 3.0 * atr
        else:
            stop_loss = price + 2.0 * atr
            take_profit = price - 3.0 * atr

    portfolio = getattr(context, "portfolio", None)
    position_qty = 0.0
    exposure = 0.0
    unrealized = 0.0
    realized = 0.0
    if portfolio is not None:
        try:
            position_qty = float(getattr(portfolio, "position_qty", 0.0) or 0.0)
        except (TypeError, ValueError):
            position_qty = 0.0
        try:
            exposure = float(getattr(portfolio, "exposure_notional", 0.0) or 0.0)
        except (TypeError, ValueError):
            exposure = 0.0
        try:
            unrealized = float(getattr(portfolio, "unrealized_pnl", 0.0) or 0.0)
        except (TypeError, ValueError):
            unrealized = 0.0
        try:
            realized = float(getattr(portfolio, "realized_pnl", 0.0) or 0.0)
        except (TypeError, ValueError):
            realized = 0.0

    thesis = _thesis_lines(
        action=action,
        symbol=token,
        valid_count=len(ordered),
        dropped_count=dropped,
        winner_share=winner_share,
        winner_reason=winner_reason,
        evidence=evidence,
    )
    rationale = _rationale(
        action=action,
        symbol=token,
        valid_count=len(ordered),
        dropped_count=dropped,
        winner_share=winner_share,
        confidence=confidence,
        winner_reason=winner_reason,
    )
    if action == "HOLD":
        risk_assessment = "NoAction"
    else:
        # Module 6 owns approval and sizing; the engine only proposes levels.
        risk_assessment = "PendingRiskReview"

    decision = Decision(
        decision_id=decision_id,
        timestamp=moment,
        symbol=token,
        action=action,
        confidence=confidence,
        entry={"symbol": token, "side": action, "reference_price": price},
        position={
            "position_qty": position_qty,
            "exposure_notional": exposure,
            "unrealized_pnl": unrealized,
            "realized_pnl": realized,
        },
        risk={"stop_loss": stop_loss, "take_profit": take_profit, "risk_amount": 0.0},
        time_horizon=horizon,
        thesis=thesis,
        strategy_version_id=version_id,
        expiry_seconds=expiry_seconds,
    )
    stamp_ms = getattr(context, "timestamp_ms", None)
    if isinstance(stamp_ms, (int, float)) and not isinstance(stamp_ms, bool):
        snapshot_id = "snap_%s_%d" % (token, int(stamp_ms))
    else:
        snapshot_id = "snap_%s_unknown" % token
    record = DecisionEvidenceRecord(
        decision_id=decision_id,
        market_snapshot_id=snapshot_id,
        action=action,
        confidence=confidence,
        evidence=evidence,
        strategy_votes=votes,
        decision_rationale=rationale,
        risk_assessment=risk_assessment,
        decision=action,
    )
    return decision, record


def is_expired(decision: Decision, now: datetime) -> bool:
    """True when now is past timestamp + expiry_seconds (boundary is valid)."""
    if not isinstance(decision, Decision):
        raise TypeError("decision must be a Decision")
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")
    moment = now
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    stamp = decision.timestamp
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return moment > stamp + timedelta(seconds=decision.expiry_seconds)


def consume_decision(decision: Decision, now: datetime) -> Decision:
    """Downstream-consumer contract: expired decisions are void, never current.

    Why a hard raise instead of a flag: a stale instruction that silently
    passes through becomes a trade on old information. Raising forces every
    consumer to handle expiry explicitly.
    """
    if is_expired(decision, now):
        raise ExpiredDecisionError(
            "decision %s expired %ds after %s"
            % (decision.decision_id, decision.expiry_seconds, decision.timestamp.isoformat())
        )
    return decision
