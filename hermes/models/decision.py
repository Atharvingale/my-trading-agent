"""Decision and decision-evidence contracts (Module 5).

Every field is required: a decision that cannot populate all of them is not
a valid decision and must not be emitted. Confidence is a calibrated
statistic, thesis and rationale are fixed template outputs. No LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


ACTIONS = ("BUY", "SELL", "HOLD")


@dataclass(frozen=True)
class Decision:
    decision_id: str
    timestamp: datetime
    symbol: str
    action: str
    confidence: float
    entry: dict[str, Any]
    position: dict[str, Any]
    risk: dict[str, Any]
    time_horizon: str
    thesis: list[str]
    strategy_version_id: str
    expiry_seconds: int

    def __post_init__(self) -> None:
        # No field is optional or defaulted into existence downstream, so the
        # constructor itself rejects anything incomplete or out of range here.
        if not self.decision_id.strip():
            raise ValueError("decision_id must be non-empty")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.action not in ACTIONS:
            raise ValueError("action must be BUY, SELL, or HOLD")
        confidence = self.confidence
        if isinstance(confidence, bool):
            raise ValueError("confidence must be a number in [0, 1]")
        try:
            value = float(confidence)
        except (TypeError, ValueError):
            raise ValueError("confidence must be a number in [0, 1]")
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if not isinstance(self.entry, dict):
            raise ValueError("entry must be a dict")
        if not isinstance(self.position, dict):
            raise ValueError("position must be a dict")
        if not isinstance(self.risk, dict):
            raise ValueError("risk must be a dict")
        for key in ("stop_loss", "take_profit", "risk_amount"):
            if key not in self.risk:
                raise ValueError("risk must contain stop_loss, take_profit, risk_amount")
        if not self.time_horizon.strip():
            raise ValueError("time_horizon must be non-empty")
        if not isinstance(self.thesis, list):
            raise ValueError("thesis must be a list of template lines")
        for line in self.thesis:
            if not isinstance(line, str) or not line.strip():
                raise ValueError("thesis lines must be non-empty strings")
        if not self.strategy_version_id.strip():
            raise ValueError("strategy_version_id must be non-empty")
        if not isinstance(self.expiry_seconds, int) or isinstance(self.expiry_seconds, bool):
            raise ValueError("expiry_seconds must be an int")
        if self.expiry_seconds <= 0:
            raise ValueError("expiry_seconds must be positive")

    def to_dict(self) -> dict[str, Any]:
        # Plain-dict view with explicit copies so callers cannot mutate us.
        thesis_copy: list[str] = []
        for line in self.thesis:
            thesis_copy.append(line)
        entry_copy: dict[str, Any] = {}
        for key in self.entry:
            entry_copy[key] = self.entry[key]
        position_copy: dict[str, Any] = {}
        for key in self.position:
            position_copy[key] = self.position[key]
        risk_copy: dict[str, Any] = {}
        for key in self.risk:
            risk_copy[key] = self.risk[key]
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "action": self.action,
            "confidence": float(self.confidence),
            "entry": entry_copy,
            "position": position_copy,
            "risk": risk_copy,
            "time_horizon": self.time_horizon,
            "thesis": thesis_copy,
            "strategy_version_id": self.strategy_version_id,
            "expiry_seconds": self.expiry_seconds,
        }


@dataclass(frozen=True)
class DecisionEvidenceRecord:
    decision_id: str
    market_snapshot_id: str
    action: str
    confidence: float
    evidence: list[dict[str, Any]]
    strategy_votes: dict[str, str]
    decision_rationale: str
    risk_assessment: str
    decision: str

    def __post_init__(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("decision_id must be non-empty")
        if not self.market_snapshot_id.strip():
            raise ValueError("market_snapshot_id must be non-empty")
        if self.action not in ACTIONS:
            raise ValueError("action must be BUY, SELL, or HOLD")
        confidence = self.confidence
        if isinstance(confidence, bool):
            raise ValueError("confidence must be a number in [0, 1]")
        try:
            value = float(confidence)
        except (TypeError, ValueError):
            raise ValueError("confidence must be a number in [0, 1]")
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if not isinstance(self.evidence, list):
            raise ValueError("evidence must be a list")
        for item in self.evidence:
            if not isinstance(item, dict):
                raise ValueError("evidence entries must be dicts")
        if not isinstance(self.strategy_votes, dict):
            raise ValueError("strategy_votes must be a dict")
        for key in self.strategy_votes:
            if self.strategy_votes[key] not in ACTIONS:
                raise ValueError("strategy votes must be BUY, SELL, or HOLD")
        if not self.decision_rationale.strip():
            raise ValueError("decision_rationale must be non-empty template text")
        if not self.risk_assessment.strip():
            raise ValueError("risk_assessment must be non-empty")
        if self.decision not in ACTIONS:
            raise ValueError("decision must be BUY, SELL, or HOLD")

    def to_dict(self) -> dict[str, Any]:
        evidence_copy: list[dict[str, Any]] = []
        for item in self.evidence:
            copied: dict[str, Any] = {}
            for key in item:
                copied[key] = item[key]
            evidence_copy.append(copied)
        votes_copy: dict[str, str] = {}
        for key in self.strategy_votes:
            votes_copy[key] = self.strategy_votes[key]
        return {
            "decision_id": self.decision_id,
            "market_snapshot_id": self.market_snapshot_id,
            "action": self.action,
            "confidence": float(self.confidence),
            "evidence": evidence_copy,
            "strategy_votes": votes_copy,
            "decision_rationale": self.decision_rationale,
            "risk_assessment": self.risk_assessment,
            "decision": self.decision,
        }

