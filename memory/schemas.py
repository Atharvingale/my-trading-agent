"""Table contracts for the Module 10 memory model.

Why a separate schemas module: repository.py owns behavior, this module owns
the stable shape. Every chain table carries its predecessor ID so trace() is
a query walk, not a convention. Storage engine is SQLite (stdlib only,
consistent with edge_validation, MarketStore, review_queue); migrations are
additive and idempotent via user_version + CREATE IF NOT EXISTS.
"""

from __future__ import annotations


SCHEMA_VERSION = 1

# Canonical chain order enforced by trace(). Supporting tables (candles,
# breadth, derivatives, universe, health, metrics, raw events) are queryable
# but sit outside the per-trade reconstruction path.
CHAIN_ORDER = (
    "market_snapshot",
    "edge_validation_record",
    "decision",
    "strategy_proposals",
    "decision_evidence",
    "risk_decision",
    "execution",
    "order",
    "position",
    "trade",
    "trade_analysis",
    "lesson",
    "strategy_version",
)

# All 20 spec tables. Each has a TEXT primary key so IDs join across stages.
TABLES = (
    "raw_market_events",
    "candles",
    "feature_snapshots",
    "breadth_snapshots",
    "derivatives_snapshots",
    "universe_history",
    "data_health",
    "edge_validation_records",
    "decisions",
    "decision_evidence",
    "strategy_proposals",
    "risk_decisions",
    "executions",
    "orders",
    "positions",
    "trades",
    "trade_analysis",
    "lessons",
    "strategy_versions",
    "performance_metrics",
)

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS raw_market_events (
    event_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    stream TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_time_ms INTEGER NOT NULL,
    received_time_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_events_symbol_time
    ON raw_market_events(symbol, event_time_ms);
CREATE TABLE IF NOT EXISTS candles (
    candle_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    open_time_ms INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_candles_symbol_time
    ON candles(symbol, open_time_ms);
CREATE TABLE IF NOT EXISTS feature_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    event_time_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feature_snapshots_symbol_time
    ON feature_snapshots(symbol, event_time_ms);
CREATE TABLE IF NOT EXISTS breadth_snapshots (
    breadth_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS derivatives_snapshots (
    derivatives_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    funding_rate REAL,
    open_interest REAL,
    basis REAL,
    liquidations REAL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_derivatives_symbol
    ON derivatives_snapshots(symbol, created_at);
CREATE TABLE IF NOT EXISTS universe_history (
    history_id TEXT PRIMARY KEY,
    symbols_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS data_health (
    health_id TEXT PRIMARY KEY,
    component TEXT NOT NULL,
    symbol TEXT,
    status TEXT NOT NULL,
    observed_time_ms INTEGER NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_data_health_time
    ON data_health(observed_time_ms);
CREATE TABLE IF NOT EXISTS edge_validation_records (
    record_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    strategy_family TEXT NOT NULL,
    verdict TEXT NOT NULL,
    snapshot_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES feature_snapshots(snapshot_id)
);
CREATE INDEX IF NOT EXISTS idx_edge_records_strategy
    ON edge_validation_records(strategy_family, created_at);
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence REAL NOT NULL,
    market_snapshot_id TEXT NOT NULL,
    edge_validation_record_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (market_snapshot_id) REFERENCES feature_snapshots(snapshot_id),
    FOREIGN KEY (edge_validation_record_id) REFERENCES edge_validation_records(record_id)
);
CREATE INDEX IF NOT EXISTS idx_decisions_symbol
    ON decisions(symbol, created_at);
CREATE TABLE IF NOT EXISTS strategy_proposals (
    proposal_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    action TEXT NOT NULL,
    edge_validation_record_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decisions(decision_id),
    FOREIGN KEY (edge_validation_record_id) REFERENCES edge_validation_records(record_id)
);
CREATE INDEX IF NOT EXISTS idx_proposals_decision
    ON strategy_proposals(decision_id);
CREATE TABLE IF NOT EXISTS decision_evidence (
    evidence_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    proposal_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decisions(decision_id),
    FOREIGN KEY (proposal_id) REFERENCES strategy_proposals(proposal_id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_decision
    ON decision_evidence(decision_id);
CREATE TABLE IF NOT EXISTS risk_decisions (
    risk_decision_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    status TEXT NOT NULL,
    approved_quantity REAL NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decisions(decision_id)
);
CREATE INDEX IF NOT EXISTS idx_risk_decision
    ON risk_decisions(decision_id);
CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    risk_decision_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (risk_decision_id) REFERENCES risk_decisions(risk_decision_id)
);
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (execution_id) REFERENCES executions(execution_id)
);
CREATE TABLE IF NOT EXISTS positions (
    position_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity REAL NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);
CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    position_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    pnl REAL NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (position_id) REFERENCES positions(position_id)
);
CREATE TABLE IF NOT EXISTS trade_analysis (
    analysis_id TEXT PRIMARY KEY,
    trade_id TEXT NOT NULL UNIQUE,
    diagnosis TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (trade_id) REFERENCES trades(trade_id)
);
CREATE TABLE IF NOT EXISTS lessons (
    lesson_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (analysis_id) REFERENCES trade_analysis(analysis_id)
);
CREATE TABLE IF NOT EXISTS strategy_versions (
    version_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    edge_validation_record_id TEXT NOT NULL,
    lesson_id TEXT,
    approver TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (edge_validation_record_id) REFERENCES edge_validation_records(record_id),
    FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id)
);
CREATE INDEX IF NOT EXISTS idx_versions_strategy
    ON strategy_versions(strategy_id, created_at);
CREATE TABLE IF NOT EXISTS performance_metrics (
    metric_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS edge_validation_records_no_update
BEFORE UPDATE ON edge_validation_records
BEGIN
    SELECT RAISE(ABORT, 'edge_validation_records are append-only');
END;
CREATE TRIGGER IF NOT EXISTS edge_validation_records_no_delete
BEFORE DELETE ON edge_validation_records
BEGIN
    SELECT RAISE(ABORT, 'edge_validation_records are append-only');
END;
CREATE TRIGGER IF NOT EXISTS strategy_versions_no_update
BEFORE UPDATE ON strategy_versions
BEGIN
    SELECT RAISE(ABORT, 'strategy_versions are append-only');
END;
CREATE TRIGGER IF NOT EXISTS strategy_versions_no_delete
BEFORE DELETE ON strategy_versions
BEGIN
    SELECT RAISE(ABORT, 'strategy_versions are append-only');
END;
"""
