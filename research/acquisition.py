"""Evidence-grade historical acquisition + validation (Module 1 research).

Provider abstraction with immutable versioned datasets: fetch, normalize,
validate, and store raw rows with a manifest (dataset_id, provider, venue,
symbol, range, count, retrieval time, content hash, schema version). Refreshes
create new versions; stored artifacts are never overwritten. Public endpoints
only; credentials (if ever needed) come from the environment and never logs.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from security.redaction import redact

SCHEMA_VERSION = 1
EIGHT_HOURS_MS = 8 * 3600 * 1000
ONE_HOUR_MS = 3600 * 1000
USER_AGENT = "hermes-research/1.0"


class AcquisitionError(RuntimeError):
    """Raised when a provider cannot supply trustworthy history."""


def http_get_json(url: str, timeout_seconds: int = 30) -> Any:
    """GET one public URL and parse JSON; transport errors become AcquisitionError."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except Exception as exc:
        raise AcquisitionError("GET failed for %s" % _safe_host(url)) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise AcquisitionError("non-JSON response from %s" % _safe_host(url)) from exc


def _safe_host(url: str) -> str:
    # Why host-only: full URLs can carry keys in query strings, and must never
    # reach an exception message or log line unredacted.
    return redact(url.split("?")[0])


class FundingHistoryProvider:
    """Binance USDⓈ-M funding-rate history (public, no credentials)."""

    name = "binance-fapi-funding"
    venue = "binance-futures"

    def __init__(self, base_url: str | None = None, pause_seconds: float = 0.3) -> None:
        # Why env-first: endpoint configuration lives outside code so staging
        # mirrors and outages are handled without edits; never credentials.
        url = base_url or os.environ.get("HERMES_FUNDING_API_BASE") or "https://fapi.binance.com"
        self.base_url = str(url).rstrip("/")
        self.pause_seconds = float(pause_seconds)

    def fetch(self, symbol: str, *, limit: int = 1000, end_time_ms: int | None = None) -> list[dict[str, Any]]:
        """Fetch up to `limit` settled funding rows ending at end_time_ms."""
        token = str(symbol).strip().upper()
        if not token:
            raise ValueError("symbol must be non-empty")
        rows: list[dict[str, Any]] = []
        cursor: int | None = end_time_ms
        remaining = int(limit)
        while remaining > 0:
            page = min(remaining, 1000)
            url = "%s/fapi/v1/fundingRate?symbol=%s&limit=%d" % (self.base_url, token, page)
            if cursor is not None:
                url = url + "&endTime=%d" % int(cursor)
            payload = http_get_json(url)
            if not isinstance(payload, list) or len(payload) == 0:
                break
            for item in payload:
                rows.append(item)
            remaining = remaining - len(payload)
            oldest = payload[-1].get("fundingTime")
            if oldest is None or len(payload) < page:
                break
            cursor = int(oldest) - 1
            time.sleep(self.pause_seconds)
        normalized: list[dict[str, Any]] = []
        for item in rows:
            normalized.append(normalize_funding_row(item, self.venue))
        return normalized


class KlinesProvider:
    """Binance spot hourly klines for execution/reference prices (public)."""

    name = "binance-spot-klines"
    venue = "binance-spot"

    def __init__(self, base_url: str | None = None, pause_seconds: float = 0.3) -> None:
        url = base_url or os.environ.get("HERMES_KLINES_API_BASE") or "https://api.binance.com"
        self.base_url = str(url).rstrip("/")
        self.pause_seconds = float(pause_seconds)

    def fetch(self, symbol: str, *, interval: str = "1h", limit: int = 1000,
              end_time_ms: int | None = None) -> list[dict[str, Any]]:
        token = str(symbol).strip().upper()
        if not token:
            raise ValueError("symbol must be non-empty")
        rows: list[dict[str, Any]] = []
        cursor: int | None = end_time_ms
        remaining = int(limit)
        while remaining > 0:
            page = min(remaining, 1000)
            url = "%s/api/v3/klines?symbol=%s&interval=%s&limit=%d" % (
                self.base_url, token, interval, page)
            if cursor is not None:
                url = url + "&endTime=%d" % int(cursor)
            payload = http_get_json(url)
            if not isinstance(payload, list) or len(payload) == 0:
                break
            for item in payload:
                rows.append(normalize_kline_row(item, token, interval, self.venue))
            remaining = remaining - len(payload)
            if len(payload) < page:
                break
            cursor = int(payload[0][0]) - 1
            time.sleep(self.pause_seconds)
        return rows


