"""Lifecycle tracker: order → fill → position → closed trade (Module 8).

Why this module owns live state: the Module 7 ledger tracks request
submission, and MemoryRepository keeps the audit backbone — neither runs a
fill-driven state machine. This tracker does: partial fills accumulate,
ambiguous submissions gate entries, exits are explicit CLOSE/REDUCE intents
(so the Module 6 entry block stands while closes flow), and every restart,
gap, or unknown resolves against exchange truth before new entries resume.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from models.execution import Fill, Order, OrderState
from models.trade import Position, Trade, excursion, position_pnl


INTENTS = ("ENTRY", "REDUCE", "CLOSE")


class LifecycleTracker:
    """Fill-driven lifecycle with unknown-state gating and memory mirroring."""

    def __init__(self, database_path: str | Path, memory: Any = None) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.memory = memory
        self._mirrored_orders: set[str] = set()
        self._mirrored_positions: set[str] = set()
        self._mirrored_trades: set[str] = set()
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                position_id TEXT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                order_type TEXT NOT NULL,
                intent TEXT NOT NULL,
                state TEXT NOT NULL,
                filled_quantity REAL NOT NULL,
                amendments INTEGER NOT NULL,
                submit_latency_ms INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fills (
                fill_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                fee REAL NOT NULL,
                funding REAL NOT NULL,
                latency_ms INTEGER,
                expected_price REAL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
            );
            CREATE TABLE IF NOT EXISTS positions (
                position_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_order_id TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                stop REAL NOT NULL,
                target REAL NOT NULL,
                fees REAL NOT NULL,
                funding REAL NOT NULL,
                filled_quantity REAL NOT NULL,
                exit_filled_quantity REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                mfe REAL NOT NULL,
                mae REAL NOT NULL,
                slippage_sum REAL NOT NULL,
                slippage_samples INTEGER NOT NULL,
                latency_total INTEGER NOT NULL,
                latency_samples INTEGER NOT NULL,
                opened_at_ms INTEGER NOT NULL,
                closed_at_ms INTEGER,
                amendments INTEGER NOT NULL,
                reconcile_state TEXT NOT NULL,
                mark_price REAL NOT NULL,
                price_path_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                position_id TEXT NOT NULL,
                entry_order_id TEXT NOT NULL,
                exit_order_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                execution_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                fees REAL NOT NULL,
                funding REAL NOT NULL,
                mfe REAL NOT NULL,
                mae REAL NOT NULL,
                duration_ms INTEGER NOT NULL,
                avg_slippage REAL,
                avg_latency REAL,
                amendments INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (position_id) REFERENCES positions(position_id)
            );
            CREATE TRIGGER IF NOT EXISTS lifecycle_no_delete_orders
            BEFORE DELETE ON orders
            BEGIN
                SELECT RAISE(ABORT, 'lifecycle orders are auditable: no deletes');
            END;
            CREATE TRIGGER IF NOT EXISTS lifecycle_no_delete_fills
            BEFORE DELETE ON fills
            BEGIN
                SELECT RAISE(ABORT, 'lifecycle fills are auditable: no deletes');
            END;
            CREATE TRIGGER IF NOT EXISTS lifecycle_no_delete_trades
            BEFORE DELETE ON trades
            BEGIN
                SELECT RAISE(ABORT, 'lifecycle trades are auditable: no deletes');
            END;
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> LifecycleTracker:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    # -- gating: explicit entry vs close semantics (Module 6 stays untouched) --
    def has_unknown(self, symbol: str) -> bool:
        token = str(symbol).strip().upper()
        row = self.connection.execute(
            "SELECT 1 FROM orders WHERE symbol=? AND state=? LIMIT 1",
            (token, OrderState.SUBMISSION_UNKNOWN),
        ).fetchone()
        return row is not None

    def open_position(self, symbol: str) -> dict[str, Any] | None:
        """Return the live position row for a symbol, or None when flat."""
        token = str(symbol).strip().upper()
        row = self.connection.execute(
            "SELECT * FROM positions WHERE symbol=? AND closed_at_ms IS NULL ORDER BY rowid DESC LIMIT 1",
            (token,),
        ).fetchone()
        if row is None:
            return None
        result: dict[str, Any] = {}
        for key in row.keys():
            result[key] = row[key]
        return result

    def may_enter(self, symbol: str) -> bool:
        """New entries need a clean symbol: no unknown, no open position."""
        token = str(symbol).strip().upper()
        if self.has_unknown(token):
            return False
        return self.open_position(token) is None

    def classify_intent(self, side: str, symbol: str) -> str:
        """ENTRY opens, CLOSE/REDUCE exits — never decided by quantity alone."""
        action = str(side).strip().upper()
        if action not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        holding = self.open_position(symbol)
        if holding is None:
            return "ENTRY"
        if str(holding["side"]).upper() == action:
            return "ENTRY_BLOCKED"
        remaining = float(holding["filled_quantity"]) - float(holding["exit_filled_quantity"])
        if remaining <= 0:
            return "ENTRY"
        return "CLOSE"

    # -- order placement --
    def place_order(
        self,
        *,
        execution_id: str,
        decision_id: str,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        intent: str = "ENTRY",
        stop: float = 0.0,
        target: float = 0.0,
        position_id: str | None = None,
        submit_latency_ms: int | None = None,
    ) -> Order:
        """Place an ENTRY, REDUCE, or CLOSE order with lifecycle gating."""
        if intent not in INTENTS:
            raise ValueError("intent must be ENTRY, REDUCE, or CLOSE")
        token = str(symbol).strip().upper()
        if not token:
            raise ValueError("symbol must be non-empty")
        if self.has_unknown(token):
            raise ValueError("symbol %s has SUBMISSION_UNKNOWN: reconcile first" % token)
        holding = self.open_position(token)
        action = str(side).strip().upper()
        linked_position = position_id
        if intent == "ENTRY":
            if holding is not None:
                raise ValueError("ENTRY blocked: open position exists; use REDUCE/CLOSE")
        else:
            if holding is None:
                raise ValueError("%s requires an open position on %s" % (intent, token))
            if str(holding["side"]).upper() == action:
                raise ValueError("%s must be the opposite side of the holding" % intent)
            open_qty = float(holding["filled_quantity"]) - float(holding["exit_filled_quantity"])
            if float(quantity) > open_qty + 1e-9:
                raise ValueError("%.6f exceeds open quantity %.6f" % (float(quantity), open_qty))
            linked_position = str(holding["position_id"])
        order_id = "ord_" + str(uuid4()).replace("-", "")[:16]
        order = Order(
            order_id=order_id,
            execution_id=str(execution_id).strip(),
            decision_id=str(decision_id).strip(),
            symbol=token,
            side=action,
            quantity=float(quantity),
            order_type=str(order_type).strip().upper() or "MARKET",
            submit_latency_ms=submit_latency_ms,
        )
        moment = _now_text()
        self.connection.execute(
            """INSERT INTO orders
            (order_id, execution_id, decision_id, position_id, symbol, side,
             quantity, order_type, intent, state, filled_quantity, amendments,
             submit_latency_ms, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0, ?, ?, ?)""",
            (
                order.order_id, order.execution_id, order.decision_id, linked_position,
                order.symbol, order.side, order.quantity, order.order_type, intent,
                order.state, order.submit_latency_ms, moment, moment,
            ),
        )
        self.connection.commit()
        _ = stop
        _ = target
        self._mirror_order(order)
        return order

    def mark_unknown(self, order_id: str) -> None:
        order = self._load_order(str(order_id))
        order.mark_unknown()
        self._save_order(order)

    def amend_order(self, order_id: str) -> None:
        """Record a correction event; quantity itself is never rewritten."""
        order = self._load_order(str(order_id))
        if order.state in (OrderState.FILLED, OrderState.CANCELED, OrderState.REJECTED):
            raise ValueError("order %s is terminal" % order_id)
        order.amendments = order.amendments + 1
        self._save_order(order)
        position = self._position_for_entry_order(order.order_id, order.symbol)
        if position is not None:
            self.connection.execute(
                "UPDATE positions SET amendments=amendments+1 WHERE position_id=?",
                (position["position_id"],),
            )
            self.connection.commit()

    # -- fills drive positions --
    def apply_fill(self, fill: Fill, *, timestamp_ms: int = 0) -> dict[str, Any]:
        """Attach a fill; opens/extends the position or realizes an exit."""
        order = self._load_order(fill.order_id)
        order.apply_fill(fill)
        self._save_order(order)
        self._store_fill(fill)
        position = self._position_for_entry_order(order.order_id, order.symbol)
        intent = self._order_intent(order.order_id)
        if intent == "ENTRY" and position is None:
            position_id = "pos_" + str(uuid4()).replace("-", "")[:16]
            created = self._open_position(order, fill, position_id, timestamp_ms)
            self._mirror_position(created)
            return {"order": order.to_dict(), "position_id": position_id, "closed_trade_id": None}
        if intent == "ENTRY" and position is not None:
            self._extend_position(position["position_id"], fill, timestamp_ms)
            return {"order": order.to_dict(), "position_id": position["position_id"], "closed_trade_id": None}
        # Exit fills realize PnL against the linked holding.
        linked = self._linked_position(order.order_id)
        if linked is None:
            raise ValueError("exit order %s has no linked position" % order.order_id)
        closed = self._apply_exit_fill(linked["position_id"], order, fill, timestamp_ms)
        return {"order": order.to_dict(), "position_id": linked["position_id"], "closed_trade_id": closed}

    def mark_price(self, symbol: str, price: float, timestamp_ms: int) -> None:
        """Record a mark; refreshes MFE/MAE and unrealized state while open."""
        token = str(symbol).strip().upper()
        if price <= 0:
            raise ValueError("mark price must be positive")
        holding = self.open_position(token)
        if holding is None:
            return
        path = json.loads(str(holding["price_path_json"]))
        path.append(float(price))
        mfe, mae = excursion(str(holding["side"]), float(holding["entry_price"]), path)
        self.connection.execute(
            "UPDATE positions SET mark_price=?, price_path_json=?, mfe=?, mae=? WHERE position_id=?",
            (float(price), json.dumps(path), mfe, mae, str(holding["position_id"])),
        )
        self.connection.commit()

    def stop_state(self, position_id: str) -> str:
        """ARMED, STOP_HIT, or TARGET_HIT from the latest mark vs levels."""
        row = self.connection.execute(
            "SELECT * FROM positions WHERE position_id=?", (str(position_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown position: {position_id}")
        mark = float(row["mark_price"])
        if mark <= 0:
            return "ARMED"
        side = str(row["side"]).upper()
        stop = float(row["stop"])
        target = float(row["target"])
        if side == "BUY":
            if stop > 0 and mark <= stop:
                return "STOP_HIT"
            if target > 0 and mark >= target:
                return "TARGET_HIT"
            return "ARMED"
        if stop > 0 and mark >= stop:
            return "STOP_HIT"
        if target > 0 and mark <= target:
            return "TARGET_HIT"
        return "ARMED"

    # -- reconciliation: rebuild from exchange truth --
    def reconcile_from_exchange(
        self, exchange_orders: list[dict[str, Any]], exchange_fills: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Adopt exchange truth for tracked orders; recover missed fills.

        Triggered on restart, on gap detection (a fill sequence skip), and for
        any SUBMISSION_UNKNOWN row. Returns counts plus newly blocked symbols.
        Local state never overrides the exchange — it only catches up to it.
        """
        recovered_fills = 0
        resolved_unknown = 0
        by_exchange: dict[str, dict[str, Any]] = {}
        for entry in exchange_orders:
            key = self._exchange_key(entry)
            if key:
                by_exchange[key] = entry
        fills_by_order: dict[str, list[dict[str, Any]]] = {}
        for fill_entry in exchange_fills:
            order_key = str(fill_entry.get("order_id", "")).strip()
            if not order_key:
                continue
            if order_key not in fills_by_order:
                fills_by_order[order_key] = []
            fills_by_order[order_key].append(fill_entry)
        local_rows = self.connection.execute("SELECT * FROM orders ORDER BY rowid").fetchall()
        for local in local_rows:
            order_id = str(local["order_id"])
            state = str(local["state"])
            if state in (OrderState.FILLED, OrderState.CANCELED, OrderState.REJECTED):
                continue
            was_unknown = state == OrderState.SUBMISSION_UNKNOWN
            remote = by_exchange.get(order_id)
            known_fills = self._known_fill_ids(order_id)
            for fill_entry in fills_by_order.get(order_id, []):
                fill_id = str(fill_entry.get("fill_id", "")).strip()
                if fill_id and fill_id not in known_fills:
                    recovered = Fill(
                        fill_id=fill_id,
                        order_id=order_id,
                        price=float(fill_entry.get("price", 0.0)),
                        quantity=float(fill_entry.get("quantity", 0.0)),
                        fee=float(fill_entry.get("fee", 0.0) or 0.0),
                        funding=float(fill_entry.get("funding", 0.0) or 0.0),
                    )
                    current = self._load_order(order_id)
                    if current.state == OrderState.SUBMISSION_UNKNOWN:
                        self.resolve_unknown(order_id, remote_state="PARTIALLY_FILLED")
                        current = self._load_order(order_id)
                    current.apply_fill(recovered)
                    self._save_order(current)
                    self._store_fill(recovered)
                    self._mirror_fill_into_position(current, recovered)
                    recovered_fills = recovered_fills + 1
                    known_fills.add(fill_id)
            # Why reload: fills applied above may already have moved the
            # order out of SUBMISSION_UNKNOWN; resolving again would raise.
            # Either path out of unknown counts as a resolution.
            current_state = self._load_order(order_id).state
            if was_unknown and current_state != OrderState.SUBMISSION_UNKNOWN:
                resolved_unknown = resolved_unknown + 1
            elif current_state == OrderState.SUBMISSION_UNKNOWN:
                if remote is not None:
                    self.resolve_unknown(order_id, remote_state=str(remote.get("status", "FILLED")))
                    resolved_unknown = resolved_unknown + 1
        blocked: list[str] = []
        unknown_rows = self.connection.execute(
            "SELECT DISTINCT symbol FROM orders WHERE state=?", (OrderState.SUBMISSION_UNKNOWN,)
        ).fetchall()
        for row in unknown_rows:
            blocked.append(str(row["symbol"]))
        report: dict[str, Any] = {}
        report["recovered_fills"] = recovered_fills
        report["resolved_unknown"] = resolved_unknown
        report["blocked_symbols"] = blocked
        return report

    def resolve_unknown(self, order_id: str, remote_state: str | None, definitive: bool = True) -> str:
        """Resolve one ambiguous order from confirmed exchange truth.

        remote_state is the exchange status (FILLED/PARTIAL/CANCELED/…); when
        the exchange definitively has no record and definitive is True, the
        order is CANCELED. Guessed resolutions raise instead of assuming.
        """
        order = self._load_order(str(order_id))
        if order.state != OrderState.SUBMISSION_UNKNOWN:
            raise ValueError("order %s is %s, not SUBMISSION_UNKNOWN" % (order_id, order.state))
        if remote_state is None:
            if definitive is False:
                raise ValueError("no exchange truth yet for %s: refusing to guess" % order_id)
            order.transition(OrderState.CANCELED)
            self._save_order(order)
            self._flag_reconciled(order.symbol)
            return order.state
        token = str(remote_state).strip().upper()
        if token in ("FILLED", "FILL", "CLOSED"):
            # Why no synthetic fill: exchange confirms the fill but sent no
            # fill detail, so the order closes at full quantity without
            # inventing prices. Position math only ever uses real fills.
            order.filled_quantity = order.quantity
            order.transition(OrderState.FILLED)
            self._save_order(order)
            self._flag_reconciled(order.symbol)
            return order.state
        if token in ("PARTIAL", "PARTIALLY_FILLED", "PARTIAL_FILL"):
            order.transition(OrderState.PARTIALLY_FILLED)
            self._save_order(order)
            return order.state
        if token in ("CANCELED", "CANCELLED", "REJECTED", "EXPIRED"):
            order.transition(OrderState.CANCELED if "CANCEL" in token or "EXPIR" in token else OrderState.REJECTED)
            self._save_order(order)
            self._flag_reconciled(order.symbol)
            return order.state
        raise ValueError("unrecognized exchange state %r for %s" % (remote_state, order_id))

    # -- chain + reads --
    def get_chain(self, trade_id: str) -> dict[str, Any]:
        """Full ID chain: decision → execution → order → position → exit → trade."""
        row = self.connection.execute(
            "SELECT * FROM trades WHERE trade_id=?", (str(trade_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown trade: {trade_id}")
        trade: dict[str, Any] = {}
        for key in row.keys():
            trade[key] = row[key]
        chain: dict[str, Any] = {}
        chain["decision_id"] = trade["decision_id"]
        chain["execution_id"] = trade["execution_id"]
        chain["order_id"] = trade["entry_order_id"]
        chain["position_id"] = trade["position_id"]
        chain["exit_order_id"] = trade["exit_order_id"]
        chain["trade_id"] = trade["trade_id"]
        chain["trade"] = trade
        return chain

    def get_order(self, order_id: str) -> dict[str, Any]:
        order = self._load_order(str(order_id))
        return order.to_dict()

    def get_position(self, position_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM positions WHERE position_id=?", (str(position_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown position: {position_id}")
        result: dict[str, Any] = {}
        for key in row.keys():
            result[key] = row[key]
        return result

    # -- internals --
    def _load_order(self, order_id: str) -> Order:
        row = self.connection.execute(
            "SELECT * FROM orders WHERE order_id=?", (order_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown order: {order_id}")
        return Order(
            order_id=str(row["order_id"]),
            execution_id=str(row["execution_id"]),
            decision_id=str(row["decision_id"]),
            symbol=str(row["symbol"]),
            side=str(row["side"]),
            quantity=float(row["quantity"]),
            order_type=str(row["order_type"]),
            state=str(row["state"]),
            filled_quantity=float(row["filled_quantity"]),
            amendments=int(row["amendments"]),
            submit_latency_ms=row["submit_latency_ms"],
        )

    def _save_order(self, order: Order) -> None:
        self.connection.execute(
            "UPDATE orders SET state=?, filled_quantity=?, amendments=?, updated_at=? WHERE order_id=?",
            (order.state, order.filled_quantity, order.amendments, _now_text(), order.order_id),
        )
        self.connection.commit()

    def _store_fill(self, fill: Fill) -> None:
        self.connection.execute(
            """INSERT OR IGNORE INTO fills
            (fill_id, order_id, price, quantity, fee, funding, latency_ms, expected_price, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fill.fill_id, fill.order_id, fill.price, fill.quantity,
                fill.fee, fill.funding, fill.latency_ms, fill.expected_price, _now_text(),
            ),
        )
        self.connection.commit()

    def _known_fill_ids(self, order_id: str) -> set[str]:
        rows = self.connection.execute(
            "SELECT fill_id FROM fills WHERE order_id=?", (order_id,)
        ).fetchall()
        known: set[str] = set()
        for row in rows:
            known.add(str(row["fill_id"]))
        return known

    def _order_intent(self, order_id: str) -> str:
        row = self.connection.execute(
            "SELECT intent FROM orders WHERE order_id=?", (order_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown order: {order_id}")
        return str(row["intent"])

    def _linked_position(self, exit_order_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT position_id FROM orders WHERE order_id=?", (exit_order_id,)
        ).fetchone()
        if row is None or row["position_id"] is None:
            return None
        return self.get_position(str(row["position_id"]))

    def _position_for_entry_order(self, entry_order_id: str, symbol: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM positions WHERE entry_order_id=? AND closed_at_ms IS NULL ORDER BY rowid DESC LIMIT 1",
            (entry_order_id,),
        ).fetchone()
        if row is None:
            return None
        result: dict[str, Any] = {}
        for key in row.keys():
            result[key] = row[key]
        return result

    def _open_position(self, order: Order, fill: Fill, position_id: str, timestamp_ms: int) -> dict[str, Any]:
        opened = int(timestamp_ms) if int(timestamp_ms) > 0 else _now_ms()
        slip = fill.slippage_bps()
        self.connection.execute(
            """INSERT INTO positions
            (position_id, symbol, side, entry_order_id, quantity, entry_price,
             stop, target, fees, funding, filled_quantity, exit_filled_quantity,
             realized_pnl, mfe, mae, slippage_sum, slippage_samples,
             latency_total, latency_samples, opened_at_ms, closed_at_ms,
             amendments, reconcile_state, mark_price, price_path_json)
            VALUES (?, ?, ?, ?, ?, ?, 0.0, 0.0, ?, ?, ?, 0.0, 0.0, 0.0, 0.0, ?, ?, ?, ?, ?, NULL, 0, 'CLEAN', ?, ?)""",
            (
                position_id, order.symbol, order.side, order.order_id, order.quantity,
                fill.price, fill.fee, fill.funding, fill.quantity,
                slip or 0.0, 1 if slip is not None else 0,
                fill.latency_ms or 0, 1 if fill.latency_ms is not None else 0,
                opened, fill.price, json.dumps([fill.price]),
            ),
        )
        self.connection.execute(
            "UPDATE orders SET position_id=? WHERE order_id=?", (position_id, order.order_id)
        )
        self.connection.commit()
        return self.get_position(position_id)

    def _extend_position(self, position_id: str, fill: Fill, timestamp_ms: int) -> None:
        row = self.get_position(position_id)
        slip = fill.slippage_bps()
        path = json.loads(str(row["price_path_json"]))
        path.append(fill.price)
        mfe, mae = excursion(str(row["side"]), float(row["entry_price"]), path)
        self.connection.execute(
            """UPDATE positions SET filled_quantity=filled_quantity+?, fees=fees+?,
            funding=funding+?, slippage_sum=slippage_sum+?, slippage_samples=slippage_samples+?,
            latency_total=latency_total+?, latency_samples=latency_samples+?,
            mfe=?, mae=?, mark_price=?, price_path_json=? WHERE position_id=?""",
            (
                fill.quantity, fill.fee, fill.funding, slip or 0.0,
                1 if slip is not None else 0,
                fill.latency_ms or 0, 1 if fill.latency_ms is not None else 0,
                mfe, mae, fill.price, json.dumps(path), position_id,
            ),
        )
        self.connection.commit()

    def _apply_exit_fill(
        self, position_id: str, exit_order: Order, fill: Fill, timestamp_ms: int
    ) -> str | None:
        row = self.get_position(position_id)
        if str(row["symbol"]) != exit_order.symbol:
            raise ValueError("exit symbol does not match position")
        leg_pnl = position_pnl(str(row["side"]), float(row["entry_price"]), fill.price, fill.quantity)
        slip = fill.slippage_bps()
        path = json.loads(str(row["price_path_json"]))
        path.append(fill.price)
        mfe, mae = excursion(str(row["side"]), float(row["entry_price"]), path)
        self.connection.execute(
            """UPDATE positions SET exit_filled_quantity=exit_filled_quantity+?,
            realized_pnl=realized_pnl+?, fees=fees+?, funding=funding+?,
            slippage_sum=slippage_sum+?, slippage_samples=slippage_samples+?,
            latency_total=latency_total+?, latency_samples=latency_samples+?,
            mfe=?, mae=?, mark_price=?, price_path_json=? WHERE position_id=?""",
            (
                fill.quantity, leg_pnl, fill.fee, fill.funding, slip or 0.0,
                1 if slip is not None else 0,
                fill.latency_ms or 0, 1 if fill.latency_ms is not None else 0,
                mfe, mae, fill.price, json.dumps(path), position_id,
            ),
        )
        self.connection.commit()
        updated = self.get_position(position_id)
        if float(updated["exit_filled_quantity"]) + 1e-9 < float(updated["filled_quantity"]):
            return None
        closed_at = int(timestamp_ms) if int(timestamp_ms) > 0 else _now_ms()
        self.connection.execute(
            "UPDATE positions SET closed_at_ms=? WHERE position_id=?", (closed_at, position_id)
        )
        self.connection.commit()
        final = self.get_position(position_id)
        trade_id = "trade_" + str(uuid4()).replace("-", "")[:16]
        avg_slip = None
        if int(final["slippage_samples"]) > 0:
            avg_slip = float(final["slippage_sum"]) / float(final["slippage_samples"])
        avg_lat = None
        if int(final["latency_samples"]) > 0:
            avg_lat = float(final["latency_total"]) / float(final["latency_samples"])
        amendments = int(final["amendments"])
        exit_amend = self._load_order(exit_order.order_id).amendments
        amendments = amendments + exit_amend
        self.connection.execute(
            """INSERT INTO trades
            (trade_id, position_id, entry_order_id, exit_order_id, decision_id,
             execution_id, symbol, side, quantity, entry_price, exit_price,
             realized_pnl, fees, funding, mfe, mae, duration_ms,
             avg_slippage, avg_latency, amendments, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade_id, position_id, str(final["entry_order_id"]), exit_order.order_id,
                exit_order.decision_id, exit_order.execution_id, str(final["symbol"]),
                str(final["side"]), float(final["filled_quantity"]), float(final["entry_price"]),
                fill.price, float(final["realized_pnl"]), float(final["fees"]), float(final["funding"]),
                float(final["mfe"]), float(final["mae"]),
                closed_at - int(final["opened_at_ms"]), avg_slip, avg_lat, amendments, _now_text(),
            ),
        )
        self.connection.commit()
        self._mirror_trade(trade_id)
        return trade_id

    def _mirror_fill_into_position(self, order: Order, fill: Fill) -> None:
        intent = self._order_intent(order.order_id)
        if intent == "ENTRY":
            position = self._position_for_entry_order(order.order_id, order.symbol)
            if position is None:
                position_id = "pos_" + str(uuid4()).replace("-", "")[:16]
                created = self._open_position(order, fill, position_id, 0)
                self._mirror_position(created)
            else:
                self._extend_position(position["position_id"], fill, 0)
        else:
            linked = self._linked_position(order.order_id)
            if linked is not None:
                self._apply_exit_fill(linked["position_id"], order, fill, 0)

    def _flag_reconciled(self, symbol: str) -> None:
        self.connection.execute(
            "UPDATE positions SET reconcile_state='RECONCILED' WHERE symbol=? AND closed_at_ms IS NULL",
            (str(symbol),),
        )
        self.connection.commit()

    @staticmethod
    def _exchange_key(entry: dict[str, Any]) -> str | None:
        for field in ("order_id", "client_order_id", "execution_id"):
            value = entry.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    # -- memory mirroring (uses existing Module 10 API only) --
    def _mirror_order(self, order: Order) -> None:
        if self.memory is None or order.order_id in self._mirrored_orders:
            return
        self.memory.record_order(
            order_id=order.order_id,
            execution_id=order.execution_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            status=order.state,
            payload={"decision_id": order.decision_id, "order_type": order.order_type},
        )
        self._mirrored_orders.add(order.order_id)

    def _mirror_position(self, position: dict[str, Any]) -> None:
        if self.memory is None or str(position["position_id"]) in self._mirrored_positions:
            return
        self.memory.record_position(
            position_id=str(position["position_id"]),
            order_id=str(position["entry_order_id"]),
            symbol=str(position["symbol"]),
            quantity=float(position["quantity"]),
            payload={"side": str(position["side"]), "entry_price": float(position["entry_price"])},
        )
        self._mirrored_positions.add(str(position["position_id"]))

    def _mirror_trade(self, trade_id: str) -> None:
        if self.memory is None or trade_id in self._mirrored_trades:
            return
        row = self.connection.execute(
            "SELECT * FROM trades WHERE trade_id=?", (trade_id,)
        ).fetchone()
        if row is None:
            return
        self.memory.record_trade(
            trade_id=trade_id,
            position_id=str(row["position_id"]),
            symbol=str(row["symbol"]),
            pnl=float(row["realized_pnl"]) - float(row["fees"]) - float(row["funding"]),
            payload={
                "entry_order_id": str(row["entry_order_id"]),
                "exit_order_id": str(row["exit_order_id"]),
                "decision_id": str(row["decision_id"]),
                "execution_id": str(row["execution_id"]),
                "entry_price": float(row["entry_price"]),
                "exit_price": float(row["exit_price"]),
                "mfe": float(row["mfe"]),
                "mae": float(row["mae"]),
                "duration_ms": int(row["duration_ms"]),
            },
        )
        self._mirrored_trades.add(trade_id)


def _now_text() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> int:
    from datetime import datetime, timezone

    return int(datetime.now(timezone.utc).timestamp() * 1000)
