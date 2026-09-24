"""Compare a refined strategy with its baseline on an untouched period."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math


@dataclass(frozen=True)
class ReplicationResult:
    primary_period: tuple[date, date]
    replication_period: tuple[date, date]
    primary_net_return: float
    replication_net_return: float
    baseline_replication_net_return: float | None
    improvement_over_baseline: float | None
    passed: bool


def check_replication(
    *,
    primary_period: tuple[date, date],
    replication_period: tuple[date, date],
    primary_net_return: float,
    replication_net_return: float,
    baseline_replication_net_return: float | None = None,
) -> ReplicationResult:
    """Require disjoint periods and positive net results in both periods."""
    _validate_period(primary_period, "primary_period")
    _validate_period(replication_period, "replication_period")
    if not (
        primary_period[1] < replication_period[0]
        or replication_period[1] < primary_period[0]
    ):
        raise ValueError("primary and replication periods must be disjoint")
    _validate_return(primary_net_return, "primary_net_return")
    _validate_return(replication_net_return, "replication_net_return")
    if baseline_replication_net_return is not None:
        _validate_return(baseline_replication_net_return, "baseline_replication_net_return")

    improvement = None
    baseline_passes = True
    if baseline_replication_net_return is not None:
        improvement = replication_net_return - baseline_replication_net_return
        baseline_passes = improvement > 0

    return ReplicationResult(
        primary_period=primary_period,
        replication_period=replication_period,
        primary_net_return=primary_net_return,
        replication_net_return=replication_net_return,
        baseline_replication_net_return=baseline_replication_net_return,
        improvement_over_baseline=improvement,
        passed=(primary_net_return > 0 and replication_net_return > 0 and baseline_passes),
    )


def _validate_period(period: tuple[date, date], name: str) -> None:
    if len(period) != 2 or not all(isinstance(value, date) for value in period):
        raise ValueError(f"{name} must contain start and end dates")
    if period[0] > period[1]:
        raise ValueError(f"{name} start must not be after end")


def _validate_return(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
