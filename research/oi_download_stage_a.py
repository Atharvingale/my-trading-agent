"""Stage A downloader: research+warm-up+embargo only (never holdout).

Why this file exists: fetches futures metrics daily zips (2020-10-03..
2025-08-31) and spot 1d monthly zips (2020-10..2025-08) for the frozen
60-symbol universe, resumable via checkpoint, checksummed every file,
bounded concurrency with backoff. Stage B (holdout) is a separate step
and must not run until the pre-cost screen passes.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


UNIVERSE = (
    "ETHUSDT", "BTCUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "SUIUSDT",
    "BNBUSDT", "TRXUSDT", "ADAUSDT", "ENAUSDT", "LINKUSDT", "PENGUUSDT",
    "UNIUSDT", "AVAXUSDT", "LTCUSDT", "WIFUSDT", "HBARUSDT", "TRUMPUSDT",
    "AAVEUSDT", "ARBUSDT", "SEIUSDT", "XLMUSDT", "WLDUSDT", "CRVUSDT",
    "NEIROUSDT", "BCHUSDT", "VIRTUALUSDT", "APTUSDT", "PNUTUSDT", "TAOUSDT",
    "NEARUSDT", "OPUSDT", "ETHFIUSDT", "DOTUSDT", "CFXUSDT", "LDOUSDT",
    "SYRUPUSDT", "BIOUSDT", "FETUSDT", "SUSDT", "ONDOUSDT", "BANANAS31USDT",
    "TIAUSDT", "PENDLEUSDT", "CAKEUSDT", "FILUSDT", "ETCUSDT", "INJUSDT",
    "EIGENUSDT", "HYPERUSDT", "HUMAUSDT", "POLUSDT", "PAXGUSDT", "RUNEUSDT",
    "ALGOUSDT", "GALAUSDT", "RENDERUSDT", "ENSUSDT", "AIXBTUSDT", "MEMEUSDT",
)

HOLDOUT_START_DAY = "2025-09-01"
DATA_ROOT = Path("data/oi_stage_a")
CHECKPOINT = DATA_ROOT / "checkpoint.json"
WORKERS = 8


def _day_list() -> list:
    """All calendar days 2020-10-03..2025-08-31 (Stage A only)."""
    import datetime as _dt

    days: list = []
    cur = _dt.date(2020, 10, 3)
    end = _dt.date(2025, 8, 31)
    while cur <= end:
        token = cur.isoformat()
        if token >= HOLDOUT_START_DAY:
            raise ValueError("stage A guard: day reaches holdout")
        days.append(token)
        cur = cur + _dt.timedelta(days=1)
    return days


def _month_list() -> list:
    """All months 2020-10..2025-08 for spot monthly 1d."""
    months: list = []
    year = 2020
    month = 10
    while True:
        if year > 2025 or (year == 2025 and month > 8):
            break
        months.append("%04d-%02d" % (year, month))
        month = month + 1
        if month > 12:
            month = 1
            year = year + 1
    return months


def _all_jobs() -> list:
    """Full Stage A job list (metrics daily + spot monthly)."""
    jobs: list = []
    for symbol in UNIVERSE:
        for day in _day_list():
            url = "https://data.binance.vision/data/futures/um/daily/metrics/%s/%s-metrics-%s.zip" % (symbol, symbol, day)
            rel = "metrics/%s/%s-metrics-%s.zip" % (symbol, symbol, day)
            jobs.append(("metrics", url, rel))
    for symbol in UNIVERSE:
        for month in _month_list():
            url = "https://data.binance.vision/data/spot/monthly/klines/%s/1d/%s-1d-%s.zip" % (symbol, symbol, month)
            rel = "spot_monthly/%s/%s-1d-%s.zip" % (symbol, symbol, month)
            jobs.append(("spot", url, rel))
    return jobs


def _fetch_one(job: tuple) -> dict:
    """Download one file + CHECKSUM sidecar, verify, store. Returns report."""
    import urllib.error as _urlerror

    kind, url, rel = job
    target = DATA_ROOT / rel
    if target.is_file() and target.stat().st_size > 0:
        return {"rel": rel, "status": "cached"}
    target.parent.mkdir(parents=True, exist_ok=True)
    attempts = 0
    while attempts < 5:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "oi-stage-a/1.0"})
            with urllib.request.urlopen(req, timeout=60) as response:
                body = response.read()
            checksum_url = url + ".CHECKSUM"
            req_sum = urllib.request.Request(checksum_url, headers={"User-Agent": "oi-stage-a/1.0"})
            with urllib.request.urlopen(req_sum, timeout=60) as response_sum:
                sidecar = response_sum.read().decode("utf-8").strip()
            parts = sidecar.split()
            expected = parts[0].strip().lower()
            actual = hashlib.sha256(body).hexdigest()
            if actual != expected:
                return {"rel": rel, "status": "checksum_mismatch"}
            target.write_bytes(body)
            return {"rel": rel, "status": "ok", "bytes": len(body)}
        except _urlerror.HTTPError as exc:
            if int(exc.code) == 404:
                return {"rel": rel, "status": "absent"}
            message = repr(exc)
            if "429" in message or "500" in message or "503" in message:
                time.sleep(2.0 + attempts * 2.0)
            else:
                time.sleep(1.0)
            attempts = attempts + 1
        except Exception as exc:
            message = repr(exc)
            if "429" in message or "500" in message or "503" in message:
                time.sleep(2.0 + attempts * 2.0)
            else:
                time.sleep(1.0)
            attempts = attempts + 1
    return {"rel": rel, "status": "failed"}


def run_batch(limit: int = 2000, workers: int = WORKERS) -> dict:
    """Download next `limit` pending jobs; updates checkpoint; returns stats."""
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    done: dict = {}
    if CHECKPOINT.is_file():
        try:
            done = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        except Exception:
            done = {}
    jobs = _all_jobs()
    pending: list = []
    for job in jobs:
        if job[2] not in done:
            pending.append(job)
        if len(pending) >= limit:
            break
    stats = {"total_jobs": len(jobs), "done_before": len(done), "batch": len(pending), "ok": 0, "cached": 0, "failed": 0, "mismatch": 0, "absent": 0}
    if len(pending) == 0:
        stats["complete"] = True
        return stats
    with ThreadPoolExecutor(max_workers=int(workers)) as pool:
        results = pool.map(_fetch_one, pending)
        for job, result in zip(pending, results):
            status = str(result.get("status", "failed"))
            if status == "ok":
                stats["ok"] = stats["ok"] + 1
                done[job[2]] = {"status": "ok", "bytes": result.get("bytes", 0)}
            elif status == "cached":
                stats["cached"] = stats["cached"] + 1
                done[job[2]] = {"status": "cached"}
            elif status == "checksum_mismatch":
                stats["mismatch"] = stats["mismatch"] + 1
            elif status == "absent":
                stats["absent"] = stats["absent"] + 1
                done[job[2]] = {"status": "absent"}
            else:
                stats["failed"] = stats["failed"] + 1
    CHECKPOINT.write_text(json.dumps(done, indent=1), encoding="utf-8")
    stats["done_after"] = len(done)
    stats["complete"] = len(done) >= len(jobs)
    return stats
