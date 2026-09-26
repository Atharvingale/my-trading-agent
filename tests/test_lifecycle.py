"""Module 8 acceptance: lifecycle, unknown-gating, reconciliation, close intents."""

from __future__ import annotations

import pytest

from memory.repository import MemoryRepository
from models.execution import Fill, Order, OrderState
from models.trade import excursion, position_pnl
from monitoring.positions import LifecycleTracker


def make_tracker(tmp_path, with_memory=True):
    memory = MemoryRepository(tmp_path / "memory.sqlite3") if with_memory else None
    tracker = LifecycleTracker(tmp_path / "lifecycle.sqlite3", memory=memory)
    return tracker, memory


def entry_order(tracker, symbol="BTCUSDT", quantity=2.0, decision="dec-001", execution="exec-001"):
    return tracker.place_order(
        execution_id=execution,
        decision_id=decision,
        symbol=symbol,
        side="BUY",
        quantity=quantity,
        intent="ENTRY",
    )


# -- unit: state machine --
def test_order_state_machine_legal_and_illegal():
    order = Order(
        order_id="ord-1", execution_id="exec-1", decision_id="dec-1",
        symbol="BTCUSDT", side="BUY", quantity=2.0, order_type="MARKET",
    )
    assert order.state == OrderState.NEW
    order.apply_fill(Fill(fill_id="f-1", order_id="ord-1", price=100.0, quantity=1.0))
    assert order.state == OrderState.PARTIALLY_FILLED
    assert order.remaining() == pytest.approx(1.0)
    order.apply_fill(Fill(fill_id="f-2", order_id="ord-1", price=101.0, quantity=1.0))
    assert order.state == OrderState.FILLED
    with pytest.raises(ValueError, match="terminal"):
        order.apply_fill(Fill(fill_id="f-3", order_id="ord-1", price=101.0, quantity=0.5))
    with pytest.raises(ValueError, match="illegal"):
        order.transition(OrderState.NEW)
    over = Order(
        order_id="ord-2", execution_id="exec-1", decision_id="dec-1",
        symbol="BTCUSDT", side="BUY", quantity=1.0, order_type="MARKET",
    )
    with pytest.raises(ValueError, match="exceeds remaining"):
        over.apply_fill(Fill(fill_id="f-9", order_id="ord-2", price=100.0, quantity=2.0))


def test_unknown_needs_reconciliation_not_assumption(tmp_path):
    tracker, _ = make_tracker(tmp_path, with_memory=False)
    order = entry_order(tracker)
    tracker.mark_unknown(order.order_id)
    assert tracker.get_order(order.order_id)["state"] == OrderState.SUBMISSION_UNKNOWN
    with pytest.raises(ValueError, match="reconcile first"):
        tracker.apply_fill(Fill(fill_id="f-x", order_id=order.order_id, price=100.0, quantity=1.0))
    tracker.close()


# -- unit: MFE/MAE + slippage on a synthetic path --
def test_mfe_mae_and_slippage_on_synthetic_path():
    path: list[float] = []
    for price in (100.0, 103.0, 99.0, 105.0, 98.0, 102.0):
        path.append(price)
    mfe, mae = excursion("BUY", 100.0, path)
    assert mfe == pytest.approx(5.0)
    assert mae == pytest.approx(2.0)
    mfe_s, mae_s = excursion("SELL", 100.0, path)
    assert mfe_s == pytest.approx(2.0)
    assert mae_s == pytest.approx(5.0)
    flat_mfe, flat_mae = excursion("BUY", 100.0, [100.0, 100.0])
    assert (flat_mfe, flat_mae) == (0.0, 0.0)
    fill = Fill(
        fill_id="f-s", order_id="ord-s", price=100.5, quantity=1.0, expected_price=100.0
    )
    assert fill.slippage_bps() == pytest.approx(50.0)
    assert Fill(fill_id="f-n", order_id="ord-s", price=100.5, quantity=1.0).slippage_bps() is None
    assert position_pnl("BUY", 100.0, 103.0, 2.0) == pytest.approx(6.0)
    assert position_pnl("SELL", 100.0, 97.0, 2.0) == pytest.approx(6.0)


