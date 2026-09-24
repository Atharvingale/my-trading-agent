"""Append-only event ledger for strategy edge evidence and fail-closed gating."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping
from uuid import uuid4

from edge_validation.acceptance_criteria import AcceptanceCriteria
from edge_validation.evidence import ExperimentEvidence
from edge_validation.report_writer import HEADER, append_hypothesis, append_result


VERDICTS = {"PENDING", "PASS", "FAIL", "NULL_RESULT"}
REQUIRED_ASSUMPTIONS = {
    "fee_rate",
    "slippage_rate",
    "tax_rate",
    "tds_rate",
    "loss_offset_allowed",
    "tds_is_cash_flow_drag",
}
FALSIFIED_FAMILIES = {"breakout", "scalping"}


class StrategyNotGatedError(RuntimeError):
    """Raised when a strategy does not have a latest PASS validation record."""


@dataclass(frozen=True)
class EdgeValidationRecord:
    record_id: str
    strategy_id: str
    hypothesis: str
    pre_registered_criteria: dict[str, Any]
    holdout_period: tuple[date, date]
    cost_and_tax_assumptions: dict[str, Any]
    bootstrap_ci: tuple[float, float] | None
    regime_results: dict[str, float]
    replication_result: str | None
    verdict: str
    linked_strategy_version_id: str | None
    created_at: datetime
    strategy_family: str
    requires_replication: bool
    acceptance_checks: dict[str, bool] | None


class EdgeValidationRegistry:
    """SQLite-backed append-only ledger; only a positive, evidence-backed PASS opens the gate."""

    def __init__(self, database_path: str | Path, report_path: str | Path | None = None) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if report_path is None:
            report_path = Path.cwd() / "research" / "reports" / "EXPERIMENT_REGISTRY.md"
        self.report_path = Path(report_path)
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS edge_validation_records (
                record_id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK (event_type IN ('HYPOTHESIS', 'RESULT')),
                strategy_id TEXT NOT NULL,
                strategy_family TEXT NOT NULL,
                verdict TEXT NOT NULL CHECK (verdict IN ('PENDING', 'PASS', 'FAIL', 'NULL_RESULT')),
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (attempt_id) REFERENCES edge_validation_records(record_id)
            );
            CREATE INDEX IF NOT EXISTS idx_edge_validation_latest
                ON edge_validation_records(strategy_family, created_at, event_type);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_edge_validation_one_result_per_attempt
                ON edge_validation_records(attempt_id) WHERE event_type = 'RESULT';
            CREATE TRIGGER IF NOT EXISTS edge_validation_no_update
            BEFORE UPDATE ON edge_validation_records
            BEGIN
                SELECT RAISE(ABORT, 'edge_validation_records are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS edge_validation_no_delete
            BEFORE DELETE ON edge_validation_records
            BEGIN
                SELECT RAISE(ABORT, 'edge_validation_records are append-only');
            END;
            """
        )
        self.connection.commit()
        self._seed_falsified_families()
        self._sync_report()

    def _sync_report(self) -> None:
        """Recover report entries if a process stopped after committing SQLite."""
        if not self.report_path.exists() or self.report_path.stat().st_size == 0:
            self.report_path.write_text(HEADER, encoding="utf-8")
        report_text = self.report_path.read_text(encoding="utf-8")
        hypotheses = self.connection.execute(
            "SELECT * FROM edge_validation_records WHERE event_type='HYPOTHESIS' ORDER BY rowid"
        ).fetchall()
        for hypothesis_row in hypotheses:
            attempt_id = str(hypothesis_row["record_id"])
            if f"Record ID: `{attempt_id}`" not in report_text:
                append_hypothesis(
                    self.report_path,
                    attempt_id,
                    str(hypothesis_row["strategy_id"]),
                    str(hypothesis_row["strategy_family"]),
                    json.loads(hypothesis_row["payload_json"]),
                    datetime.fromisoformat(hypothesis_row["created_at"]),
                )
                report_text = self.report_path.read_text(encoding="utf-8")
            result_row = self.connection.execute(
                "SELECT * FROM edge_validation_records WHERE attempt_id=? AND event_type='RESULT'",
                (attempt_id,),
            ).fetchone()
            result_marker = f"Preregistration record ID: `{attempt_id}`"
            if result_row is not None and result_marker not in report_text:
                append_result(
                    self.report_path,
                    attempt_id,
                    str(result_row["verdict"]),
                    json.loads(result_row["payload_json"]),
                    datetime.fromisoformat(result_row["created_at"]),
                )
                report_text = self.report_path.read_text(encoding="utf-8")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> EdgeValidationRegistry:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def submit_hypothesis(
        self,
        *,
        strategy_id: str,
        hypothesis: str,
        pre_registered_criteria: Mapping[str, Any],
        holdout_period: tuple[date, date],
        cost_and_tax_assumptions: Mapping[str, Any],
        strategy_family: str | None = None,
        requires_replication: bool = False,
        linked_strategy_version_id: str | None = None,
        materially_new_hypothesis: bool = False,
        new_hypothesis_rationale: str | None = None,
    ) -> str:
        """Persist and publish a hypothesis before any holdout result is accepted."""
        strategy = _normalize_identifier(strategy_id, "strategy_id")
        hypothesis_text = hypothesis.strip()
        if not hypothesis_text:
            raise ValueError("hypothesis must not be empty")
        inferred_family = _strategy_family_for_lookup(strategy)
        family = _normalize_identifier(strategy_family or inferred_family, "strategy_family")
        if family != inferred_family:
            raise ValueError("strategy identifiers cannot be reclassified into another family")
        _validate_period(holdout_period)
        _validate_preregistered_criteria(pre_registered_criteria)
        assumptions = _validate_assumptions(cost_and_tax_assumptions)
        if not isinstance(requires_replication, bool):
            raise ValueError("requires_replication must be boolean")
        if not isinstance(materially_new_hypothesis, bool):
            raise ValueError("materially_new_hypothesis must be boolean")
        if family in FALSIFIED_FAMILIES and not materially_new_hypothesis:
            raise ValueError(
                f"{family} is falsified; a materially new hypothesis and rationale are required"
            )
        if materially_new_hypothesis and not (new_hypothesis_rationale or "").strip():
            raise ValueError("materially new hypotheses require an auditable rationale")
        if linked_strategy_version_id is not None and not linked_strategy_version_id.strip():
            raise ValueError("linked_strategy_version_id must be non-empty when provided")

        self._check_fresh_holdout(family, holdout_period)
        self._check_unique_hypothesis(family, hypothesis_text)
        attempt_id = str(uuid4())
        created_at = _utc_now()
        payload = {
            "hypothesis": hypothesis_text,
            "pre_registered_criteria": dict(pre_registered_criteria),
            "holdout_period": [_date_text(holdout_period[0]), _date_text(holdout_period[1])],
            "cost_and_tax_assumptions": assumptions,
            "requires_replication": requires_replication,
            "linked_strategy_version_id": linked_strategy_version_id,
            "materially_new_hypothesis": materially_new_hypothesis,
            "new_hypothesis_rationale": (new_hypothesis_rationale or "").strip() or None,
        }
        self.connection.execute(
            """INSERT INTO edge_validation_records
            (record_id, attempt_id, event_type, strategy_id, strategy_family,
             verdict, created_at, payload_json)
            VALUES (?, ?, 'HYPOTHESIS', ?, ?, 'PENDING', ?, ?)""",
            (attempt_id, attempt_id, strategy, family, created_at.isoformat(), _json(payload)),
        )
        try:
            self._sync_report()
            self.connection.commit()
        except OSError:
            self.connection.rollback()
            raise
        return attempt_id

    def record_result(
        self,
        record_id: str,
        *,
        bootstrap_ci: tuple[float, float],
        regime_results: Mapping[str, float],
        criteria: AcceptanceCriteria,
        verdict: str,
        replication_result: str | None = None,
        evidence: ExperimentEvidence | None = None,
    ) -> EdgeValidationRecord:
        """Append one final outcome; attempts cannot be revised or retried."""
        if verdict not in {"PASS", "FAIL", "NULL_RESULT"}:
            raise ValueError("verdict must be PASS, FAIL, or NULL_RESULT")
        hypothesis_row = self.connection.execute(
            """SELECT * FROM edge_validation_records
            WHERE record_id = ? AND event_type = 'HYPOTHESIS'""",
            (record_id,),
        ).fetchone()
        if hypothesis_row is None:
            raise KeyError(f"unknown hypothesis record: {record_id}")
        duplicate = self.connection.execute(
            "SELECT 1 FROM edge_validation_records WHERE attempt_id = ? AND event_type = 'RESULT'",
            (record_id,),
        ).fetchone()
        if duplicate is not None:
            raise ValueError("a result is already recorded; attempts are final")
        if not isinstance(criteria, AcceptanceCriteria):
            raise TypeError("criteria must be an AcceptanceCriteria checklist")
        ci = _validate_interval(bootstrap_ci)
        regimes = _validate_regimes(regime_results)
        payload_hypothesis = json.loads(hypothesis_row["payload_json"])
        if verdict == "PASS":
            if ci[0] <= 0:
                raise ValueError("PASS requires a positive bootstrap confidence interval")
            if evidence is None:
                raise ValueError(
                    "PASS requires independently verified experiment evidence; "
                    "provide independently computed experiment evidence"
                )
            if not isinstance(evidence, ExperimentEvidence):
                raise TypeError("evidence must be an ExperimentEvidence instance")
            if evidence.bootstrap_ci[0] <= 0:
                raise ValueError("PASS requires a positive computed bootstrap confidence interval")
            if not _same_ci(ci, evidence.bootstrap_ci):
                raise ValueError("bootstrap_ci must match the computed evidence interval")
            if dict(evidence.regime_returns) != regimes:
                raise ValueError("regime_results must match the computed evidence")
            if not criteria.all_pass:
                raise ValueError("PASS requires all seven acceptance criteria")
            if len(regimes) < 2:
                raise ValueError("PASS requires results in two structurally different regimes")
            if payload_hypothesis["requires_replication"] and replication_result != "PASS":
                raise ValueError("refined hypotheses require a passing independent replication")
            if replication_result not in (None, "PASS", "FAIL", "NULL_RESULT"):
                raise ValueError("replication_result must be PASS, FAIL, NULL_RESULT, or None")
        elif replication_result not in (None, "PASS", "FAIL", "NULL_RESULT"):
            raise ValueError("replication_result must be PASS, FAIL, NULL_RESULT, or None")

        payload = {
            "bootstrap_ci": list(ci),
            "regime_results": regimes,
            "acceptance_checks": criteria.as_dict(),
            "replication_result": replication_result,
        }
        if evidence is not None:
            payload["evidence"] = {
                "dataset_id": evidence.dataset_id,
                "dataset_sha256": evidence.dataset_sha256,
                "net_return": evidence.net_return,
                "fingerprint": evidence.fingerprint(),
            }
        result_id = str(uuid4())
        created_at = _utc_now()
        self.connection.execute(
            """INSERT INTO edge_validation_records
            (record_id, attempt_id, event_type, strategy_id, strategy_family,
             verdict, created_at, payload_json)
            VALUES (?, ?, 'RESULT', ?, ?, ?, ?, ?)""",
            (
                result_id,
                record_id,
                hypothesis_row["strategy_id"],
                hypothesis_row["strategy_family"],
                verdict,
                created_at.isoformat(),
                _json(payload),
            ),
        )
        self.connection.commit()
        self._sync_report()
        return self._record_for_attempt(record_id)

    def get_verdict(self, strategy_id: str) -> str:
        """Return the latest family verdict; unknown or unfinished strategies fail closed."""
        strategy = _normalize_identifier(strategy_id, "strategy_id")
        family = _strategy_family_for_lookup(strategy)
        row = self.connection.execute(
            """SELECT verdict FROM edge_validation_records
            WHERE strategy_family = ?
            ORDER BY rowid DESC LIMIT 1""",
            (family,),
        ).fetchone()
        if row is None:
            return "NOT_TESTED"
        return str(row["verdict"])

    def require_pass(self, strategy_id: str) -> EdgeValidationRecord:
        """Return the latest passing evidence or reject strategy loading."""
        strategy = _normalize_identifier(strategy_id, "strategy_id")
        family = _strategy_family_for_lookup(strategy)
        row = self.connection.execute(
            """SELECT record_id, attempt_id, verdict FROM edge_validation_records
            WHERE strategy_family = ? ORDER BY rowid DESC LIMIT 1""",
            (family,),
        ).fetchone()
        if row is None or row["verdict"] != "PASS":
            verdict = str(row["verdict"]) if row is not None else "NOT_TESTED"
            raise StrategyNotGatedError(
                f"strategy {strategy_id!r} cannot be loaded: latest edge verdict is {verdict}"
            )
        record = self._record_for_attempt(str(row["attempt_id"]))
        if record.verdict != "PASS":
            raise StrategyNotGatedError(
                f"strategy {strategy_id!r} has no current PASS evidence"
            )
        return record

    def delete_record(self, record_id: str) -> None:
        """Repository contract deliberately refuses destructive edits."""
        raise ValueError(f"edge validation records are append-only: {record_id}")

    def list_records(self, strategy_id: str | None = None) -> list[EdgeValidationRecord]:
        """Return one materialized record per registered attempt, in insertion order."""
        if strategy_id is None:
            rows = self.connection.execute(
                "SELECT record_id FROM edge_validation_records WHERE event_type='HYPOTHESIS' ORDER BY rowid"
            ).fetchall()
        else:
            family = _strategy_family_for_lookup(_normalize_identifier(strategy_id, "strategy_id"))
            rows = self.connection.execute(
                """SELECT record_id FROM edge_validation_records
                WHERE event_type='HYPOTHESIS' AND strategy_family=? ORDER BY rowid""",
                (family,),
            ).fetchall()
        result = []
        for row in rows:
            result.append(self._record_for_attempt(str(row["record_id"])))
        return result

    def _seed_falsified_families(self) -> None:
        seeds = (
            ("breakout", "Known breakout variants were falsified in the module 1 specification."),
            ("scalping", "Known scalping variant was falsified in the module 1 specification."),
        )
        for family, hypothesis in seeds:
            found = self.connection.execute(
                "SELECT 1 FROM edge_validation_records WHERE strategy_family = ? LIMIT 1",
                (family,),
            ).fetchone()
            if found is not None:
                continue
            attempt_id = f"seed-{family}"
            created_at = _utc_now()
            payload = {
                "hypothesis": hypothesis,
                "pre_registered_criteria": {"source": "docs/files/01-edge-validation-gate.md"},
                "holdout_period": None,
                "cost_and_tax_assumptions": {},
                "requires_replication": False,
                "linked_strategy_version_id": None,
                "acceptance_checks": None,
                "bootstrap_ci": None,
                "regime_results": {},
                "replication_result": None,
                "seeded_from_specification": True,
            }
            self.connection.execute(
                """INSERT INTO edge_validation_records
                (record_id, attempt_id, event_type, strategy_id, strategy_family,
                 verdict, created_at, payload_json)
                VALUES (?, ?, 'RESULT', ?, ?, 'FAIL', ?, ?)""",
                (attempt_id, attempt_id, family, family, created_at.isoformat(), _json(payload)),
            )
        self.connection.commit()

    def _check_fresh_holdout(self, family: str, period: tuple[date, date]) -> None:
        rows = self.connection.execute(
            """SELECT payload_json FROM edge_validation_records
            WHERE strategy_family = ? AND event_type = 'HYPOTHESIS'""",
            (family,),
        ).fetchall()
        for row in rows:
            prior_period = json.loads(row["payload_json"]).get("holdout_period")
            if prior_period is None:
                continue
            prior_start = date.fromisoformat(prior_period[0])
            prior_end = date.fromisoformat(prior_period[1])
            if period[0] <= prior_end and prior_start <= period[1]:
                raise ValueError("holdout period overlaps a previously registered holdout")

    def _check_unique_hypothesis(self, family: str, hypothesis: str) -> None:
        rows = self.connection.execute(
            """SELECT payload_json FROM edge_validation_records
            WHERE strategy_family = ? AND event_type = 'HYPOTHESIS'""",
            (family,),
        ).fetchall()
        normalized = " ".join(hypothesis.casefold().split())
        for row in rows:
            prior = json.loads(row["payload_json"]).get("hypothesis", "")
            if " ".join(prior.casefold().split()) == normalized:
                raise ValueError("hypothesis already registered for this strategy family")

    def _record_for_attempt(self, attempt_id: str) -> EdgeValidationRecord:
        hypothesis_row = self.connection.execute(
            "SELECT * FROM edge_validation_records WHERE record_id = ? AND event_type='HYPOTHESIS'",
            (attempt_id,),
        ).fetchone()
        if hypothesis_row is None:
            raise KeyError(f"unknown hypothesis record: {attempt_id}")
        payload = json.loads(hypothesis_row["payload_json"])
        result_row = self.connection.execute(
            """SELECT * FROM edge_validation_records
            WHERE attempt_id = ? AND event_type='RESULT' ORDER BY rowid DESC LIMIT 1""",
            (attempt_id,),
        ).fetchone()
        result = json.loads(result_row["payload_json"]) if result_row is not None else {}
        dates = payload["holdout_period"]
        holdout_period = (date.fromisoformat(dates[0]), date.fromisoformat(dates[1]))
        return EdgeValidationRecord(
            record_id=attempt_id,
            strategy_id=str(hypothesis_row["strategy_id"]),
            hypothesis=str(payload["hypothesis"]),
            pre_registered_criteria=dict(payload["pre_registered_criteria"]),
            holdout_period=holdout_period,
            cost_and_tax_assumptions=dict(payload["cost_and_tax_assumptions"]),
            bootstrap_ci=tuple(result["bootstrap_ci"]) if result.get("bootstrap_ci") else None,
            regime_results=dict(result.get("regime_results", {})),
            replication_result=result.get("replication_result"),
            verdict=str(result_row["verdict"] if result_row is not None else "PENDING"),
            linked_strategy_version_id=payload.get("linked_strategy_version_id"),
            created_at=datetime.fromisoformat(
                result_row["created_at"] if result_row is not None else hypothesis_row["created_at"]
            ),
            strategy_family=str(hypothesis_row["strategy_family"]),
            requires_replication=bool(payload["requires_replication"]),
            acceptance_checks=result.get("acceptance_checks"),
        )


