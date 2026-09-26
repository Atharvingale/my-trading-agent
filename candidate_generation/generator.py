"""Scheduled candidate generator with permanent audit (Module 15).

Why this file exists: automation may invent ideas, but it must not cheat by
trying unlimited ideas until one looks lucky, and it must never wire a
strategy by itself. This module enforces a configurable schedule (weekly by
default, so holdout budget is spent deliberately), logs every generation
immediately (even malformed or excluded ones), rejects excluded signal
classes before the gate, and leaves promotion to PASS + human approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from candidate_generation.hypothesis_menu import HypothesisMenu
from candidate_generation import multiple_testing
from candidate_generation.provider_client import propose_hypothesis


WEEK_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class CandidateHypothesis:
    hypothesis_id: str
    generated_at: datetime
    signal_class: str
    rationale: str
    proposed_entry_exit_rules: dict[str, Any]
    provider_used: str
    excluded_because: str | None
    candidate_id: str
    parent_candidate_id: str | None = None


class CandidateGenerator:
    """Weekly-budgeted, fail-closed hypothesis producer with an audit ledger."""

    def __init__(
        self,
        database_path: str | Path,
        menu: HypothesisMenu | None = None,
        min_interval_seconds: int = WEEK_SECONDS,
        max_candidates: int | None = None,
    ) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.menu = menu if menu is not None else HypothesisMenu()
        self.owns_menu = menu is None
        interval = int(min_interval_seconds)
        if interval < 0:
            raise ValueError("min_interval_seconds must be non-negative")
        self.min_interval_seconds = interval
        if max_candidates is not None:
            budget = int(max_candidates)
            if budget < 1:
                raise ValueError("max_candidates must be positive when set")
            self.max_candidates: int | None = budget
        else:
            self.max_candidates = None
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id TEXT PRIMARY KEY,
                hypothesis_id TEXT NOT NULL UNIQUE,
                parent_candidate_id TEXT,
                signal_class TEXT NOT NULL,
                rationale TEXT NOT NULL,
                rules_json TEXT NOT NULL,
                provider_used TEXT NOT NULL,
                source TEXT NOT NULL,
                excluded_because TEXT,
                status TEXT NOT NULL,
                raw_response_json TEXT NOT NULL,
                gate_record_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rejected_responses (
                rejection_id TEXT PRIMARY KEY,
                reason TEXT NOT NULL,
                raw_response_json TEXT NOT NULL,
                provider_used TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS preregistrations (
                prereg_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                hypothesis_id TEXT NOT NULL,
                gate_record_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id)
            );
            CREATE TRIGGER IF NOT EXISTS candidates_no_update
            BEFORE UPDATE ON candidates
            BEGIN
                SELECT RAISE(ABORT, 'candidates are append-only; use a new candidate id');
            END;
            CREATE TRIGGER IF NOT EXISTS candidates_no_delete
            BEFORE DELETE ON candidates
            BEGIN
                SELECT RAISE(ABORT, 'candidates are append-only');
            END;
            """
        )
        self.connection.commit()

    def close(self) -> None:
        if self.owns_menu:
            self.menu.close()
        self.connection.close()

    def __enter__(self) -> CandidateGenerator:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    # -- schedule / budget --
    def last_generated_at(self) -> datetime | None:
        row = self.connection.execute(
            "SELECT created_at FROM candidates ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(str(row["created_at"]))

    def generated_count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS total FROM candidates").fetchone()
        return int(row["total"])

    def should_run(self, now: datetime | None = None) -> bool:
        """True only when the schedule is due and the budget is not spent."""
        moment = now if now is not None else datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        if self.max_candidates is not None:
            if self.generated_count() >= self.max_candidates:
                return False
        last = self.last_generated_at()
        if last is None:
            return True
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (moment - last).total_seconds()
        return elapsed >= float(self.min_interval_seconds)

    def check_schedule(self, now: datetime | None = None) -> None:
        if self.should_run(now=now) is False:
            raise ValueError("generation schedule not due or candidate budget spent")

    # -- prompt --
    def build_prompt(self) -> str:
        """Prompt text naming only the approved classes so the LLM stays in-menu."""
        lines: list[str] = []
        lines.append("Propose one new trading-strategy hypothesis as JSON with keys:")
        lines.append("signal_class, rationale, proposed_entry_exit_rules.")
        lines.append("signal_class must be exactly one of:")
        for approved in self.menu.list_approved():
            lines.append("- " + approved)
        lines.append("rationale must explain why this differs from failed price-action classes.")
        lines.append("proposed_entry_exit_rules must be a JSON object of entry/exit rules.")
        return "\n".join(lines)

    # -- generation --
    def run_once(
        self,
        prompt: str | None,
        api_url: str,
        api_key: str,
        model_name: str,
        *,
        parent_candidate_id: str | None = None,
        now: datetime | None = None,
        timeout_seconds: int = 30,
    ) -> CandidateHypothesis | None:
        """Call the provider once, log immediately, return a hypothesis or None.

        Returns None only for malformed provider output (logged as REJECTED).
        Excluded classes return a hypothesis with excluded_because set and are
        never sent to the gate. Raises when the schedule is not due.
        """
        self.check_schedule(now=now)
        text = prompt if prompt is not None else self.build_prompt()
        provider_label = "%s:%s" % (str(api_url).strip(), str(model_name).strip())
        try:
            raw = propose_hypothesis(text, api_url, api_key, model_name, timeout_seconds=timeout_seconds)
        except (ValueError, OSError) as exc:
            self._log_rejection(str(exc), "{}", provider_label)
            return None
        return self.generate_from_response(
            raw, provider_used=provider_label, parent_candidate_id=parent_candidate_id
        )

    def generate_from_response(
        self, raw: Mapping[str, Any], *, provider_used: str, parent_candidate_id: str | None = None
    ) -> CandidateHypothesis | None:
        """Parse, menu-check, and audit-log one provider response (fail-closed)."""
        label = str(provider_used).strip() or "unknown-provider"
        if not isinstance(raw, Mapping):
            self._log_rejection("provider returned a non-object payload", "{}", label)
            return None
        try:
            signal_class, rationale, rules = _parse_fields(raw)
        except ValueError as exc:
            self._log_rejection(str(exc), _json(dict(raw)), label)
            return None
        verdict = self.menu.check(signal_class)
        candidate_id = str(uuid4())
        hypothesis_id = str(uuid4())
        created = datetime.now(timezone.utc)
        if verdict["allowed"] is not True:
            hypothesis = CandidateHypothesis(
                hypothesis_id=hypothesis_id,
                generated_at=created,
                signal_class=str(signal_class).strip(),
                rationale=rationale,
                proposed_entry_exit_rules=rules,
                provider_used=label,
                excluded_because=str(verdict["excluded_because"]),
                candidate_id=candidate_id,
                parent_candidate_id=_clean_or_none(parent_candidate_id),
            )
            self._log_candidate(hypothesis, raw, status="EXCLUDED", source="AI_RESEARCH")
            return hypothesis
        hypothesis = CandidateHypothesis(
            hypothesis_id=hypothesis_id,
            generated_at=created,
            signal_class=str(signal_class).strip(),
            rationale=rationale,
            proposed_entry_exit_rules=rules,
            provider_used=label,
            excluded_because=None,
            candidate_id=candidate_id,
            parent_candidate_id=_clean_or_none(parent_candidate_id),
        )
        self._log_candidate(hypothesis, raw, status="GENERATED", source="AI_RESEARCH")
        return hypothesis

    def preregister(
        self,
        candidate: CandidateHypothesis,
        registry: Any,
        *,
        holdout_period: tuple[Any, Any],
        cost_and_tax_assumptions: Mapping[str, Any],
        strategy_id: str,
        multiple_testing_family: str = "all",
    ) -> str:
        """Submit one allowed candidate through the identical Module 1 path.

        Computes the current Bonferroni threshold from the live ledger and
        stores it as provenance. Excluded or malformed candidates raise
        instead of reaching the gate.
        """
        if candidate.excluded_because is not None:
            raise ValueError("excluded candidate cannot be preregistered: %s" % candidate.excluded_because)
        self.menu.require_allowed(candidate.signal_class)
        bar = multiple_testing.adjusted_threshold(registry=registry, family=multiple_testing_family)
        record_id = registry.submit_hypothesis(
            strategy_id=strategy_id,
            hypothesis="%s | %s" % (candidate.signal_class, candidate.rationale),
            pre_registered_criteria={"multiple_testing_required_alpha": bar["required_alpha"]},
            holdout_period=holdout_period,
            cost_and_tax_assumptions=dict(cost_and_tax_assumptions),
            candidate_id=candidate.candidate_id,
            parent_candidate_id=candidate.parent_candidate_id,
            hypothesis_id=candidate.hypothesis_id,
            signal_class=candidate.signal_class,
            source="AI_RESEARCH",
            provider_used=candidate.provider_used,
            multiple_testing_family=str(multiple_testing_family),
            multiple_testing_threshold=float(bar["required_alpha"]),
        )
        # Why a companion row: the candidates ledger is append-only, so gate
        # linkage is a new event row, never an in-place status edit.
        self.connection.execute(
            """INSERT INTO preregistrations
            (prereg_id, candidate_id, hypothesis_id, gate_record_id, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (
                str(uuid4()),
                candidate.candidate_id,
                candidate.hypothesis_id,
                record_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.connection.commit()
        return record_id

    # -- audit reads --
    def list_logged(self, status: str | None = None) -> list[dict[str, Any]]:
        if status is None:
            rows = self.connection.execute("SELECT * FROM candidates ORDER BY rowid").fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM candidates WHERE status=? ORDER BY rowid", (str(status),)
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            entry: dict[str, Any] = {}
            for key in row.keys():
                entry[key] = row[key]
            result.append(entry)
        return result

    def list_rejections(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM rejected_responses ORDER BY rowid").fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            entry: dict[str, Any] = {}
            for key in row.keys():
                entry[key] = row[key]
            result.append(entry)
        return result

    # -- internals --
    def _log_candidate(
        self, hypothesis: CandidateHypothesis, raw: Mapping[str, Any], *, status: str, source: str
    ) -> None:
        self.connection.execute(
            """INSERT INTO candidates
            (candidate_id, hypothesis_id, parent_candidate_id, signal_class, rationale,
             rules_json, provider_used, source, excluded_because, status,
             raw_response_json, gate_record_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                hypothesis.candidate_id,
                hypothesis.hypothesis_id,
                hypothesis.parent_candidate_id,
                hypothesis.signal_class,
                hypothesis.rationale,
                _json(hypothesis.proposed_entry_exit_rules),
                hypothesis.provider_used,
                source,
                hypothesis.excluded_because,
                status,
                _json(dict(raw)),
                None,
                hypothesis.generated_at.isoformat(),
            ),
        )
        self.connection.commit()

    def list_preregistrations(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM preregistrations ORDER BY rowid").fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            entry: dict[str, Any] = {}
            for key in row.keys():
                entry[key] = row[key]
            result.append(entry)
        return result

    def _log_rejection(self, reason: str, raw_json: str, provider_used: str) -> None:
        self.connection.execute(
            """INSERT INTO rejected_responses
            (rejection_id, reason, raw_response_json, provider_used, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (str(uuid4()), str(reason), str(raw_json), str(provider_used), datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()


def _parse_fields(raw: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
    # Why strict: a hypothesis missing required fields is not tested, it is
    # logged as rejected and the loop moves to its next scheduled run.
    if "signal_class" not in raw:
        raise ValueError("provider output missing required field: signal_class")
    if "rationale" not in raw:
        raise ValueError("provider output missing required field: rationale")
    if "proposed_entry_exit_rules" not in raw:
        raise ValueError("provider output missing required field: proposed_entry_exit_rules")
    signal_class = raw["signal_class"]
    rationale = raw["rationale"]
    rules = raw["proposed_entry_exit_rules"]
    if not isinstance(signal_class, str) or not signal_class.strip():
        raise ValueError("signal_class must be a non-empty string")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("rationale must be a non-empty string")
    if not isinstance(rules, dict) or len(rules) == 0:
        raise ValueError("proposed_entry_exit_rules must be a non-empty object")
    cleaned: dict[str, Any] = {}
    for key in rules:
        cleaned[str(key)] = rules[key]
    return str(signal_class).strip(), str(rationale).strip(), cleaned


def _clean_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)
