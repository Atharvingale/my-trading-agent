"""Allowed signal-class menu for the research plane (Module 15).

Why this file exists: the generator may only draw from an explicit,
human-maintained list. Classes already falsified through Module 1 are
permanently excluded with reasons, so automation can never quietly re-propose
a repackaged Breakout/Trend/Mean-Reversion variant. Adding a new class needs
a one-line human sign-off (approver + rationale), persisted for audit.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Initial approved menu: the two structurally different, still-untested
# classes named in Module 1. Everything else needs human sign-off first.
INITIAL_APPROVED = (
    "funding-rate carry",
    "cross-exchange dislocation",
)

# Permanently excluded: falsified through the Module 1 gate (7/7 FAIL).
# Keys are normalized signal names, values are the recorded reasons.
EXCLUDED = {
    "breakout": "FALSIFIED per Module 1: net -27.78%, bootstrap CI entirely negative",
    "scalping": "FALSIFIED per Module 1: net -39.42%, bootstrap CI entirely negative",
    "trend following": "FAILED per Module 1: net -5.34%, CI [-1.73%, -0.67%]",
    "order flow": "FAILED per Module 1: net -10.13%, CI [-1.64%, -1.22%]",
    "mean reversion": "FAILED per Module 1: net -9.49%, CI [-1.86%, -1.23%]",
    "vwap reversion": "FAILED per Module 1: net -1.13%, CI [-1.85%, -0.30%], only 16 trades",
    "daily trend": "FAILED per Module 1 probe: net -1.10%, CI [-3.27%, -0.15%], only 8 trades",
    "daily trend following": "FAILED per Module 1 probe: net -1.10%, CI [-3.27%, -0.15%], only 8 trades",
}


def normalize_signal_class(value: str) -> str:
    """Collapse case, dashes, underscores and whitespace to one comparable key."""
    text = str(value).strip().casefold()
    cleaned = ""
    for char in text:
        if char == "_" or char == "-":
            cleaned = cleaned + " "
        else:
            cleaned = cleaned + char
    parts: list[str] = []
    for part in cleaned.split():
        if part:
            parts.append(part)
    return " ".join(parts)


class HypothesisMenu:
    """Approved + excluded signal classes with human-gated additions."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.path: Path | None = None
        self.connection: sqlite3.Connection | None = None
        self._memory_additions: list[dict[str, str]] = []
        if database_path is not None:
            self.path = Path(database_path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(self.path)
            self.connection.row_factory = sqlite3.Row
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS menu_additions (
                    signal_class TEXT PRIMARY KEY,
                    normalized TEXT NOT NULL UNIQUE,
                    approver TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    approved_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS menu_additions_no_update
                BEFORE UPDATE ON menu_additions
                BEGIN
                    SELECT RAISE(ABORT, 'menu_additions are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS menu_additions_no_delete
                BEFORE DELETE ON menu_additions
                BEGIN
                    SELECT RAISE(ABORT, 'menu_additions are append-only');
                END;
                """
            )
            self.connection.commit()

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()

    def __enter__(self) -> HypothesisMenu:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def is_excluded(self, signal_class: str) -> bool:
        key = normalize_signal_class(signal_class)
        return key in EXCLUDED

    def exclusion_reason(self, signal_class: str) -> str | None:
        key = normalize_signal_class(signal_class)
        if key in EXCLUDED:
            return str(EXCLUDED[key])
        # Why substring matching: a repackaged variant ("Breakout 24/12/14
        # hourly", "order-flow v2") must not slip past an exact-match check.
        for excluded_key in EXCLUDED:
            if excluded_key and excluded_key in key:
                return "repackaged '%s': %s" % (excluded_key, str(EXCLUDED[excluded_key]))
        return None

    def is_allowed(self, signal_class: str) -> bool:
        """True only for approved, non-excluded classes (fail-closed)."""
        key = normalize_signal_class(signal_class)
        if key in EXCLUDED:
            return False
        for approved in self.list_approved():
            if normalize_signal_class(approved) == key:
                return True
        return False

    def check(self, signal_class: str) -> dict[str, Any]:
        """Classify without raising: allowed flag plus exclusion reason."""
        name = str(signal_class).strip()
        if not name:
            return {"allowed": False, "excluded_because": "empty signal class"}
        reason = self.exclusion_reason(name)
        if reason is not None:
            return {"allowed": False, "excluded_because": reason}
        if self.is_allowed(name):
            return {"allowed": True, "excluded_because": None}
        return {
            "allowed": False,
            "excluded_because": "signal class '%s' is not on the approved menu; human sign-off required" % name,
        }

    def require_allowed(self, signal_class: str) -> str:
        """Return the cleaned name or raise before anything reaches the gate."""
        verdict = self.check(signal_class)
        if verdict["allowed"] is not True:
            raise ValueError(str(verdict["excluded_because"]))
        return str(signal_class).strip()

    def add_with_approval(self, signal_class: str, approver: str, rationale: str) -> str:
        """One-line human sign-off to admit a genuinely new signal class."""
        name = str(signal_class).strip()
        if not name:
            raise ValueError("signal_class must be non-empty")
        who = str(approver).strip()
        if not who:
            raise ValueError("approver must be non-empty: no anonymous menu change")
        why = str(rationale).strip()
        if not why:
            raise ValueError("rationale must be non-empty: no unexplained menu change")
        key = normalize_signal_class(name)
        if key in EXCLUDED:
            raise ValueError("cannot re-admit excluded class '%s': %s" % (name, EXCLUDED[key]))
        for approved in self.list_approved():
            if normalize_signal_class(approved) == key:
                return approved
        stamped = datetime.now(timezone.utc).isoformat()
        if self.connection is not None:
            self.connection.execute(
                "INSERT INTO menu_additions (signal_class, normalized, approver, rationale, approved_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (name, key, who, why, stamped),
            )
            self.connection.commit()
        else:
            self._memory_additions.append({"signal_class": name, "approver": who, "rationale": why})
        return name

    def list_approved(self) -> list[str]:
        """Initial menu plus every human-approved addition, in admit order."""
        approved: list[str] = []
        for name in INITIAL_APPROVED:
            approved.append(name)
        if self.connection is not None:
            rows = self.connection.execute(
                "SELECT signal_class FROM menu_additions ORDER BY rowid"
            ).fetchall()
            for row in rows:
                approved.append(str(row["signal_class"]))
        else:
            for entry in self._memory_additions:
                approved.append(str(entry["signal_class"]))
        return approved

    def list_excluded(self) -> list[dict[str, str]]:
        """Excluded classes with reasons, in a fixed order for audit."""
        order: list[str] = []
        order.append("breakout")
        order.append("scalping")
        order.append("trend following")
        order.append("order flow")
        order.append("mean reversion")
        order.append("vwap reversion")
        order.append("daily trend")
        order.append("daily trend following")
        result: list[dict[str, str]] = []
        for key in order:
            if key in EXCLUDED:
                result.append({"signal_class": key, "reason": str(EXCLUDED[key])})
        return result