# -- lifecycle: partial fills -> position -> close -> trade --
def test_partial_fills_build_one_position_then_close(tmp_path):
    tracker, _ = make_tracker(tmp_path, with_memory=False)
    order = entry_order(tracker, quantity=4.0)
    tracker.apply_fill(Fill(fill_id="f-1", order_id=order.order_id, price=100.0, quantity=1.5, fee=0.5))
    assert tracker.get_order(order.order_id)["state"] == OrderState.PARTIALLY_FILLED
    tracker.apply_fill(Fill(fill_id="f-2", order_id=order.order_id, price=101.0, quantity=2.5, fee=0.5))
    assert tracker.get_order(order.order_id)["state"] == OrderState.FILLED
    holding = tracker.open_position("BTCUSDT")
    assert holding is not None
    assert holding["filled_quantity"] == pytest.approx(4.0)
    assert holding["fees"] == pytest.approx(1.0)
    # Same-side ENTRY while holding is blocked; opposite side closes.
    assert tracker.classify_intent("BUY", "BTCUSDT") == "ENTRY_BLOCKED"
    assert tracker.classify_intent("SELL", "BTCUSDT") == "CLOSE"
    with pytest.raises(ValueError, match="ENTRY blocked"):
        tracker.place_order(
            execution_id="exec-2", decision_id="dec-2", symbol="BTCUSDT",
            side="BUY", quantity=1.0, intent="ENTRY",
        )
    exit_order = tracker.place_order(
        execution_id="exec-9", decision_id="dec-9", symbol="BTCUSDT",
        side="SELL", quantity=4.0, intent="CLOSE",
    )
    result = tracker.apply_fill(
        Fill(fill_id="f-x1", order_id=exit_order.order_id, price=103.0, quantity=4.0, fee=0.4),
        timestamp_ms=2000,
    )
    assert result["closed_trade_id"] is not None
    assert tracker.open_position("BTCUSDT") is None
    chain = tracker.get_chain(str(result["closed_trade_id"]))
    assert chain["decision_id"] == "dec-9"
    assert chain["execution_id"] == "exec-9"
    assert chain["order_id"] == order.order_id
    assert chain["exit_order_id"] == exit_order.order_id
    assert chain["trade"]["realized_pnl"] > 0
    tracker.close()


def test_reduce_then_close_leaves_correct_open_quantity(tmp_path):
    tracker, _ = make_tracker(tmp_path, with_memory=False)
    order = entry_order(tracker, quantity=4.0)
    tracker.apply_fill(Fill(fill_id="f-1", order_id=order.order_id, price=100.0, quantity=4.0))
    reduce_order = tracker.place_order(
        execution_id="exec-r", decision_id="dec-r", symbol="BTCUSDT",
        side="SELL", quantity=1.5, intent="REDUCE",
    )
    tracker.apply_fill(Fill(fill_id="f-r1", order_id=reduce_order.order_id, price=102.0, quantity=1.5))
    holding = tracker.open_position("BTCUSDT")
    assert holding is not None
    assert float(holding["filled_quantity"]) - float(holding["exit_filled_quantity"]) == pytest.approx(2.5)
    with pytest.raises(ValueError, match="exceeds open quantity"):
        tracker.place_order(
            execution_id="exec-r2", decision_id="dec-r2", symbol="BTCUSDT",
            side="SELL", quantity=9.0, intent="REDUCE",
        )
    tracker.close()


def test_stop_target_state_from_marks(tmp_path):
    tracker, _ = make_tracker(tmp_path, with_memory=False)
    order = entry_order(tracker, quantity=1.0)
    tracker.apply_fill(Fill(fill_id="f-1", order_id=order.order_id, price=100.0, quantity=1.0))
    holding = tracker.open_position("BTCUSDT")
    assert holding is not None
    position_id = str(holding["position_id"])
    tracker.connection.execute(
        "UPDATE positions SET stop=?, target=? WHERE position_id=?", (98.0, 103.0, position_id)
    )
    tracker.connection.commit()
    assert tracker.stop_state(position_id) == "ARMED"
    tracker.mark_price("BTCUSDT", 97.0, 5000)
    assert tracker.stop_state(position_id) == "STOP_HIT"
    tracker.mark_price("BTCUSDT", 104.0, 6000)
    assert tracker.stop_state(position_id) == "TARGET_HIT"
    refreshed = tracker.get_position(position_id)
    assert refreshed["mfe"] == pytest.approx(4.0)
    assert refreshed["mae"] == pytest.approx(3.0)
    tracker.close()


