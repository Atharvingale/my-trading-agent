"""Persistence check for audit/ledger artifacts (Cycle 4 durability fix).

Run at the start of every future task, before treating any prior-task file
as ground truth: confirms each expected artifact exists on disk with
non-trivial content. Exits 0 when everything is present, 1 otherwise with
the missing list printed. Read-only: never writes, never touches the
ledger, the menu, or any strategy/execution/risk path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent

# Minimum plausible byte sizes guard against truncated/empty writes.
EXPECTED_FILES = (
    ("docs/results/oi-liquidation-public-archive-coverage-audit.md", 50000),
    ("docs/results/oi-liquidation-coverage-audit.md", 5000),
    ("docs/results/D1-D3-NOTE.md", 300),
    ("docs/files/implementation-log.md", 50000),
    ("docs/files/module-status.md", 2000),
    ("research/reports/d1_d3_closure.json", 500),
    ("research/reports/liquidation_intensity_closure.json", 500),
    ("research/reports/cross_sectional_rs_gate_run.json", 2000),
    ("research/hypotheses/cross_sectional_rs_001.md", 3000),
)

# SQLite ledgers that must open and hold at least the known baseline rows.
EXPECTED_TABLE_COUNTS = (
    ("research/runtime_edge_validation.sqlite3", "edge_validation_records", 24),
    ("research/hypothesis_menu.sqlite3", "menu_additions", 2),
)


def main() -> int:
    failures = []
    for relative, minimum in EXPECTED_FILES:
        target = REPO / relative
        if not target.is_file():
            failures.append("%s: MISSING" % relative)
            continue
        size = target.stat().st_size
        if size < minimum:
            failures.append("%s: present but too small (%d < %d bytes)"
                            % (relative, size, minimum))
    for relative, table, minimum in EXPECTED_TABLE_COUNTS:
        target = REPO / relative
        if not target.is_file():
            failures.append("%s: MISSING" % relative)
            continue
        try:
            connection = sqlite3.connect(target)
            try:
                total = connection.execute(
                    "SELECT COUNT(*) FROM %s" % table).fetchone()[0]
            finally:
                connection.close()
        except Exception as exc:
            failures.append("%s: unreadable (%s)" % (relative, exc))
            continue
        if total < minimum:
            failures.append("%s: only %d rows in %s, expected at least %d"
                            % (relative, total, table, minimum))
    if failures:
        print("PERSISTENCE CHECK FAILED:")
        for failure in failures:
            print("  - " + failure)
        return 1
    print("persistence check OK: %d files + %d ledgers verified"
          % (len(EXPECTED_FILES), len(EXPECTED_TABLE_COUNTS)))
    return 0


def run() -> int:
    """Entry point for `python -c "from scripts.verify_artifacts import run"`;
    kept guard-free per project coding conventions (no __main__ blocks)."""
    import sys as _sys

    return main()


# Invocation: python -c "import sys; sys.path.insert(0, '.'); from scripts.verify_artifacts import run; sys.exit(run())"
