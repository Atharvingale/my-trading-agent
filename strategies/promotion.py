"""Promotion adapter: candidate PASS + human approval -> production version.

Why this file exists: Module 15 may produce a CandidateStrategyVersion, but
Module 4 may consume it only after PASS plus explicit human approval plus an
immutable production version row. This adapter is the single narrow bridge
between candidate_generation/review_queue.py and strategies/registry.py, so
the existing gate check stays authoritative and no raw candidate can slip in.
"""

from __future__ import annotations

from candidate_generation.review_queue import ReviewQueue
from edge_validation.registry import EdgeValidationRegistry, StrategyNotGatedError
from strategies.production_versions import ProductionVersion, ProductionVersionStore


def promote_candidate(
    *,
    strategy_id: str,
    edge_validation_record_id: str,
    registry: EdgeValidationRegistry,
    reviews: ReviewQueue,
    versions: ProductionVersionStore,
    approver: str,
    rationale: str,
    version_id: str | None = None,
) -> ProductionVersion:
    """Create an immutable production version after PASS + human approval.

    Raises StrategyNotGatedError unless the edge record is the current PASS
    for the strategy and a human has approved that exact record. Neither
    condition alone is enough.
    """
    name = str(strategy_id).strip()
    if not name:
        raise ValueError("strategy_id must be non-empty")
    record_token = str(edge_validation_record_id).strip()
    if not record_token:
        raise ValueError("edge_validation_record_id must be non-empty")
    # Fail-closed: the edge record must be the live PASS, not a stale PASS
    # superseded by a later FAIL or PENDING attempt.
    record = registry.require_pass(name)
    if record.record_id != record_token:
        raise StrategyNotGatedError(
            "strategy %r has no current PASS for record %r" % (name, record_token)
        )
    if reviews.is_approved(record_token) is False:
        raise StrategyNotGatedError(
            "record %r has PASS but no explicit human approval" % (record_token,)
        )
    who = str(approver).strip()
    if not who:
        raise ValueError("approver must be non-empty")
    why = str(rationale).strip()
    if not why:
        raise ValueError("rationale must be non-empty")
    vid = str(version_id).strip() if version_id is not None else ""
    if not vid:
        vid = "%s@%s" % (record.strategy_id, record.record_id[:8])
    linked = record.linked_strategy_version_id
    if linked is not None and str(linked).strip():
        vid = str(linked).strip()
    return versions.create_version(
        version_id=vid,
        strategy_id=record.strategy_id,
        edge_validation_record_id=record.record_id,
        approver=who,
        rationale=why,
        approved_at=None,
    )