class CoinbaseCandlesProvider:
    """Coinbase Exchange spot candles, hourly (public, 300 per call)."""

    name = "coinbase-spot-candles"
    venue = "coinbase"

    def __init__(self, base_url: str | None = None, pause_seconds: float = 0.5) -> None:
        url = base_url or os.environ.get("HERMES_COINBASE_API_BASE") or "https://api.exchange.coinbase.com"
        self.base_url = str(url).rstrip("/")
        self.pause_seconds = float(pause_seconds)

    def fetch(self, product_id: str, *, granularity: int = 3600, pages: int = 30) -> list[dict[str, Any]]:
        """Page backwards from now; each page holds up to 300 candles."""
        product = str(product_id).strip().upper()
        if not product:
            raise ValueError("product_id must be non-empty")
        rows: list[dict[str, Any]] = []
        end: int | None = None
        page = 0
        while page < int(pages):
            url = "%s/products/%s/candles?granularity=%d" % (self.base_url, product, granularity)
            if end is not None:
                url = url + "&end=%d" % end
            payload = http_get_json(url)
            if not isinstance(payload, list) or len(payload) == 0:
                break
            for item in payload:
                rows.append(normalize_coinbase_row(item, product, self.venue))
            end = int(payload[-1][0]) - granularity
            page = page + 1
            time.sleep(self.pause_seconds)
        return rows


class KrakenOhlcProvider:
    """Kraken spot OHLC, hourly (public, 720 candles per call)."""

    name = "kraken-spot-ohlc"
    venue = "kraken"

    def __init__(self, base_url: str | None = None, pause_seconds: float = 0.5) -> None:
        url = base_url or os.environ.get("HERMES_KRAKEN_API_BASE") or "https://api.kraken.com"
        self.base_url = str(url).rstrip("/")
        self.pause_seconds = float(pause_seconds)

    def fetch(self, pair: str, *, interval: int = 60, pages: int = 12) -> list[dict[str, Any]]:
        """Page backwards; each response holds up to 720 candles plus `last`."""
        token = str(pair).strip().upper()
        if not token:
            raise ValueError("pair must be non-empty")
        rows: list[dict[str, Any]] = []
        since: int | None = None
        page = 0
        while page < int(pages):
            url = "%s/0/public/OHLC?pair=%s&interval=%d" % (self.base_url, token, interval)
            if since is not None:
                url = url + "&since=%d" % since
            payload = http_get_json(url)
            if not isinstance(payload, dict) or payload.get("error"):
                raise AcquisitionError("kraken error for %s" % token)
            result = payload.get("result", {})
            names: list[str] = []
            for key in result:
                if key != "last":
                    names.append(key)
            if len(names) == 0:
                break
            candles = result[names[0]]
            if len(candles) == 0:
                break
            for item in candles:
                rows.append(normalize_kraken_row(item, names[0], self.venue))
            since = int(result.get("last", 0))
            if since <= 0 or len(candles) < 720:
                if page > 0 or len(candles) < 720:
                    break
            page = page + 1
            time.sleep(self.pause_seconds)
        return rows


def normalize_funding_row(item: Mapping[str, Any], venue: str) -> dict[str, Any]:
    """Validate one funding row into canonical shape; raises on garbage."""
    try:
        symbol = str(item["symbol"]).strip().upper()
        stamp = int(item["fundingTime"])
        rate = float(item["fundingRate"])
        mark = float(item.get("markPrice", 0.0) or 0.0)
    except (KeyError, TypeError, ValueError) as exc:
        raise AcquisitionError("malformed funding row") from exc
    if not symbol or stamp <= 0:
        raise AcquisitionError("malformed funding row")
    if abs(rate) > 0.05:
        raise AcquisitionError("impossible funding rate %r for %s" % (rate, symbol))
    return {
        "symbol": symbol,
        "funding_time_ms": stamp,
        "rate": rate,
        "mark_price": mark,
        "venue": str(venue),
    }


def normalize_kline_row(item: Any, symbol: str, interval: str, venue: str) -> dict[str, Any]:
    if not isinstance(item, (list, tuple)) or len(item) < 6:
        raise AcquisitionError("malformed kline row")
    try:
        stamp = int(item[0])
        close = float(item[4])
        volume = float(item[5])
    except (TypeError, ValueError) as exc:
        raise AcquisitionError("malformed kline row") from exc
    if stamp <= 0 or close <= 0 or volume < 0:
        raise AcquisitionError("impossible kline values")
    return {
        "symbol": str(symbol).strip().upper(),
        "interval": str(interval),
        "open_time_ms": stamp,
        "close": close,
        "volume": volume,
        "venue": str(venue),
    }