def _strategy_family_for_lookup(strategy_id: str) -> str:
    if strategy_id == "breakout" or strategy_id.startswith("breakout_"):
        return "breakout"
    if strategy_id == "scalping" or strategy_id.startswith("scalping_") or strategy_id.startswith("scalp_"):
        return "scalping"
    return strategy_id


def _normalize_identifier(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a non-empty string")
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")
    if not normalized:
        raise ValueError(f"{name} must be a non-empty string")
    if normalized.startswith("breakout_"):
        return "breakout"
    if normalized.startswith(("scalping_", "scalp_")):
        return "scalping"
    return normalized


def _validate_period(period: tuple[date, date]) -> None:
    if not isinstance(period, tuple) or len(period) != 2:
        raise ValueError("holdout_period must be a (start_date, end_date) tuple")
    if not all(isinstance(value, date) and not isinstance(value, datetime) for value in period):
        raise ValueError("holdout_period values must be dates")
    if period[0] > period[1]:
        raise ValueError("holdout_period start must not be after end")


def _validate_preregistered_criteria(criteria: Mapping[str, Any]) -> None:
    if not isinstance(criteria, Mapping) or not criteria:
        raise ValueError("pre_registered_criteria must be a non-empty mapping")
    try:
        _json(dict(criteria))
    except (TypeError, ValueError) as exc:
        raise ValueError("pre_registered_criteria must be JSON-serializable") from exc


def _validate_assumptions(assumptions: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(assumptions, Mapping):
        raise ValueError("cost_and_tax_assumptions must be a mapping")
    missing = []
    for key in REQUIRED_ASSUMPTIONS:
        if key not in assumptions:
            missing.append(key)
    if missing:
        raise ValueError(f"missing cost and tax assumptions: {missing}")
    values = dict(assumptions)
    for key in ("fee_rate", "slippage_rate", "tax_rate", "tds_rate"):
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite non-negative rate")
        if value < 0 or value > 1:
            raise ValueError(f"{key} must be between 0 and 1")
    if values["fee_rate"] < 0.001:
        raise ValueError("fee_rate must be at least 0.10% per side")
    if values["slippage_rate"] < 0.001:
        raise ValueError("slippage_rate must be at least 0.10% per side")
    if not math.isclose(float(values["tax_rate"]), 0.312, abs_tol=1e-9):
        raise ValueError("tax_rate must reflect the specified 31.2% effective VDA tax")
    if not math.isclose(float(values["tds_rate"]), 0.01, abs_tol=1e-9):
        raise ValueError("tds_rate must reflect the specified 1% gross-proceeds TDS")
    if values["loss_offset_allowed"] is not False:
        raise ValueError("loss_offset_allowed must be false")
    if values["tds_is_cash_flow_drag"] is not True:
        raise ValueError("tds_is_cash_flow_drag must be true, not a permanent expense")
    _json(values)
    return values


def _validate_interval(interval: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(interval, (tuple, list)) or len(interval) != 2:
        raise ValueError("bootstrap_ci must contain lower and upper bounds")
    lower, upper = interval
    for value in (lower, upper):
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError("bootstrap confidence interval bounds must be finite numbers")
    if lower > upper:
        raise ValueError("bootstrap confidence interval lower bound exceeds upper bound")
    return float(lower), float(upper)


def _validate_regimes(regime_results: Mapping[str, float]) -> dict[str, float]:
    if not isinstance(regime_results, Mapping):
        raise ValueError("regime_results must be a mapping")
    result = {}
    for regime, value in regime_results.items():
        if not isinstance(regime, str) or not regime.strip():
            raise ValueError("regime names must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError(f"regime result for {regime!r} must be a finite return")
        result[regime.strip()] = float(value)
    return result


def _same_ci(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return all(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12) for a, b in zip(left, right))


def _date_text(value: date) -> str:
    return value.isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)
