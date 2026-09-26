"""Append-only human-readable audit trail for edge experiments."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping


HEADER = "# Edge Validation Experiment Registry\n\nAppend-only preregistration and outcome log. Hypotheses are recorded before results.\n\n"


def append_hypothesis(
    path: str | Path,
    record_id: str,
    strategy_id: str,
    strategy_family: str,
    payload: Mapping[str, Any],
    created_at: datetime,
) -> None:
    """Append the frozen hypothesis and acceptance thresholds before testing."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(HEADER, encoding="utf-8")
    criteria = json.dumps(payload["pre_registered_criteria"], indent=2, sort_keys=True)
    assumptions = json.dumps(payload["cost_and_tax_assumptions"], indent=2, sort_keys=True)
    period = payload["holdout_period"]
    # Provenance lines retain the Module 15 candidate lineage without weakening the gate.
    text = (
        f"## Preregistered hypothesis — {created_at.isoformat()}\n\n"
        f"- Record ID: `{record_id}`\n"
        f"- Strategy: `{strategy_id}` (family `{strategy_family}`)\n"
        f"- Hypothesis: {payload['hypothesis']}\n"
        f"- Holdout: {period[0]} through {period[1]}\n"
        f"- Requires independent replication: {payload['requires_replication']}\n"
        f"- Materially new rationale: {payload.get('new_hypothesis_rationale') or 'None'}\n"
        f"- Source: `{payload.get('source') or 'HUMAN'}`\n"
        f"- Candidate ID: `{payload.get('candidate_id') or 'None'}`\n"
        f"- Parent candidate ID: `{payload.get('parent_candidate_id') or 'None'}`\n"
        f"- Hypothesis ID: `{payload.get('hypothesis_id') or 'None'}`\n"
        f"- Signal class: `{payload.get('signal_class') or 'None'}`\n"
        f"- Provider: `{payload.get('provider_used') or 'None'}`\n"
        f"- Multiple-testing family: `{payload.get('multiple_testing_family') or 'None'}`\n"
        f"- Multiple-testing threshold: `{payload.get('multiple_testing_threshold')}`\n"
        f"- Pre-registered thresholds:\n\n```json\n{criteria}\n```\n"
        f"- Cost and tax assumptions:\n\n```json\n{assumptions}\n```\n\n"
        "Outcome: PENDING — no results recorded yet.\n\n---\n\n"
    )
    _append(target, text)


def append_result(
    path: str | Path,
    record_id: str,
    verdict: str,
    payload: Mapping[str, Any],
    created_at: datetime,
) -> None:
    """Append an immutable result referencing its prior preregistration."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(HEADER, encoding="utf-8")
    rendered = json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False)
    text = (
        f"## Result — {created_at.isoformat()}\n\n"
        f"- Preregistration record ID: `{record_id}`\n"
        f"- Verdict: **{verdict}**\n"
        f"- Evidence:\n\n```json\n{rendered}\n```\n\n---\n\n"
    )
    _append(target, text)


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as report:
        report.write(text)
