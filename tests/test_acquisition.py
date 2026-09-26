"""Acquisition + validation level: providers, store, sync, reproducibility."""

from __future__ import annotations

import pytest

from research import acquisition as acq
from research import dislocation as dis
from research import funding_carry as fund


# -- funding normalization --
def test_funding_normalization_and_rejection():
    row = acq.normalize_funding_row(
        {"symbol": "btcusdt", "fundingTime": 1000, "fundingRate": "0.0001", "markPrice": "100.0"},
        "binance-futures",
    )
    assert row["symbol"] == "BTCUSDT"
    assert row["rate"] == pytest.approx(0.0001)
    with pytest.raises(acq.AcquisitionError):
        acq.normalize_funding_row({"symbol": "BTCUSDT"}, "v")
    with pytest.raises(acq.AcquisitionError, match="impossible"):
        acq.normalize_funding_row(
            {"symbol": "BTCUSDT", "fundingTime": 1, "fundingRate": "0.5", "markPrice": "1.0"}, "v"
        )


def test_kline_and_venue_normalization():
    row = acq.normalize_kline_row([1000, "1", "2", "0.5", "1.5", "10"], "BTCUSDT", "1h", "v")
    assert row["close"] == pytest.approx(1.5)
    with pytest.raises(acq.AcquisitionError):
        acq.normalize_kline_row([1000, "1"], "BTCUSDT", "1h", "v")
    coinbase = acq.normalize_coinbase_row([1000, "1", "2", "1", "1.5", "10"], "BTC-USD", "v")
    assert coinbase["open_time_ms"] == 1000000
    kraken = acq.normalize_kraken_row([1000, "1", "2", "0.5", "1.5", "1.4", "10", 5], "XBTUSD", "v")
    assert kraken["close"] == pytest.approx(1.5)
    with pytest.raises(acq.AcquisitionError):
        acq.normalize_kraken_row([1000, "1"], "XBTUSD", "v")


def test_funding_pagination_without_network(monkeypatch):
    calls: list[str] = []

    def page_of(count, start):
        page: list[dict] = []
        index = 0
        while index < count:
            page.append({"symbol": "BTCUSDT", "fundingTime": start - index,
                         "fundingRate": "0.0001", "markPrice": "100"})
            index = index + 1
        return page

    def fake_get(url, timeout_seconds=30):
        calls.append(url)
        if "endTime" not in url:
            return page_of(1000, 1_000_000_000)
        return page_of(200, 999_000_000)

    monkeypatch.setattr("research.acquisition.http_get_json", fake_get)
    provider = acq.FundingHistoryProvider(pause_seconds=0.0)
    rows = provider.fetch("BTCUSDT", limit=1200)
    assert len(rows) == 1200
    assert len(calls) == 2
    assert rows[0]["funding_time_ms"] == 1_000_000_000


# -- timestamp validation, duplicates, missing intervals --
def test_validate_series_ordering_duplicates_gaps():
    base = 1_000_000
    rows: list[dict] = []
    index = 0
    while index < 10:
        if index != 5:
            rows.append({"t": base + index * 28_800_000})
        index = index + 1
    report = acq.validate_series(rows, "t", expected_step_ms=28_800_000)
    assert report["ok"] is True
    assert report["gaps"] == 1
    assert report["missing_intervals"] == 1
    assert report["expected_intervals"] == 10
    assert report["span_days"] == pytest.approx(9 * 28_800_000 / 86400000.0)
    doubled = rows + [{"t": base}]
    assert acq.validate_series(doubled, "t")["duplicates"] == 1
    assert acq.validate_series([], "t")["ok"] is False


# -- hashing + immutable store --
def test_store_is_immutable_and_hash_verified(tmp_path):
    rows = [{"symbol": "BTCUSDT", "funding_time_ms": 1, "rate": 0.0001}]
    first = acq.store_dataset(
        str(tmp_path), dataset_id="fund-btc", provider="binance-fapi-funding",
        venue="binance-futures", symbol="BTCUSDT", rows=rows,
        start_ms=1, end_ms=2,
    )
    assert first["version"] == 1
    assert first["record_count"] == 1
    same = acq.store_dataset(
        str(tmp_path), dataset_id="fund-btc", provider="binance-fapi-funding",
        venue="binance-futures", symbol="BTCUSDT", rows=rows,
        start_ms=1, end_ms=2,
    )
    assert same["version"] == 1
    changed_rows = [{"symbol": "BTCUSDT", "funding_time_ms": 1, "rate": 0.0002}]
    second = acq.store_dataset(
        str(tmp_path), dataset_id="fund-btc", provider="binance-fapi-funding",
        venue="binance-futures", symbol="BTCUSDT", rows=changed_rows,
        start_ms=1, end_ms=2,
    )
    assert second["version"] == 2
    assert second["content_hash"] != first["content_hash"]
    loaded = acq.load_dataset(str(tmp_path), "fund-btc", 1)
    assert loaded["rows"] == rows