# -- SUBMISSION_UNKNOWN gating --
def test_unknown_blocks_new_entries_until_resolved(tmp_path):
    tracker, _ = make_tracker(tmp_path, with_memory=False)
    order = entry_order(tracker, symbol="BTCUSDT")
    assert tracker.may_enter("BTCUSDT") is True
    tracker.mark_unknown(order.order_id)
    assert tracker.has_unknown("BTCUSDT") is True
    assert tracker.may_enter("BTCUSDT") is False
    with pytest.raises(ValueError, match="SUBMISSION_UNKNOWN"):
        tracker.place_order(
            execution_id="exec-2", decision_id="dec-2", symbol="BTCUSDT",
            side="BUY", quantity=1.0, intent="ENTRY",
        )
    tracker.resolve_unknown(order.order_id, remote_state="CANCELED")
    assert tracker.may_enter("BTCUSDT") is True
    # Other symbols are unaffected by the block.
    tracker2_order = entry_order(tracker, symbol="ETHUSDT")
    assert tracker2_order.state == OrderState.NEW
    tracker.close()


def test_unknown_resolve_paths():
    tracker_holder: list[LifecycleTracker] = []

    import tempfile as _tempfile

    first_dir = _tempfile.mkdtemp()
    first = LifecycleTracker(first_dir + "/life.sqlite3")
    order = first.place_order(
        execution_id="exec-u", decision_id="dec-u", symbol="BTCUSDT",
        side="BUY", quantity=1.0, intent="ENTRY",
    )
    first.mark_unknown(order.order_id)
    assert first.resolve_unknown(order.order_id, remote_state="FILLED") == OrderState.FILLED
    first.close()
    second_dir = _tempfile.mkdtemp()
    second = LifecycleTracker(second_dir + "/life.sqlite3")
    tracker_holder.append(second)
    order2 = second.place_order(
        execution_id="exec-u2", decision_id="dec-u2", symbol="BTCUSDT",
        side="BUY", quantity=1.0, intent="ENTRY",
    )
    second.mark_unknown(order2.order_id)
    assert second.resolve_unknown(order2.order_id, remote_state=None, definitive=True) == OrderState.CANCELED
    with pytest.raises(ValueError, match="not SUBMISSION_UNKNOWN"):
        second.resolve_unknown(order2.order_id, remote_state="FILLED")
    second.close()


# -- reconciliation: missed fill recovered without manual intervention --
def test_missed_fill_event_recovered_by_reconciliation(tmp_path):
    tracker, _ = make_tracker(tmp_path, with_memory=False)
    order = entry_order(tracker, quantity=2.0)
    # Only the first fill arrived over the wire; the second was missed.
    tracker.apply_fill(Fill(fill_id="f-seen", order_id=order.order_id, price=100.0, quantity=1.0))
    assert tracker.get_order(order.order_id)["state"] == OrderState.PARTIALLY_FILLED
    report = tracker.reconcile_from_exchange(
        [{"order_id": order.order_id, "status": "FILLED"}],
        [
            {"order_id": order.order_id, "fill_id": "f-seen", "price": 100.0, "quantity": 1.0},
            {"order_id": order.order_id, "fill_id": "f-missed", "price": 101.0, "quantity": 1.0, "fee": 0.2},
        ],
    )
    assert report["recovered_fills"] == 1
    assert tracker.get_order(order.order_id)["state"] == OrderState.FILLED
    holding = tracker.open_position("BTCUSDT")
    assert holding is not None
    assert holding["filled_quantity"] == pytest.approx(2.0)
    assert holding["reconcile_state"] in ("CLEAN", "RECONCILED")
    tracker.close()


def test_restart_rebuilds_from_exchange_truth(tmp_path):
    tracker, _ = make_tracker(tmp_path, with_memory=False)
    order = entry_order(tracker, quantity=1.0, execution="exec-r1", decision="dec-r1")
    tracker.mark_unknown(order.order_id)
    tracker.close()
    # Simulate a process restart: reopen the same ledger file.
    reopened = LifecycleTracker(tmp_path / "lifecycle.sqlite3")
    assert reopened.has_unknown("BTCUSDT") is True
    assert reopened.may_enter("BTCUSDT") is False
    report = reopened.reconcile_from_exchange(
        [{"order_id": order.order_id, "status": "FILLED"}],
        [{"order_id": order.order_id, "fill_id": "f-late", "price": 100.0, "quantity": 1.0}],
    )
    assert report["resolved_unknown"] == 1
    assert reopened.may_enter("BTCUSDT") is False  # position now open, not unknown
    assert reopened.open_position("BTCUSDT") is not None
    reopened.close()


