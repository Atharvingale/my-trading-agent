"""Pre-cost screen for oi_positioning_001 (research window only).

Why this file exists: Step 3 go/no-go on the frozen spec. Computes trade
count, mean GROSS return per trade, and the date-cluster bootstrap CI of
the gross mean on 2021-01-01..2025-05-31 only. Compares against the
per-round-trip fixed cost 0.0140. Below it (or CI upper below it) closes
as CLOSED_PRECOST_SCREEN with no ledger row and no holdout consumption.
No parameter is tuned here; any change would be a new hypothesis.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import research.oi_positioning as engine
import research.oi_cluster_bootstrap as cluster


DATA_ROOT = Path("data/oi_stage_a")
FIXED_COST = 0.001 * 2.0 + 0.001 * 2.0 + 0.01
RESEARCH_FIRST = "2021-01-01"
RESEARCH_LAST_SIGNAL = "2025-05-25"
RESEARCH_LAST_EXIT = "2025-05-31"


def _read_metrics_daily(symbol: str, day: str) -> float | None:
    """Last 5-minute row value for one metrics day, or None if absent."""
    target = DATA_ROOT / ("metrics/%s/%s-metrics-%s.zip" % (symbol, symbol, day))
    if target.is_file() is False:
        return None
    try:
        with zipfile.ZipFile(target, "r") as archive:
            names = archive.namelist()
            if len(names) == 0:
                return None
            raw = archive.read(names[0]).decode("utf-8")
    except Exception:
        return None
    lines = raw.strip().split("\n")
    if len(lines) < 2:
        return None
    header = lines[0].strip().split(",")
    field_index = -1
    index = 0
    while index < len(header):
        if header[index].strip() == engine.SIGNAL_FIELD:
            field_index = index
        index = index + 1
    if field_index < 0:
        return None
    last = lines[len(lines) - 1].strip().split(",")
    try:
        return float(last[field_index])
    except Exception:
        return None


def _load_spot_opens(universe: list) -> dict:
    """Spot daily OPEN by symbol/day from monthly 1d zips (research span)."""
    opens: dict = {}
    for symbol in universe:
        opens[symbol] = {}
    pattern = list((DATA_ROOT / "spot_monthly").glob("*/*.zip"))
    for path in pattern:
        try:
            with zipfile.ZipFile(path, "r") as archive:
                names = archive.namelist()
                if len(names) == 0:
                    continue
                raw = archive.read(names[0]).decode("utf-8")
        except Exception:
            continue
        symbol = path.parent.name
        if symbol not in opens:
            continue
        for line in raw.strip().split("\n"):
            if line.strip() == "":
                continue
            cols = line.strip().split(",")
            if len(cols) < 6:
                continue
            try:
                open_time_us = int(float(cols[0]))
                open_time_ms = int(open_time_us / 1000)
                import datetime as _dt

                day = _dt.datetime.fromtimestamp(open_time_ms / 1000.0, tz=_dt.timezone.utc).date().isoformat()
                if day < "2021-01-01" or day > RESEARCH_LAST_EXIT:
                    continue
                price = float(cols[1])
                if price > 0:
                    opens[symbol][day] = price
            except Exception:
                continue
    return opens


def run(universe: list, out_path: str = "research/reports/oi_positioning_001_screen.json") -> dict:
    """Execute the research-only screen; writes the JSON record."""
    import datetime as _dt

    metrics_by_symbol: dict = {}
    for symbol in universe:
        metrics_by_symbol[symbol] = {}
    cur = _dt.date(2020, 10, 3)
    end = _dt.date(2025, 5, 31)
    while cur <= end:
        day = cur.isoformat()
        for symbol in universe:
            value = _read_metrics_daily(symbol, day)
            if value is not None:
                metrics_by_symbol[symbol][day] = value
        cur = cur + _dt.timedelta(days=1)
    opens = _load_spot_opens(universe)
    # Validation: duplicates impossible by dict; gaps are missing (never filled).
    # Lifecycle: pre-first dates absent are boundaries, interior missing stays missing.
    trades = engine.generate_trades(
        metrics_by_symbol,
        opens,
        list(universe),
        RESEARCH_FIRST,
        RESEARCH_LAST_SIGNAL,
        notional=1000.0,
        stressed=False,
    )
    trade_count = len(trades)
    gross_fracs: list = []
    for trade in trades:
        gross_fracs.append(float(trade["gross_pnl"]) / 1000.0)
    by_date = cluster.cluster_by_entry_date(trades)
    # Gross clustering needs gross fractions per date; rebuild from trades.
    gross_by_date: dict = {}
    for trade in trades:
        day = str(trade["entry_day"])
        frac = float(trade["gross_pnl"]) / 1000.0
        if day not in gross_by_date:
            gross_by_date[day] = []
        gross_by_date[day].append(frac)
    gross_means: list = []
    for day in gross_by_date:
        vals = gross_by_date[day]
        total = 0.0
        for value in vals:
            total = total + float(value)
        gross_means.append(total / float(len(vals)))
    if len(gross_fracs) == 0:
        mean_gross = 0.0
        ci = (0.0, 0.0)
    else:
        total_gross = 0.0
        for value in gross_fracs:
            total_gross = total_gross + float(value)
        mean_gross = total_gross / float(len(gross_fracs))
        ci = cluster.bootstrap_ci(gross_means, seed=20260928, samples=10000)
    entry_dates = len(by_date)
    decision = "GO"
    if trade_count == 0 or mean_gross < FIXED_COST or ci[1] < FIXED_COST:
        decision = "CLOSED_PRECOST_SCREEN"
    record = {
        "hypothesis_id": engine.HYPOTHESIS_ID,
        "window": ["2021-01-01", "2025-05-31"],
        "universe_size": len(universe),
        "trade_count": trade_count,
        "entry_date_count": entry_dates,
        "mean_gross_per_trade": mean_gross,
        "gross_cluster_ci": [ci[0], ci[1]],
        "round_trip_fixed_cost": FIXED_COST,
        "decision": decision,
        "bootstrap_seed": 20260928,
        "bootstrap_samples": 10000,
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    return record