def test_tampered_artifact_fails_load(tmp_path):
    import json as _json

    rows = [{"symbol": "BTCUSDT", "funding_time_ms": 1, "rate": 0.0001}]
    acq.store_dataset(
        str(tmp_path), dataset_id="fund-btc", provider="p", venue="v", symbol="BTCUSDT",
        rows=rows, start_ms=1, end_ms=2,
    )
    path = tmp_path / "fund-btc-v1.json"
    payload = _json.loads(path.read_text(encoding="utf-8"))
    payload["rows"].append({"symbol": "BTCUSDT", "funding_time_ms": 2, "rate": 0.9})
    path.write_text(_json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        acq.load_dataset(str(tmp_path), "fund-btc", 1)


# -- sufficiency branches on deterministic fixtures --
def test_funding_sufficiency_fail_and_success():
    thin: list[fund.FundingObservation] = []
    index = 0
    while index < 30:
        thin.append(fund.FundingObservation("BTCUSDT", 1_000_000 + index * 28_800_000, 0.0002, 100.0))
        index = index + 1
    assert fund.evaluate_sufficiency(thin, ["leg"])["verdict"] == "INCONCLUSIVE"
    wide: list[fund.FundingObservation] = []
    index = 0
    while index < 210:
        wide.append(fund.FundingObservation(
            "BTCUSDT", 1_000_000 + index * 28_800_000, 0.0002, 100.0 + index * 0.5))
        index = index + 1
    verdict = fund.evaluate_sufficiency(wide, ["up-leg", "down-leg"])
    assert verdict["verdict"] == "READY"


# -- cross-exchange sync, quotes, executability --
def test_sync_tolerance():
    assert acq.check_sync(1000, 1200, tolerance_ms=500)["synchronized"] is True
    assert acq.check_sync(1000, 2000, tolerance_ms=500)["synchronized"] is False


def quoted(symbol="BTCUSDT", stamp=1000, executable=True):
    if executable:
        return dis.DislocationObservation(
            symbol, stamp, 85000.0, 8.0, 4, "CONFIRMED",
            venue_a="binance", bid_a=84990.0, ask_a=85000.0, depth_a=2.0,
            venue_b="coinbase", bid_b=85070.0, ask_b=85080.0, depth_b=2.0,
        )
    return dis.DislocationObservation(symbol, stamp, 85000.0, 8.0, 4, "CONFIRMED")


def test_executability_paths():
    bare: list[dis.DislocationObservation] = []
    index = 0
    while index < 5:
        bare.append(quoted(stamp=1000 + index, executable=False))
        index = index + 1
    verdict = dis.check_executability(bare)
    assert verdict["executable"] is False
    assert len(verdict["missing"]) == 6
    crossed: list[dis.DislocationObservation] = []
    index = 0
    while index < 5:
        obs = quoted(stamp=1000 + index)
        crossed.append(dis.DislocationObservation(
            obs.symbol, obs.timestamp_ms, obs.reference_price, obs.disagreement_bps,
            obs.source_count, obs.status,
            venue_a="binance", bid_a=85000.0, ask_a=84990.0, depth_a=2.0,
            venue_b="coinbase", bid_b=85070.0, ask_b=85080.0, depth_b=2.0,
        ))
        index = index + 1
    assert dis.check_executability(crossed)["executable"] is False
    thin_depth: list[dis.DislocationObservation] = []
    index = 0
    while index < 5:
        obs = quoted(stamp=1000 + index)
        thin_depth.append(dis.DislocationObservation(
            obs.symbol, obs.timestamp_ms, obs.reference_price, obs.disagreement_bps,
            obs.source_count, obs.status,
            venue_a="binance", bid_a=84990.0, ask_a=85000.0, depth_a=0.00001,
            venue_b="coinbase", bid_b=85070.0, ask_b=85080.0, depth_b=0.00001,
        ))
        index = index + 1
    assert dis.check_executability(thin_depth)["executable"] is False


def test_dislocation_sufficiency_success_fixture():
    observations: list[dis.DislocationObservation] = []
    index = 0
    while index < 1500:
        observations.append(quoted(stamp=1_000_000 + index * 3_600_000))
        index = index + 1
    verdict = dis.evaluate_sufficiency(observations, ["leg-a", "leg-b"])
    assert verdict["verdict"] == "READY"
    assert verdict["hypotheses_tested"] == 0
    verdict2 = dis.evaluate_sufficiency(observations[:10], ["leg-a"])
    assert verdict2["verdict"] == "INCONCLUSIVE"


# -- security: env config, redacted errors, fixture rejection --
def test_provider_base_url_from_environment(monkeypatch):
    monkeypatch.setenv("HERMES_FUNDING_API_BASE", "https://mirror.local/fapi")
    provider = acq.FundingHistoryProvider()
    assert provider.base_url == "https://mirror.local/fapi"
    monkeypatch.delenv("HERMES_FUNDING_API_BASE")
    assert acq.FundingHistoryProvider().base_url == "https://fapi.binance.com"


def test_transport_errors_hide_query_strings(monkeypatch):
    def boom(url, timeout_seconds=30):
        raise RuntimeError("unreachable")

    monkeypatch.setattr("research.acquisition.urllib.request.urlopen", boom)
    with pytest.raises(acq.AcquisitionError) as exc_info:
        acq.http_get_json("https://example.local/x?api_key=S3CR3T")
    assert "example.local" in str(exc_info.value)
    assert "S3CR3T" not in str(exc_info.value)


def test_fixture_datasets_rejected():
    with pytest.raises(ValueError, match="fixture"):
        acq.assert_evidence_grade({"provider": "fixture", "dataset_id": "real-data"})
    with pytest.raises(ValueError, match="fixture"):
        acq.assert_evidence_grade({"provider": "binance", "dataset_id": "test-fixture-x"})
    acq.assert_evidence_grade({"provider": "binance-fapi-funding", "dataset_id": "fund-btcusdt-v1"})


def test_no_secrets_logged_or_committed():
    import pathlib as _pathlib

    root = _pathlib.Path(__file__).resolve().parent.parent / "research" / "acquisition.py"
    text = root.read_text(encoding="utf-8")
    assert "print(" not in text
    assert "logging" not in text