# -- integration: risk-approved entry through Module 7 into lifecycle --
def test_risk_to_execution_to_lifecycle_close_flow(tmp_path):
    from datetime import datetime, timezone

    from execution.n8n_client import ExecutionConfig, build_request
    from execution.order_manager import ExecutionOrderManager
    from hermes.context import ContextBuilder
    from hermes.models.decision import Decision
    from risk.engine import RiskEngine

    now_ms = 1_700_000_000_000
    moment = datetime.fromtimestamp(now_ms / 1000.0, tz=timezone.utc)
    builder = ContextBuilder(stale_after_seconds=30.0)
    snapshot = fresh_snapshot_for_flow()
    context = builder.build(
        symbol="BTCUSDT",
        feature_snapshot=snapshot,
        event_time_ms=now_ms,
        breadth={"advancing_pct": 0.7},
        cross_exchange=None,
        health_entries=[
            {"component": "spot_websocket", "symbol": None, "status": "connected",
             "observed_time_ms": now_ms, "details": {}},
        ],
        now_ms=now_ms,
    )
    assert context.valid is True
    decision = Decision(
        decision_id="dec-flow-1",
        timestamp=moment,
        symbol="BTCUSDT",
        action="BUY",
        confidence=0.7,
        entry={"symbol": "BTCUSDT", "side": "BUY", "reference_price": 100.0},
        position={"position_qty": 0.0, "exposure_notional": 0.0, "unrealized_pnl": 0.0, "realized_pnl": 0.0},
        risk={"stop_loss": 98.0, "take_profit": 103.0, "risk_amount": 0.0},
        time_horizon="15m",
        thesis=["flow thesis"],
        strategy_version_id="v1",
        expiry_seconds=120,
    )
    engine = RiskEngine()
    risk = engine.evaluate(
        decision, context, equity=10000.0, peak_equity=10000.0, daily_realized_pnl=0.0,
        open_notional=0.0, symbol_exposure=0.0, open_positions=0, now_ms=now_ms + 1000,
    )
    assert risk.status == "APPROVED"
    request = build_request(risk, symbol="BTCUSDT", side="BUY", now=moment)
    assert request.quantity == risk.approved_quantity
    config = ExecutionConfig(
        webhook_url="https://n8n.local/webhook/flow", webhook_secret="flow-secret", environment="paper"
    )
    manager = ExecutionOrderManager(tmp_path / "exec_flow.sqlite3")

    def sender(url, payload, headers, timeout):
        assert payload["quantity"] == risk.approved_quantity
        return {"order_id": "ord-flow-entry", "status": "ACKED"}

    outcome = manager.submit_once(
        request, config=config, sender=sender, now=moment, risk_decision=risk
    )
    assert outcome["state"] == "ACKED"
    # Lifecycle picks up the Module 7 execution_id without re-submitting it.
    tracker, _ = make_tracker(tmp_path, with_memory=False)
    entry = tracker.place_order(
        execution_id=request.execution_id, decision_id="dec-flow-1", symbol="BTCUSDT",
        side="BUY", quantity=request.quantity, intent="ENTRY",
    )
    tracker.apply_fill(Fill(fill_id="f-e1", order_id=entry.order_id, price=100.0, quantity=request.quantity))
    assert tracker.open_position("BTCUSDT") is not None
    # Close intent flows through lifecycle exits while risk keeps its
    # entry block (Module 6 untouched): same-side add still rejected here.
    assert tracker.classify_intent("BUY", "BTCUSDT") == "ENTRY_BLOCKED"
    exit_order = tracker.place_order(
        execution_id="exec-flow-exit", decision_id="dec-flow-1", symbol="BTCUSDT",
        side="SELL", quantity=request.quantity, intent="CLOSE",
    )
    result = tracker.apply_fill(
        Fill(fill_id="f-x1", order_id=exit_order.order_id, price=102.0, quantity=request.quantity),
        timestamp_ms=now_ms + 60_000,
    )
    assert result["closed_trade_id"] is not None
    chain = tracker.get_chain(str(result["closed_trade_id"]))
    assert chain["decision_id"] == "dec-flow-1"
    assert chain["execution_id"] == "exec-flow-exit"
    assert chain["order_id"] == entry.order_id
    assert chain["exit_order_id"] == exit_order.order_id
    assert chain["trade"]["realized_pnl"] > 0
    # Entry leg still resolves through the Module 7 execution_id.
    assert tracker.get_order(entry.order_id)["execution_id"] == request.execution_id
    manager.close()
    tracker.close()


