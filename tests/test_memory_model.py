"""Module 10 acceptance: unified traceability plus append-only enforcement."""

from __future__ import annotations

import sqlite3

import pytest

from memory.repository import MemoryRepository, TraceNotFoundError
from memory.schemas import CHAIN_ORDER, TABLES


def make_repo(tmp_path):
    return MemoryRepository(tmp_path / "memory.sqlite3")


def build_chain(repo):
    # Why this order: each row carries its predecessor ID, so inserts must
    # follow the spec chain from market snapshot down to strategy version.
    repo.record_market_snapshot(
        snapshot_id="snap-001", symbol="BTCUSDT", event_time_ms=1700000000000, payload={"close": 100.0}
    )
    repo.record_edge_validation(
        record_id="edge-001",
        strategy_id="synthetic_carry_v1",
        strategy_family="carry",
        verdict="PASS",
        snapshot_id="snap-001",
        payload={"hypothesis": "synthetic"},
    )
    repo.record_decision(
        decision_id="dec-001",
        symbol="BTCUSDT",
        action="BUY",
        confidence=0.7,
        market_snapshot_id="snap-001",
        edge_validation_record_id="edge-001",
        payload={"thesis": ["synthetic"]},
    )
    repo.record_proposal(
        proposal_id="prop-001",
        decision_id="dec-001",
        strategy_id="synthetic_carry_v1",
        action="BUY",
        edge_validation_record_id="edge-001",
        payload={"confidence": 0.7},
    )
    repo.record_proposal(
        proposal_id="prop-002",
        decision_id="dec-001",
        strategy_id="synthetic_carry_v1",
        action="BUY",
        edge_validation_record_id="edge-001",
        payload={"confidence": 0.6},
    )
    repo.record_evidence(
        evidence_id="ev-001", decision_id="dec-001", proposal_id="prop-001", payload={"feature": "ema"}
    )
    repo.record_evidence(
        evidence_id="ev-002", decision_id="dec-001", proposal_id="prop-002", payload={"feature": "rsi"}
    )
    repo.record_risk(
        risk_decision_id="risk-001",
        decision_id="dec-001",
        status="APPROVED",
        approved_quantity=0.5,
        payload={"stop": 98.0},
    )
    repo.record_execution(
        execution_id="exec-001", risk_decision_id="risk-001", status="ACKED", payload={"venue": "n8n"}
    )
    repo.record_order(
        order_id="ord-001",
        execution_id="exec-001",
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.5,
        status="FILLED",
        payload={},
    )
    repo.record_position(
        position_id="pos-001", order_id="ord-001", symbol="BTCUSDT", quantity=0.5, payload={}
    )
    repo.record_trade(
        trade_id="trade-001", position_id="pos-001", symbol="BTCUSDT", pnl=12.5, payload={}
    )
    repo.record_analysis(
        analysis_id="ana-001", trade_id="trade-001", diagnosis="synthetic win", payload={}
    )
    repo.record_lesson(
        lesson_id="les-001", analysis_id="ana-001", status="CANDIDATE", payload={"note": "synthetic"}
    )
    repo.record_strategy_version(
        version_id="synthetic_carry_v1@edge-001",
        strategy_id="synthetic_carry_v1",
        edge_validation_record_id="edge-001",
        lesson_id="les-001",
        approver="atharva",
        payload={"version": 1},
    )
    return "trade-001"


def test_trace_returns_complete_correctly_ordered_chain(tmp_path):
    repo = make_repo(tmp_path)
    trade_id = build_chain(repo)
    result = repo.trace(trade_id)
    keys: list[str] = []
    for key in result:
        keys.append(key)
    expected: list[str] = []
    for key in CHAIN_ORDER:
        expected.append(key)
    assert keys == expected
    assert result["market_snapshot"]["snapshot_id"] == "snap-001"
    assert result["edge_validation_record"]["record_id"] == "edge-001"
    assert result["decision"]["decision_id"] == "dec-001"
    assert result["risk_decision"]["risk_decision_id"] == "risk-001"
    assert result["execution"]["execution_id"] == "exec-001"
    assert result["order"]["order_id"] == "ord-001"
    assert result["position"]["position_id"] == "pos-001"
    assert result["trade"]["trade_id"] == "trade-001"
    assert result["trade_analysis"]["analysis_id"] == "ana-001"
    assert result["lesson"]["lesson_id"] == "les-001"
    assert result["strategy_version"]["version_id"] == "synthetic_carry_v1@edge-001"
    # Linkage: every stage carries its predecessor ID (query-enforced).
    assert result["decision"]["market_snapshot_id"] == result["market_snapshot"]["snapshot_id"]
    assert result["decision"]["edge_validation_record_id"] == result["edge_validation_record"]["record_id"]
    assert result["risk_decision"]["decision_id"] == result["decision"]["decision_id"]
    assert result["execution"]["risk_decision_id"] == result["risk_decision"]["risk_decision_id"]
    assert result["order"]["execution_id"] == result["execution"]["execution_id"]
    assert result["position"]["order_id"] == result["order"]["order_id"]
    assert result["trade"]["position_id"] == result["position"]["position_id"]
    assert result["trade_analysis"]["trade_id"] == result["trade"]["trade_id"]
    assert result["lesson"]["analysis_id"] == result["trade_analysis"]["analysis_id"]
    assert result["strategy_version"]["lesson_id"] == result["lesson"]["lesson_id"]
    assert result["strategy_version"]["edge_validation_record_id"] == result["edge_validation_record"]["record_id"]
    # One-to-many legs return insertion-ordered lists.
    assert len(result["strategy_proposals"]) == 2
    assert result["strategy_proposals"][0]["proposal_id"] == "prop-001"
    assert result["strategy_proposals"][1]["proposal_id"] == "prop-002"
    assert len(result["decision_evidence"]) == 2
    repo.close()