def normalize_coinbase_row(item: Any, product: str, venue: str) -> dict[str, Any]:
    # [time, low, high, open, close, volume], seconds UTC.
    if not isinstance(item, (list, tuple)) or len(item) < 6:
        raise AcquisitionError("malformed coinbase candle")
    try:
        stamp = int(item[0]) * 1000
        close = float(item[4])
        volume = float(item[5])
    except (TypeError, ValueError) as exc:
        raise AcquisitionError("malformed coinbase candle") from exc
    if stamp <= 0 or close <= 0 or volume < 0:
        raise AcquisitionError("impossible coinbase values")
    return {
        "symbol": str(product).strip().upper(),
        "interval": "1h",
        "open_time_ms": stamp,
        "close": close,
        "volume": volume,
        "venue": str(venue),
    }


def normalize_kraken_row(item: Any, pair: str, venue: str) -> dict[str, Any]:
    # [time, open, high, low, close, vwap, volume, count].
    if not isinstance(item, (list, tuple)) or len(item) < 7:
        raise AcquisitionError("malformed kraken candle")
    try:
        stamp = int(item[0]) * 1000
        close = float(item[4])
        volume = float(item[6])
    except (TypeError, ValueError) as exc:
        raise AcquisitionError("malformed kraken candle") from exc
    if stamp <= 0 or close <= 0 or volume < 0:
        raise AcquisitionError("impossible kraken values")
    return {
        "symbol": str(pair).strip().upper(),
        "interval": "1h",
        "open_time_ms": stamp,
        "close": close,
        "volume": volume,
        "venue": str(venue),
    }


# -- validation --
def validate_series(
    rows: list[dict[str, Any]], time_key: str, *, expected_step_ms: int | None = None
) -> dict[str, Any]:
    """Ordering, duplicates, gaps, monotonic coverage for one time series."""
    report: dict[str, Any] = {}
    report["n"] = len(rows)
    if len(rows) == 0:
        report["ok"] = False
        report["reasons"] = ["empty series"]
        return report
    ordered_ok = True
    seen: dict[int, int] = {}
    stamps: list[int] = []
    for row in rows:
        stamp = int(row[time_key])
        if stamp in seen:
            seen[stamp] = seen[stamp] + 1
        else:
            seen[stamp] = 1
            stamps.append(stamp)
    ordered_stamps: list[int] = []
    for stamp in stamps:
        placed = False
        index = 0
        while index < len(ordered_stamps):
            if stamp < ordered_stamps[index]:
                ordered_stamps.insert(index, stamp)
                placed = True
                break
            index = index + 1
        if placed is False:
            ordered_stamps.append(stamp)
    index = 1
    gaps = 0
    missing = 0
    while index < len(ordered_stamps):
        if ordered_stamps[index] <= ordered_stamps[index - 1]:
            ordered_ok = False
        if expected_step_ms is not None:
            steps = round((ordered_stamps[index] - ordered_stamps[index - 1]) / expected_step_ms)
            if steps > 1:
                gaps = gaps + 1
                missing = missing + (steps - 1)
        index = index + 1
    duplicates = 0
    for stamp in seen:
        if seen[stamp] > 1:
            duplicates = duplicates + (seen[stamp] - 1)
    report["ordered"] = ordered_ok
    report["duplicates"] = duplicates
    report["gaps"] = gaps
    report["missing_intervals"] = missing
    report["expected_intervals"] = None
    if expected_step_ms is not None and len(ordered_stamps) >= 2:
        span = ordered_stamps[-1] - ordered_stamps[0]
        report["expected_intervals"] = int(round(span / expected_step_ms)) + 1
    report["first_ms"] = ordered_stamps[0]
    report["last_ms"] = ordered_stamps[-1]
    report["span_days"] = (ordered_stamps[-1] - ordered_stamps[0]) / 86400000.0
    reasons: list[str] = []
    if ordered_ok is False:
        reasons.append("timestamps out of order")
    if duplicates > 0:
        reasons.append("%d duplicate records" % duplicates)
    report["ok"] = len(reasons) == 0
    report["reasons"] = reasons
    return report


def check_sync(
    left_ms: int, right_ms: int, *, tolerance_ms: int
) -> dict[str, Any]:
    """Absolute venue-timestamp difference against tolerance; no filling."""
    difference = abs(int(left_ms) - int(right_ms))
    return {
        "difference_ms": difference,
        "tolerance_ms": int(tolerance_ms),
        "synchronized": difference <= int(tolerance_ms),
    }