def fresh_snapshot_for_flow(symbol="BTCUSDT"):
    return {
        "symbol": symbol,
        "event_time": "2024-01-01T00:00:00+00:00",
        "last_price": 100.0,
        "spread_bps": 2.0,
        "bid_depth": 500.0,
        "ask_depth": 500.0,
        "depth_within_bps": {25: {"bid_qty": 400.0, "ask_qty": 400.0}},
        "execution_quality": {"BUY": {"price_impact_rate": 0.0001, "status": "OK"}},
        "technical": {"1h": {"ema_fast": 101.0, "ema_slow": 100.0, "rsi": 55.0, "atr": 1.0,
                             "vwap": 99.5, "bollinger_bandwidth": 0.04, "returns": 0.001}},
        "multi_timeframe_alignment": {"state": "BULLISH", "confirmed_timeframes": 2},
        "trade_cvd": 10.0,
        "aggressive_buy_pct": 0.55,
        "large_trade_concentration": 0.1,
        "top_book_imbalance": 0.05,
        "depth_imbalance": 0.02,
        "trade_volume": 100.0,
    }


# -- memory persistence through the existing repository --
def seed_upstream(memory, decision_id, execution_id, risk_id):
    # Why the full chain: memory enforces FKs from order up through
    # execution/risk/decision to snapshot+edge, so lifecycle mirroring lands
    # on a coherent backbone instead of orphan rows. No Module 10 change.
    if "snap-001" not in _known(memory, "feature_snapshots", "snapshot_id"):
        memory.record_market_snapshot(
            snapshot_id="snap-001", symbol="BTCUSDT", event_time_ms=1, payload={"close": 100.0}
        )
    if "edge-001" not in _known(memory, "edge_validation_records", "record_id"):
        memory.record_edge_validation(
            record_id="edge-001", strategy_id="synthetic_v1", strategy_family="synthetic",
            verdict="PASS", snapshot_id="snap-001", payload={},
        )
    memory.record_decision(
        decision_id=decision_id, symbol="BTCUSDT", action="BUY", confidence=0.7,
        market_snapshot_id="snap-001", edge_validation_record_id="edge-001", payload={},
    )
    memory.record_risk(
        risk_decision_id=risk_id, decision_id=decision_id, status="APPROVED",
        approved_quantity=2.0, payload={},
    )
    memory.record_execution(
        execution_id=execution_id, risk_decision_id=risk_id, status="ACKED", payload={}
    )


def _known(memory, table, pk):
    rows = memory.connection.execute("SELECT %s FROM %s" % (pk, table)).fetchall()
    found: set[str] = set()
    for row in rows:
        found.add(str(row[0]))
    return found


def test_lifecycle_mirrors_into_memory_repository(tmp_path):
    tracker, memory = make_tracker(tmp_path, with_memory=True)
    assert memory is not None
    seed_upstream(memory, "dec-001", "exec-001", "risk-001")
    seed_upstream(memory, "dec-x", "exec-x", "risk-x")
    order = entry_order(tracker, quantity=2.0)
    assert memory.get("orders", order.order_id)["order_id"] == order.order_id
    tracker.apply_fill(Fill(fill_id="f-1", order_id=order.order_id, price=100.0, quantity=2.0))
    holding = tracker.open_position("BTCUSDT")
    assert holding is not None
    assert memory.get("positions", str(holding["position_id"]))["position_id"] == str(holding["position_id"])
    exit_order = tracker.place_order(
        execution_id="exec-x", decision_id="dec-x", symbol="BTCUSDT",
        side="SELL", quantity=2.0, intent="CLOSE",
    )
    result = tracker.apply_fill(
        Fill(fill_id="f-x", order_id=exit_order.order_id, price=102.0, quantity=2.0)
    )
    assert result["closed_trade_id"] is not None
    stored = memory.get("trades", str(result["closed_trade_id"]))
    assert stored["trade_id"] == str(result["closed_trade_id"])
    chain = tracker.get_chain(str(result["closed_trade_id"]))
    assert chain["position_id"] == str(holding["position_id"])
    # The mirrored backbone resolves end to end through the same IDs.
    assert memory.get("executions", "exec-001")["risk_decision_id"] == "risk-001"
    tracker.close()
    memory.close()