def test_all_spec_tables_exist(tmp_path):
    repo = make_repo(tmp_path)
    names = repo.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    found: list[str] = []
    for row in names:
        found.append(str(row[0]))
    for table in TABLES:
        assert table in found
    repo.close()


def test_supporting_tables_roundtrip(tmp_path):
    repo = make_repo(tmp_path)
    repo.record_raw_event(
        event_id="evt-001",
        symbol="BTCUSDT",
        stream="bookTicker",
        event_type="tick",
        event_time_ms=1,
        received_time_ms=2,
        payload={"a": 1},
    )
    repo.record_candle(
        candle_id="c-001",
        symbol="BTCUSDT",
        interval="1h",
        open_time_ms=1,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
    )
    repo.record_breadth(breadth_id="b-001", payload={"advancing_pct": 0.6})
    repo.record_derivatives(
        derivatives_id="d-001", symbol="BTCUSDT", payload={}, funding_rate=0.0001
    )
    repo.record_universe(history_id="u-001", symbols=["BTCUSDT"], reason="test")
    repo.record_health(
        health_id="h-001", component="spot_websocket", status="connected", observed_time_ms=1
    )
    repo.record_metric(metric_id="m-001", scope="portfolio", payload={"sharpe": 1.0})
    assert repo.get("raw_market_events", "evt-001")["event_id"] == "evt-001"
    assert repo.get("candles", "c-001")["candle_id"] == "c-001"
    assert repo.get("breadth_snapshots", "b-001")["breadth_id"] == "b-001"
    assert repo.get("derivatives_snapshots", "d-001")["derivatives_id"] == "d-001"
    assert repo.get("universe_history", "u-001")["history_id"] == "u-001"
    assert repo.get("data_health", "h-001")["health_id"] == "h-001"
    assert repo.get("performance_metrics", "m-001")["metric_id"] == "m-001"
    repo.close()


def test_edge_records_are_append_only(tmp_path):
    repo = make_repo(tmp_path)
    build_chain(repo)
    with pytest.raises(sqlite3.IntegrityError):
        repo.connection.execute(
            "UPDATE edge_validation_records SET verdict='FAIL' WHERE record_id='edge-001'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        repo.connection.execute("DELETE FROM edge_validation_records WHERE record_id='edge-001'")
    with pytest.raises(ValueError, match="append-only"):
        repo.update_record("edge_validation_records", "edge-001")
    with pytest.raises(ValueError, match="append-only"):
        repo.delete_record("edge_validation_records", "edge-001")
    repo.close()


def test_strategy_versions_are_append_only(tmp_path):
    repo = make_repo(tmp_path)
    build_chain(repo)
    with pytest.raises(sqlite3.IntegrityError):
        repo.connection.execute(
            "UPDATE strategy_versions SET approver='mallory' WHERE version_id='synthetic_carry_v1@edge-001'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        repo.connection.execute(
            "DELETE FROM strategy_versions WHERE version_id='synthetic_carry_v1@edge-001'"
        )
    with pytest.raises(ValueError, match="append-only"):
        repo.update_record("strategy_versions", "synthetic_carry_v1@edge-001")
    with pytest.raises(ValueError, match="append-only"):
        repo.delete_record("strategy_versions", "synthetic_carry_v1@edge-001")
    repo.close()


def test_trace_unknown_trade_raises(tmp_path):
    repo = make_repo(tmp_path)
    build_chain(repo)
    with pytest.raises((KeyError, TraceNotFoundError)):
        repo.trace("trade-missing")
    repo.close()


def test_migrate_is_idempotent_and_versioned(tmp_path):
    first = make_repo(tmp_path)
    assert first.schema_version() == 1
    first.close()
    second = MemoryRepository(tmp_path / "memory.sqlite3")
    assert second.schema_version() == 1
    assert second.migrate() == 1
    second.close()
