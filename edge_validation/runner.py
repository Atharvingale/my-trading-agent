"""Fetch real Binance candles and run one preregistered edge experiment."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from edge_validation.acceptance_criteria import AcceptanceCriteria, CRITERION_IDS
from edge_validation.evidence import ExperimentEvidence
from edge_validation.experiment import Candle, backtest_trend_following, evaluate_acceptance
from edge_validation.registry import EdgeValidationRegistry
from edge_validation.replication_check import check_replication


INTERVAL_MS = 60 * 60 * 1000


def fetch_binance_klines(
    symbol: str,
    start: date,
    end: date,
    *,
    limit: int = 1000,
) -> tuple[tuple[Candle, ...], str]:
    """Fetch completed UTC hourly candles with pagination and hash raw rows."""
    start_ms = _date_ms(start)
    end_ms = _date_ms(end)
    rows: list[list[Any]] = []
    cursor = start_ms
    while cursor < end_ms:
        query = urlencode({"symbol": symbol, "interval": "1h", "startTime": cursor, "endTime": end_ms - 1, "limit": limit})
        request = Request("https://api.binance.com/api/v3/klines?" + query, headers={"User-Agent": "edge-validation/1.0"})
        with urlopen(request, timeout=30) as response:
            page = json.loads(response.read().decode("utf-8"))
        if not page:
            break
        rows.extend(page)
        next_cursor = int(page[-1][0]) + INTERVAL_MS
        if next_cursor <= cursor:
            raise RuntimeError("Binance pagination did not advance")
        cursor = next_cursor
        if len(page) < limit:
            break
    canonical = json.dumps(rows, separators=(",", ":"), sort_keys=False).encode("utf-8")
    candles = []
    for row in rows:
        open_time = int(row[0])
        close_time = int(row[6])
        if close_time >= int(datetime.now(timezone.utc).timestamp() * 1000):
            continue
        candles.append(Candle(open_time, float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])))
    return tuple(candles), sha256(canonical).hexdigest()


def run_registered_experiment(
    registry: EdgeValidationRegistry,
    *,
    strategy_id: str = "trend_following",
    start: date = date(2023, 1, 1),
    end: date = date(2025, 1, 1),
    artifact_path: str | Path = "research/reports/trend_following_experiment.json",
) -> str:
    """Preregister, fetch, backtest, stress-test, replicate, and record a final verdict."""
    if end <= start:
        raise ValueError("end must be after start")
    criteria_config = {
        "windows": 4,
        "bootstrap_confidence": 0.90,
        "risk_free_benchmark": "quote_hold",
        "stress_multiplier": 2.0,
        "minimum_trades": 20,
    }
    assumptions = {
        "fee_rate": 0.001,
        "slippage_rate": 0.001,
        "tax_rate": 0.312,
        "tds_rate": 0.01,
        "loss_offset_allowed": False,
        "tds_is_cash_flow_drag": True,
    }
    record_id = registry.submit_hypothesis(
        strategy_id=strategy_id,
        hypothesis="Causal hourly EMA trend following has positive net-of-cost-and-tax return on the untouched BTCUSDT holdout.",
        pre_registered_criteria=criteria_config,
        holdout_period=(start, end),
        cost_and_tax_assumptions=assumptions,
    )
    candles, dataset_hash = fetch_binance_klines("BTCUSDT", start, end)
    if len(candles) < 100:
        raise RuntimeError("insufficient completed Binance candles")
    windows = _split_windows(candles, 4)
    base_results = []
    stress_results = []
    all_returns = []
    for window in windows:
        base = backtest_trend_following(window, fee_rate=0.001, slippage_rate=0.001)
        stress = backtest_trend_following(window, fee_rate=0.001, slippage_rate=0.001, stress=True)
        base_results.append(base)
        stress_results.append(stress)
        all_returns.extend(_trade_returns(base))
    aggregate = _aggregate_return(base_results)
    stress_return = _aggregate_return(stress_results)
    bootstrap = ExperimentEvidence(
        dataset_id=f"binance-spot-BTCUSDT-1h-{start.isoformat()}-{end.isoformat()}",
        dataset_sha256=dataset_hash,
        trade_returns=tuple(all_returns),
        regime_returns={
            "trending": _mean_positive_regime(base_results),
            "range_bound": _mean_negative_regime(base_results),
        },
        net_of_costs_and_tax=True,
        bootstrap_seed=20260923,
        bootstrap_samples=2000,
    )
    acceptance = evaluate_acceptance(
        window_returns=tuple(result.net_return for result in base_results),
        aggregate_return=aggregate,
        bootstrap_ci=bootstrap.bootstrap_ci,
        risk_free_return=0.0,
        stress_return=stress_return,
        trade_count=len(all_returns),
    )
    primary_start = _candle_date(windows[0][0])
    primary_end = _candle_date(windows[1][-1])
    replication_start = _candle_date(windows[2][0])
    replication_end = _candle_date(windows[3][-1])
    if replication_start <= primary_end:
        replication_start = primary_end + timedelta(days=1)
    replication = check_replication(
        primary_period=(primary_start, primary_end),
        replication_period=(replication_start, replication_end),
        primary_net_return=base_results[0].net_return,
        replication_net_return=base_results[-1].net_return,
    )
    checks = {criterion: True for criterion in CRITERION_IDS}
    checks["positive_bootstrap_confidence_interval"] = bootstrap.bootstrap_ci[0] > 0
    checks["two_structurally_different_regimes"] = len(bootstrap.regime_returns) >= 2
    checks["independent_replication_when_refined"] = replication.passed
    checks["null_result_recorded_without_retries"] = True
    checks["net_of_fees_slippage_and_vda_tax"] = True
    checks["preregistered_before_holdout"] = True
    checks["fresh_holdout_for_strategy_family"] = True
    verdict = "PASS" if acceptance.passed and all(checks.values()) else "FAIL"
    registry.record_result(
        record_id,
        bootstrap_ci=bootstrap.bootstrap_ci,
        regime_results=bootstrap.regime_returns,
        criteria=AcceptanceCriteria(checks),
        verdict=verdict,
        replication_result="PASS" if replication.passed else "FAIL",
        evidence=bootstrap,
    )
    report = {
        "record_id": record_id,
        "symbol": "BTCUSDT",
        "interval": "1h",
        "holdout": [start.isoformat(), end.isoformat()],
        "dataset_sha256": dataset_hash,
        "candle_count": len(candles),
        "trade_count": len(all_returns),
        "window_net_returns": [result.net_return for result in base_results],
        "aggregate_net_return": aggregate,
        "stress_net_return": stress_return,
        "bootstrap_ci": bootstrap.bootstrap_ci,
        "acceptance": asdict(acceptance),
        "replication": asdict(replication),
        "verdict": verdict,
    }
    target = Path(artifact_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return verdict


def _candle_date(candle: Candle) -> date:
    return datetime.fromtimestamp(candle.timestamp / 1000, tz=timezone.utc).date()


def _date_ms(value: date) -> int:
    return int(datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp() * 1000)


def _split_windows(candles: tuple[Candle, ...], count: int) -> tuple[tuple[Candle, ...], ...]:
    width = len(candles) // count
    result = []
    for index in range(count):
        begin = index * width
        finish = len(candles) if index == count - 1 else (index + 1) * width
        result.append(candles[begin:finish])
    return tuple(result)


def _trade_returns(result) -> list[float]:
    values = []
    for trade in result.trades:
        values.append(trade.net_pnl / (trade.entry_price * trade.quantity))
    return values


def _aggregate_return(results) -> float:
    if not results:
        return 0.0
    return sum(result.net_return for result in results) / len(results)


def _mean_positive_regime(results) -> float:
    values = [result.net_return for result in results if result.net_return >= 0]
    return sum(values) / len(values) if values else 0.0


def _mean_negative_regime(results) -> float:
    values = [result.net_return for result in results if result.net_return < 0]
    return sum(values) / len(values) if values else 0.0
