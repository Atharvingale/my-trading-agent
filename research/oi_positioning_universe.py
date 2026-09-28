"""OI positioning universe ranking (embargo-only, Amendment 1 guard).

Why this file exists: the Cycle 4 universe must be ranked on the embargo
window 2025-06-01..2025-08-31 only, never touching holdout (2025-09-01 on).
A prior session fetched one extra day (2025-09-01) via inclusive endTime;
that ranking was discarded. This module enforces the boundary in code.
"""

from __future__ import annotations


EMBARGO_START_MS = 1748736000000
EMBARGO_END_MS = 1756684799999
HOLDOUT_START_MS = 1756684800000
EXPECTED_EMBARGO_DAYS = 92
MIN_QUOTE_VOLUME_PER_DAY = 10000000.0

STABLE_FIAT_BASES = (
    "USDC",
    "FDUSD",
    "TUSD",
    "USDP",
    "DAI",
    "USDD",
    "FRAX",
    "LUSD",
    "SUSD",
    "GUSD",
    "PYUSD",
    "AEUR",
    "EUR",
    "EURI",
    "GBP",
    "BRL",
    "TRY",
    "ARS",
    "MXN",
)

INDEX_SYMBOLS = (
    "BTCDOMUSDT",
)


def assert_embargo_only(open_times_ms: list) -> None:
    """Fail closed if any timestamp reaches the holdout start.

    Why strict: Binance kline ranges are inclusive, so callers must use
    endTime <= 2025-08-31T23:59:59.999Z. Any timestamp at or after
    2025-09-01T00:00:00Z means holdout data entered the ranking input.
    """
    for stamp in open_times_ms:
        if int(stamp) >= HOLDOUT_START_MS:
            raise ValueError("embargo guard: timestamp reaches holdout start")


def assert_embargo_end_bound(end_ms: int) -> None:
    """Fail closed unless the call end bound stays inside the embargo."""
    if int(end_ms) > EMBARGO_END_MS:
        raise ValueError("embargo guard: endTime exceeds embargo end")


def is_leveraged(symbol: str, spot_set: set) -> bool:
    """Corrected rule: UP/DOWN only when stripped underlying is spot.

    Why this form: JUPUSDT and SYRUPUSDT end in UP but their stripped
    forms (JUUSDT, SYRUSDT) are not spot symbols, so they are not
    leveraged tokens and must not be excluded.
    """
    token = str(symbol).strip().upper()
    if token.endswith("UPUSDT"):
        core = token[0:len(token) - 6]
        underlying = core + "USDT"
        if underlying in spot_set:
            return True
        return False
    if token.endswith("DOWNUSDT"):
        core = token[0:len(token) - 8]
        underlying = core + "USDT"
        if underlying in spot_set:
            return True
        return False
    if token.endswith("BULLUSDT"):
        return True
    if token.endswith("BEARUSDT"):
        return True
    return False


def is_stable_or_fiat(symbol: str) -> bool:
    """True for stablecoin and fiat-pegged bases quoted in USDT."""
    token = str(symbol).strip().upper()
    if token.endswith("USDT") is False:
        return False
    base = token[0:len(token) - 4]
    for name in STABLE_FIAT_BASES:
        if base == name:
            return True
    return False


def is_index_product(symbol: str) -> bool:
    """True for index/derived products that are not single-asset spot."""
    token = str(symbol).strip().upper()
    for name in INDEX_SYMBOLS:
        if token == name:
            return True
    return False


def average_quote_volume(quote_volumes: list) -> float:
    """Mean daily quote volume with an explicit loop (no hidden weighting)."""
    total = 0.0
    count = 0
    for value in quote_volumes:
        total = total + float(value)
        count = count + 1
    if count == 0:
        return 0.0
    return total / float(count)


def rank_descending(entries: list) -> list:
    """Order (avg, symbol, n) by avg descending via explicit insertion."""
    ordered: list = []
    for item in entries:
        placed = False
        index = 0
        while index < len(ordered):
            if item[0] > ordered[index][0]:
                ordered.insert(index, item)
                placed = True
                break
            index = index + 1
        if placed is False:
            ordered.append(item)
    return ordered
