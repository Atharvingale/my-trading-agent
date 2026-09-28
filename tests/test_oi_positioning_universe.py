"""Guard tests for the embargo-only universe ranking (Amendment 1)."""

from __future__ import annotations

import research.oi_positioning_universe as uni


def test_guard_rejects_holdout_timestamp() -> None:
    bad = [uni.EMBARGO_START_MS, uni.HOLDOUT_START_MS]
    try:
        uni.assert_embargo_only(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("guard must reject holdout timestamp")


def test_guard_accepts_embargo_only() -> None:
    good = [uni.EMBARGO_START_MS, uni.EMBARGO_END_MS]
    uni.assert_embargo_only(good)


def test_guard_rejects_end_beyond_embargo() -> None:
    try:
        uni.assert_embargo_end_bound(uni.HOLDOUT_START_MS)
    except ValueError:
        pass
    else:
        raise AssertionError("guard must reject end beyond embargo")


def test_guard_accepts_embargo_end() -> None:
    uni.assert_embargo_end_bound(uni.EMBARGO_END_MS)


def test_leveraged_rule_keeps_jup_and_syrup() -> None:
    spot = set(["BTCUSDT", "ETHUSDT", "JUPUSDT", "SYRUPUSDT", "JUUSDT"])
    # JUP/SYRUP end in UP but stripped forms are not spot (JUUSDT is fake
    # here only to show the rule checks membership; real spot lacks them).
    real_spot = set(["BTCUSDT", "ETHUSDT", "JUPUSDT", "SYRUPUSDT"])
    if uni.is_leveraged("JUPUSDT", real_spot) is True:
        raise AssertionError("JUPUSDT is not leveraged")
    if uni.is_leveraged("SYRUPUSDT", real_spot) is True:
        raise AssertionError("SYRUPUSDT is not leveraged")
    true_spot = set(["BTCUSDT", "BTCUPUSDT"])
    if uni.is_leveraged("BTCUPUSDT", true_spot) is False:
        raise AssertionError("BTCUPUSDT is leveraged")


def test_stable_exclusion() -> None:
    if uni.is_stable_or_fiat("USDCUSDT") is False:
        raise AssertionError("USDCUSDT must be excluded")
    if uni.is_stable_or_fiat("FRAXUSDT") is False:
        raise AssertionError("FRAXUSDT must be excluded")
    if uni.is_stable_or_fiat("BTCUSDT") is True:
        raise AssertionError("BTCUSDT must be kept")


def run() -> int:
    test_guard_rejects_holdout_timestamp()
    test_guard_accepts_embargo_only()
    test_guard_rejects_end_beyond_embargo()
    test_guard_accepts_embargo_end()
    test_leveraged_rule_keeps_jup_and_syrup()
    test_stable_exclusion()
    print("oi universe guard tests OK")
    return 0
