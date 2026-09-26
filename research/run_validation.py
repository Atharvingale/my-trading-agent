"""Funding + dislocation validation run (Module 1 research, operator-invoked).

Produces research/reports/funding_xex_validation.json and .md: bounded
hypothesis sets, data-quality findings, descriptive stats, multiple-testing
accounting, and INCONCLUSIVE verdicts with exact missing-data specs. No gate
records are written, no holdout is touched, nothing is promoted.

Invoke with: python -c "from research.run_validation import main; main()"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from candidate_generation import multiple_testing
from candidate_generation.generator import CandidateGenerator
from candidate_generation.hypothesis_menu import HypothesisMenu
from research import dislocation as dis
from research import funding_carry as fund

BASE_ALPHA = 0.05
GATE_LEDGER = "research/runtime_edge_validation.sqlite3"
CANDIDATES_DB = "research/candidates_funding_xex.sqlite3"
MARKET_DB = "data/market_data.sqlite3"

FUNDING_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "signal_class": "funding-rate carry",
        "rationale": "Short perp when trailing-3 mean funding exceeds 0.01%, hold one 8h period; carry minus price drift.",
        "proposed_entry_exit_rules": {"hypothesis": "F1", "direction": "SHORT", "threshold": 0.0001, "persistence": 3, "holding_periods": 1},
    },
    {
        "signal_class": "funding-rate carry",
        "rationale": "F1 restricted to calm periods (realized vol below trailing median); same one-period hold.",
        "proposed_entry_exit_rules": {"hypothesis": "F2", "direction": "SHORT", "threshold": 0.0005, "persistence": 3, "holding_periods": 1, "volatility_filter": True},
    },
    {
        "signal_class": "funding-rate carry",
        "rationale": "Mirror long when trailing-3 mean funding is below -0.01%; collect negative funding over one period.",
        "proposed_entry_exit_rules": {"hypothesis": "F3", "direction": "LONG", "threshold": -0.0001, "persistence": 3, "holding_periods": 1},
    },
)

DISLOCATION_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "signal_class": "cross-exchange dislocation",
        "rationale": "Disagreement at or above 5bps for 3 consecutive confirmations, 1h convergence window.",
        "proposed_entry_exit_rules": {"hypothesis": "D1", "threshold_bps": 5.0, "persistence": 3, "convergence_hours": 1.0},
    },
    {
        "signal_class": "cross-exchange dislocation",
        "rationale": "Stricter 10bps leg of the same dislocation sketch.",
        "proposed_entry_exit_rules": {"hypothesis": "D2", "threshold_bps": 10.0, "persistence": 3, "convergence_hours": 1.0},
    },
    {
        "signal_class": "cross-exchange dislocation",
        "rationale": "Rare-event leg: 20bps held for 5 confirmations, 2h window.",
        "proposed_entry_exit_rules": {"hypothesis": "D3", "threshold_bps": 20.0, "persistence": 5, "convergence_hours": 2.0},
    },
)


def main(
    market_db: str = MARKET_DB,
    candidates_db: str = CANDIDATES_DB,
    out_dir: str = "research/reports",
    today: str = "2026-09-26",
) -> dict[str, Any]:
    """Run the full validation pass and write JSON + Markdown artifacts."""
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    menu = HypothesisMenu()
    generator = CandidateGenerator(candidates_db, menu=menu, min_interval_seconds=0)
    try:
        registered = _register(generator)
        funding_obs = fund.load_from_market_db(market_db, symbols=["BTCUSDT", "ETHUSDT"])
        xex_obs = dis.load_from_market_db(market_db, symbols=["BTCUSDT", "ETHUSDT"])
        funding_quality = fund.quality_gate(funding_obs)
        xex_quality = dis.quality_gate(xex_obs)
        tested = multiple_testing.count_hypotheses(database_path=GATE_LEDGER)
        future_threshold = multiple_testing.required_significance(
            base_alpha=BASE_ALPHA, total_tested=tested + 1
        )
        funding_stats = fund.describe_stats(funding_obs)
        xex_stats = _xex_stats(xex_obs)
        crossings: list[dict[str, Any]] = []
        for hypothesis in dis.DISLOCATION_HYPOTHESES:
            crossings.append(dis.describe_crossings(xex_obs, hypothesis))
        funding_eval = fund.evaluate_sufficiency(funding_obs, regime_legs=["single-33d-window"], total_tested_elsewhere=tested)
        xex_eval = dis.evaluate_sufficiency(xex_obs, regime_legs=["single-4d-window"], total_tested_elsewhere=tested)
        artifact: dict[str, Any] = {}
        artifact["run_date"] = today
        artifact["market_db"] = market_db
        artifact["gate_ledger"] = GATE_LEDGER
        artifact["multiple_testing"] = {
            "method": "bonferroni",
            "base_alpha": BASE_ALPHA,
            "ledger_hypotheses_tested": tested,
            "new_hypotheses_registered": 6,
            "new_hypotheses_tested": 0,
        }
        artifact["multiple_testing"]["adjusted_threshold_now"] = None
        artifact["multiple_testing"]["adjusted_threshold_when_tested"] = future_threshold
        artifact["multiple_testing"]["note"] = (
            "Registered candidates consume no budget until tested; the first "
            "future test faces alpha %.6f." % future_threshold
        )
        artifact["funding"] = {
            "n_observations": len(funding_obs),
            "dataset_hash": fund.dataset_hash(funding_obs),
            "quality": funding_quality,
            "descriptive": funding_stats,
            "hypotheses": _hypothesis_ids(fund.FUNDING_HYPOTHESES),
            "candidates": registered["funding"],
            "evaluation": funding_eval,
            "verdict": "INCONCLUSIVE",
        }
        artifact["dislocation"] = {
            "n_observations": len(xex_obs),
            "dataset_hash": dis.dataset_hash(xex_obs),
            "quality": xex_quality,
            "descriptive": xex_stats,
            "threshold_crossings": crossings,
            "hypotheses": _hypothesis_ids(dis.DISLOCATION_HYPOTHESES),
            "candidates": registered["dislocation"],
            "evaluation": xex_eval,
            "verdict": "INCONCLUSIVE",
        }
        artifact["gate_records_written"] = 0
        artifact["holdout_consumed"] = None
        artifact["production_approved"] = 0
        (target / "funding_xex_validation.json").write_text(
            json.dumps(artifact, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        (target / "funding_xex_validation.md").write_text(_render_markdown(artifact), encoding="utf-8")
        return artifact
    finally:
        generator.close()
        menu.close()


def _hypothesis_ids(hypotheses: Any) -> list[str]:
    # Explicit loop per project conventions (no comprehensions).
    ids: list[str] = []
    for hypothesis in hypotheses:
        ids.append(hypothesis.hypothesis_id)
    return ids


def _register(generator: CandidateGenerator) -> dict[str, list[dict[str, str]]]:
    registered: dict[str, list[dict[str, str]]] = {"funding": [], "dislocation": []}
    for candidate in FUNDING_CANDIDATES:
        hypothesis = generator.generate_from_response(dict(candidate), provider_used="research-operator")
        assert hypothesis is not None
        registered["funding"].append({
            "candidate_id": hypothesis.candidate_id,
            "hypothesis_id": hypothesis.hypothesis_id,
            "signal_class": hypothesis.signal_class,
        })
    for candidate in DISLOCATION_CANDIDATES:
        hypothesis = generator.generate_from_response(dict(candidate), provider_used="research-operator")
        assert hypothesis is not None
        registered["dislocation"].append({
            "candidate_id": hypothesis.candidate_id,
            "hypothesis_id": hypothesis.hypothesis_id,
            "signal_class": hypothesis.signal_class,
        })
    return registered


def _xex_stats(observations: list) -> dict[str, Any]:
    values: list[float] = []
    confirmed = 0
    for obs in observations:
        if obs.status == "CONFIRMED" and obs.disagreement_bps is not None:
            confirmed = confirmed + 1
            values.append(float(obs.disagreement_bps))
    ordered: list[float] = []
    for value in values:
        placed = False
        index = 0
        while index < len(ordered):
            if value < ordered[index]:
                ordered.insert(index, value)
                placed = True
                break
            index = index + 1
        if placed is False:
            ordered.append(value)
    percentiles: dict[str, float] = {}
    if ordered:
        for frac, name in ((0.5, "p50"), (0.9, "p90"), (0.99, "p99")):
            position = int(frac * (len(ordered) - 1))
            percentiles[name] = ordered[position]
    return {"n": len(observations), "confirmed": confirmed, "disagreement_bps": percentiles}


def _render_markdown(artifact: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Funding-Rate Carry + Cross-Exchange Dislocation — Module 1 Validation")
    lines.append("")
    lines.append("Run date: %s. Verdicts: funding INCONCLUSIVE, dislocation INCONCLUSIVE." % artifact["run_date"])
    lines.append("Gate records written: 0. Holdout consumed: none. Production approved: 0.")
    lines.append("")
    lines.append("## Multiple testing")
    mt = artifact["multiple_testing"]
    lines.append("Method: %s, base alpha %.3f, ledger tested %d, registered 6, tested 0." % (
        mt["method"], mt["base_alpha"], mt["ledger_hypotheses_tested"]))
    lines.append(str(mt["note"]))
    lines.append("")
    lines.append("## Funding-rate carry — INCONCLUSIVE")
    funding = artifact["funding"]
    lines.append("Observations: %d, hash `%s`." % (funding["n_observations"], funding["dataset_hash"][:16]))
    lines.append("Quality: %s." % json.dumps(funding["quality"], sort_keys=True))
    lines.append("Descriptive: %s." % json.dumps(funding["descriptive"], sort_keys=True))
    lines.append("Evaluation: %s." % json.dumps(funding["evaluation"], sort_keys=True))
    lines.append("Missing for gate evidence: multi-month funding history spanning at least two "
                 "regime legs (have 33 days / one leg), longer per-symbol series, dated holdout windows.")
    lines.append("")
    lines.append("## Cross-exchange dislocation — INCONCLUSIVE")
    xex = artifact["dislocation"]
    lines.append("Observations: %d, hash `%s`." % (xex["n_observations"], xex["dataset_hash"][:16]))
    lines.append("Quality: %s." % json.dumps(xex["quality"], sort_keys=True))
    lines.append("Threshold crossings (descriptive, not returns): %s." % json.dumps(xex["threshold_crossings"], sort_keys=True))
    lines.append("Evaluation: %s." % json.dumps(xex["evaluation"], sort_keys=True))
    lines.append("Missing for gate evidence: synchronized per-venue bid/ask quotes with spreads, "
                 "depth, fee schedules, and latency assumptions, spanning at least two regime legs "
                 "(have ~4.4 days of aggregate disagreement only).")
    lines.append("")
    return "\n".join(lines)