def regime_legs_from_closes(closes: list[float]) -> list[str]:
    """Pre-declared chronological legs labeled by realized direction.

    Splits the span into thirds; a leg is UP/DOWN when |return| >= 5%, else
    RANGE. Declared before any strategy result is inspected, so legs cannot
    be tuned to flatter outcomes — they only size the sufficiency check.
    """
    if len(closes) < 3:
        return []
    third = len(closes) // 3
    legs: list[str] = []
    index = 0
    while index < 3:
        start = index * third
        end = (index + 1) * third if index < 2 else len(closes)
        first = closes[start]
        last = closes[end - 1]
        if first <= 0:
            legs.append("RANGE")
        else:
            ret = (last - first) / first
            if ret >= 0.05:
                legs.append("UP")
            elif ret <= -0.05:
                legs.append("DOWN")
            else:
                legs.append("RANGE")
        index = index + 1
    distinct: list[str] = []
    for leg in legs:
        if leg not in distinct:
            distinct.append(leg)
    return distinct


def assert_evidence_grade(dataset: Mapping[str, Any]) -> None:
    """Refuse test fixtures and synthetic markers in the research runner."""
    provider = str(dataset.get("provider", "")).strip().lower()
    if provider in ("fixture", "synthetic", "mock", "test"):
        raise ValueError("test fixture dataset rejected by the research runner")
    dataset_id = str(dataset.get("dataset_id", ""))
    lowered = dataset_id.lower()
    for marker in ("fixture", "synthetic", "mock", "test-"):
        if marker in lowered:
            raise ValueError("test fixture dataset rejected by the research runner")


# -- immutable store --
def content_hash(rows: list[dict[str, Any]]) -> str:
    """SHA-256 over canonical JSON; any row change alters the hash."""
    import hashlib as _hashlib

    canonical: list[str] = []
    for row in rows:
        items: list[str] = []
        keys: list[str] = []
        for key in row:
            keys.append(key)
        ordered_keys: list[str] = []
        for key in keys:
            placed = False
            index = 0
            while index < len(ordered_keys):
                if key < ordered_keys[index]:
                    ordered_keys.insert(index, key)
                    placed = True
                    break
                index = index + 1
            if placed is False:
                ordered_keys.append(key)
        for key in ordered_keys:
            items.append(json.dumps(key) + ":" + json.dumps(row[key], sort_keys=True))
        canonical.append("{" + ",".join(items) + "}")
    ordered_rows: list[str] = []
    for line in canonical:
        placed = False
        index = 0
        while index < len(ordered_rows):
            if line < ordered_rows[index]:
                ordered_rows.insert(index, line)
                placed = True
                break
            index = index + 1
        if placed is False:
            ordered_rows.append(line)
    return _hashlib.sha256("\n".join(ordered_rows).encode("utf-8")).hexdigest()


def store_dataset(
    base_dir: str,
    *,
    dataset_id: str,
    provider: str,
    venue: str,
    symbol: str,
    rows: list[dict[str, Any]],
    start_ms: int,
    end_ms: int,
    schema_version: int = SCHEMA_VERSION,
) -> dict[str, Any]:
    """Write one immutable version; existing versions are never overwritten."""
    root = Path(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    digest = content_hash(rows)
    version = 1
    while (root / ("%s-v%d.json" % (dataset_id, version))).exists():
        existing = json.loads((root / ("%s-v%d.json" % (dataset_id, version))).read_text(encoding="utf-8"))
        if existing.get("manifest", {}).get("content_hash") == digest:
            return existing["manifest"]
        version = version + 1
    manifest: dict[str, Any] = {}
    manifest["dataset_id"] = dataset_id
    manifest["version"] = version
    manifest["provider"] = provider
    manifest["venue"] = venue
    manifest["symbol"] = symbol
    manifest["start_ms"] = int(start_ms)
    manifest["end_ms"] = int(end_ms)
    manifest["record_count"] = len(rows)
    manifest["retrieval_timestamp"] = datetime.now(timezone.utc).isoformat()
    manifest["content_hash"] = digest
    manifest["schema_version"] = int(schema_version)
    payload: dict[str, Any] = {}
    payload["manifest"] = manifest
    payload["rows"] = rows
    (root / ("%s-v%d.json" % (dataset_id, version))).write_text(
        json.dumps(payload, separators=(",", ":"), sort_keys=True), encoding="utf-8"
    )
    return manifest


def load_dataset(base_dir: str, dataset_id: str, version: int) -> dict[str, Any]:
    """Load one immutable version and verify its hash before returning."""
    path = Path(base_dir) / ("%s-v%d.json" % (dataset_id, version))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert_evidence_grade(payload.get("manifest", {}))
    if content_hash(payload["rows"]) != payload["manifest"]["content_hash"]:
        raise ValueError("dataset %s v%d hash mismatch: artifact changed" % (dataset_id, version))
    return payload
