"""Synchronous trading pipeline: one market event through the whole stack.

Why synchronous steps: async workers (workers.py) move data, but every stage
transition happens here in plain call order — market → context → strategy →
decision → risk → execution → venue → lifecycle → learning → research — so
tests can drive the exact production path without clocks or networks. HOLD
cycles persist nothing to the audit backbone (no edge link exists to join
on); actionable flows persist the full ID chain before submission.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

from candidate_generation.generator import CandidateGenerator
from candidate_generation.hypothesis_menu import HypothesisMenu
from candidate_generation.review_queue import ReviewQueue
from edge_validation.registry import EdgeValidationRegistry
from execution.n8n_client import ExecutionConfig, build_request
from execution.order_manager import ExecutionOrderManager
from hermes.decision import decide
from hermes.observer import HermesObserver
from learning.lesson_engine import LessonEngine
from learning.trade_analyzer import analyze_trade
from memory.repository import MemoryRepository
from models.execution import Fill
from monitoring.positions import LifecycleTracker
from risk.engine import RiskEngine
from runtime.config import RuntimeConfig
from runtime.paper_venue import PaperN8nServer, make_paper_sender
from strategies.base import LoadedStrategy
from strategies.production_versions import ProductionVersionStore
from strategies.proposal import build_proposal, describe_context_evidence
from strategies.registry import load_production_strategy


SignalFn = Callable[[Any, LoadedStrategy], dict[str, Any]]


class PipelineBlockedError(RuntimeError):
    """Raised when production activation is attempted without a PASS gate."""


class HermesPipeline:
    """Wired modules with explicit, auditable stage transitions."""

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        observer: HermesObserver | None = None,
        registry: EdgeValidationRegistry | None = None,
        versions: ProductionVersionStore | None = None,
        reviews: ReviewQueue | None = None,
        risk_engine: RiskEngine | None = None,
        exec_manager: ExecutionOrderManager | None = None,
        tracker: LifecycleTracker | None = None,
        memory: MemoryRepository | None = None,
        lessons: LessonEngine | None = None,
        generator: CandidateGenerator | None = None,
        venue: PaperN8nServer | None = None,
        allow_test_signals: bool = False,
        webhook_secret: str = "paper-webhook-secret",
    ) -> None:
        self.config = config
        self.allow_test_signals = bool(allow_test_signals)
        paths = config.store_paths()
        self.observer = observer if observer is not None else HermesObserver(symbols=list(config.symbols))
        self.registry = registry
        if self.registry is None:
            self.registry = EdgeValidationRegistry(paths["edge"], paths["edge_report"])
        self.versions = versions
        if self.versions is None:
            self.versions = ProductionVersionStore(paths["versions"])
        self.reviews = reviews
        if self.reviews is None:
            self.reviews = ReviewQueue(paths["reviews"])
        self.risk_engine = risk_engine if risk_engine is not None else RiskEngine()
        self.exec_manager = exec_manager
        if self.exec_manager is None:
            self.exec_manager = ExecutionOrderManager(paths["execution"])
        self.memory = memory
        if self.memory is None:
            self.memory = MemoryRepository(paths["memory"])
        self.tracker = tracker
        if self.tracker is None:
            self.tracker = LifecycleTracker(paths["lifecycle"], memory=self.memory)
        self.lessons = lessons
        if self.lessons is None:
            self.lessons = LessonEngine(paths["lessons"])
        self.generator = generator
        if self.generator is None:
            self.generator = CandidateGenerator(paths["candidates"], menu=HypothesisMenu())
        self.venue = venue if venue is not None else PaperN8nServer()
        self.exec_config = ExecutionConfig(
            webhook_url="http://127.0.0.1:9/n8n-paper",
            webhook_secret=webhook_secret,
            environment="paper" if config.environment == "paper" else "production",
        )
        self._webhook_secret = webhook_secret
        self.signals: dict[str, SignalFn] = {}
        self.signal_test_only: dict[str, bool] = {}
        self._last_event_ms: dict[str, int] = {}
        self.account = {
            "equity": float(config.starting_equity),
            "peak": float(config.starting_equity),
            "daily": 0.0,
        }
        self.counters = {"contexts": 0, "decisions": 0, "holds": 0, "approved": 0, "submitted": 0, "trades": 0}

    def close(self) -> None:
        self.registry.close()
        self.versions.close()
        self.reviews.close()
        self.exec_manager.close()
        self.tracker.close()
        self.memory.close()
        self.lessons.close()
        self.generator.close()

    # -- strategy runner (the missing callback; empty means safely idle) --
    def register_signal(self, strategy_id: str, fn: SignalFn, *, test_only: bool = False) -> None:
        name = str(strategy_id).strip()
        if not name:
            raise ValueError("strategy_id must be non-empty")
        if test_only and name.startswith("test_") is False:
            raise ValueError("test signals must use a test_ strategy_id prefix")
        if test_only is False and name.startswith("test_"):
            raise ValueError("test_ strategies must be registered test-only")
        self.signals[name] = fn
        self.signal_test_only[name] = bool(test_only)

    def assert_no_test_signals(self) -> None:
        """Production boot guard: fixtures can never load outside tests."""
        for name in self.signal_test_only:
            if self.signal_test_only[name] is True:
                raise PipelineBlockedError("test signal registered: %s" % name)

    def approved_strategies(self) -> list[tuple[str, LoadedStrategy]]:
        """Currently approved immutable versions with a live PASS each."""
        found: list[tuple[str, LoadedStrategy]] = []
        seen: list[str] = []
        for version in self.versions.list_versions():
            strategy_id = str(version.strategy_id)
            already = False
            for known in seen:
                if known == strategy_id:
                    already = True
            if already:
                continue
            seen.append(strategy_id)
            try:
                loaded = load_production_strategy(strategy_id, self.registry, self.versions)
            except Exception:
                continue
            found.append((strategy_id, loaded))
        return found

    def proposals_for(self, context: Any) -> list[Any]:
        """Run every approved signal; a failing signal is skipped, never fatal."""
        proposals: list[Any] = []
        for strategy_id, loaded in self.approved_strategies():
            fn = self.signals.get(strategy_id)
            if fn is None:
                continue
            try:
                spec = fn(context, loaded)
            except Exception:
                continue
            try:
                proposals.append(
                    build_proposal(
                        loaded,
                        context,
                        action=spec["action"],
                        confidence=spec["confidence"],
                        evidence=spec.get("evidence") or describe_context_evidence(context),
                        horizon=spec.get("horizon", "15m"),
                    )
                )
            except Exception:
                continue
        return proposals

    # -- market → context → strategy → decision → risk --
    def step_market(
        self,
        symbol: str,
        snapshot: Mapping[str, Any] | None,
        event_time_ms: int | None,
        *,
        now_ms: int,
        breadth: Mapping[str, Any] | None = None,
        health_entries: list[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Process one market event; malformed input is skipped, never fatal."""
        token = str(symbol).strip().upper()
        if not token or snapshot is None:
            return {"skipped": True, "reason": "malformed event"}
        if event_time_ms is not None:
            last = self._last_event_ms.get(token)
            if last is not None and int(event_time_ms) == last:
                return {"skipped": True, "reason": "duplicate event"}
            self._last_event_ms[token] = int(event_time_ms)
        emitted = self.observer.refresh_once(
            {token: snapshot},
            {token: event_time_ms},
            breadth=breadth,
            health_entries=health_entries,
            now_ms=now_ms,
        )
        results: list[dict[str, Any]] = []
        for context in emitted:
            results.append(self._process_context(context, now_ms))
        return {"skipped": False, "results": results}

    def decide_for(self, context: Any, proposals: list[Any], now_ms: int) -> tuple[Any, Any]:
        """Deterministic strategy-to-decision step shared by sync and workers."""
        moment = datetime.fromtimestamp(float(now_ms) / 1000.0, tz=timezone.utc)
        return decide(str(context.symbol), context, proposals, timestamp=moment)

    def _process_context(self, context: Any, now_ms: int) -> dict[str, Any]:
        self.counters["contexts"] = self.counters["contexts"] + 1
        proposals = self.proposals_for(context)
        decision, record = self.decide_for(context, proposals, now_ms)
        self.counters["decisions"] = self.counters["decisions"] + 1
        outcome: dict[str, Any] = {}
        outcome["context"] = context
        outcome["proposals"] = proposals
        outcome["decision"] = decision
        outcome["evidence_record"] = record
        outcome["risk"] = None
        outcome["request"] = None
        if decision.action == "HOLD" or len(proposals) == 0:
            # Fail-closed persistence: with no edge-linked proposal there is
            # nothing the audit backbone can join on, so HOLD cycles persist
            # nothing rather than orphan rows.
            self.counters["holds"] = self.counters["holds"] + 1
            return outcome
        account = self._account_state(str(context.symbol))
        risk = self.risk_engine.evaluate(
            decision,
            context,
            equity=account["equity"],
            peak_equity=account["peak"],
            daily_realized_pnl=account["daily"],
            open_notional=account["open_notional"],
            symbol_exposure=account["symbol_exposure"],
            open_positions=account["open_positions"],
            now_ms=now_ms,
        )
        outcome["risk"] = risk
        if risk.status != "APPROVED":
            return outcome
        self.counters["approved"] = self.counters["approved"] + 1
        self._persist_chain(context, proposals, record, decision, risk)
        moment = datetime.fromtimestamp(float(now_ms) / 1000.0, tz=timezone.utc)
        request = build_request(risk, symbol=str(context.symbol), side=decision.action, now=moment)
        outcome["request"] = request
        return outcome

    # -- execution → venue --
    def submit(self, request: Any, risk: Any, *, now_ms: int) -> dict[str, Any]:
        """Submit through the n8n boundary into the paper venue, then track."""
        moment = datetime.fromtimestamp(float(now_ms) / 1000.0, tz=timezone.utc)
        sender = make_paper_sender(self.venue, self._webhook_secret, now_ms)
        outcome = self.exec_manager.submit_once(
            request,
            config=self.exec_config,
            sender=sender,
            now=moment,
            kill_switch_active=self.risk_engine.is_halted(),
            risk_decision=risk,
        )
        try:
            self.memory.get("executions", request.execution_id)
        except KeyError:
            self.memory.record_execution(
                execution_id=request.execution_id,
                risk_decision_id=request.risk_decision_id,
                status=str(outcome.get("state", "SUBMITTED")),
                payload={"idempotency_key": request.idempotency_key},
            )
        if outcome.get("duplicate_suppressed") is not True:
            self.counters["submitted"] = self.counters["submitted"] + 1
        return outcome

    def on_venue_fills(self, request: Any, *, timestamp_ms: int = 0) -> dict[str, Any]:
        """Route paper fills into the lifecycle; closed trades trigger learning."""
        order = self.tracker.place_order(
            execution_id=request.execution_id,
            decision_id=self._decision_for_request(request),
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            intent="ENTRY",
        )
        fills = self._paper_fills_for(request, order.order_id)
        closed_trade_id: str | None = None
        for fill in fills:
            result = self.tracker.apply_fill(fill, timestamp_ms=timestamp_ms)
            if result.get("closed_trade_id") is not None:
                closed_trade_id = str(result["closed_trade_id"])
        outcome: dict[str, Any] = {}
        outcome["order_id"] = order.order_id
        outcome["fills"] = len(fills)
        outcome["closed_trade_id"] = closed_trade_id
        outcome["learning"] = None
        if closed_trade_id is not None:
            self.counters["trades"] = self.counters["trades"] + 1
            self._settle_account(closed_trade_id)
            outcome["learning"] = self.learn_from_trade(closed_trade_id)
        return outcome

    def close_position(
        self, symbol: str, *, price: float,
        quantity: float, timestamp_ms: int = 0,
    ) -> dict[str, Any]:
        """Explicit lifecycle exit (CLOSE intent); never weakens risk.

        Why no new execution id: the exit fulfills the entry's lifecycle, so
        it carries the entry's execution/decision linkage. Minting fresh
        risk/execution rows for a lifecycle-managed exit would fabricate
        backbone history the gate never produced.
        """
        holding = self.tracker.open_position(symbol)
        if holding is None:
            raise ValueError("no open position on %s" % symbol)
        entry_order_id = str(holding["entry_order_id"])
        entry_row = self.tracker.connection.execute(
            "SELECT execution_id, decision_id FROM orders WHERE order_id=?", (entry_order_id,)
        ).fetchone()
        if entry_row is None:
            raise KeyError("entry order missing for position on %s" % symbol)
        order = self.tracker.place_order(
            execution_id=str(entry_row["execution_id"]),
            decision_id=str(entry_row["decision_id"]),
            symbol=symbol,
            side=self._exit_side(symbol),
            quantity=quantity,
            intent="CLOSE",
        )
        result = self.tracker.apply_fill(
            Fill(
                fill_id="fill_" + str(uuid4()).replace("-", "")[:16],
                order_id=order.order_id,
                price=float(price),
                quantity=float(quantity),
            ),
            timestamp_ms=timestamp_ms,
        )
        outcome: dict[str, Any] = {}
        outcome["order_id"] = order.order_id
        outcome["closed_trade_id"] = result.get("closed_trade_id")
        outcome["learning"] = None
        if result.get("closed_trade_id") is not None:
            self.counters["trades"] = self.counters["trades"] + 1
            self._settle_account(str(result["closed_trade_id"]))
            outcome["learning"] = self.learn_from_trade(str(result["closed_trade_id"]))
        return outcome

    # -- learning → research (propose only; humans validate) --
    def learn_from_trade(self, trade_id: str) -> dict[str, Any]:
        """Analyze a closed trade and bank a lesson candidate if actionable."""
        chain = self.tracker.get_chain(trade_id)
        trade = chain["trade"]
        closed = {
            "trade_id": trade["trade_id"],
            "quantity": trade["quantity"],
            "realized_pnl": trade["realized_pnl"],
            "mfe": trade["mfe"],
            "mae": trade["mae"],
            "avg_slippage": trade.get("avg_slippage"),
        }
        analysis = analyze_trade(
            closed,
            context_valid=True,
            gate_record_ok=self._gate_ok_for_trade(trade_id),
            approved_quantity=float(trade["quantity"]),
            regime_fit=True,
        )
        lesson_id = self.lessons.propose(analysis)
        self._mirror_learning(trade_id, analysis, lesson_id)
        return {"analysis": analysis, "lesson_id": lesson_id}

    def _mirror_learning(self, trade_id: str, analysis: Any, lesson_id: str | None) -> None:
        """Mirror analysis, lesson, and version rows so the backbone resolves.

        NORMAL trades bank no lesson by design; the backbone then completes
        through the strategy version matched on the edge record instead.
        """
        try:
            self.memory.get("trade_analysis", str(analysis.analysis_id))
            return
        except KeyError:
            pass
        self.memory.record_analysis(
            analysis_id=str(analysis.analysis_id),
            trade_id=trade_id,
            diagnosis="%s: %s" % (str(analysis.category), str(analysis.recommended_action)),
            payload={"category": str(analysis.category), "actionable": bool(analysis.actionable)},
        )
        strategy_id = self._strategy_for_trade(trade_id)
        if lesson_id is not None:
            try:
                self.memory.get("lessons", lesson_id)
            except KeyError:
                self.memory.record_lesson(
                    lesson_id=lesson_id,
                    analysis_id=str(analysis.analysis_id),
                    status="CANDIDATE",
                    payload={"category": str(analysis.category)},
                )
        if strategy_id is None:
            return
        active = self.versions.get_active_version(strategy_id)
        if active is None:
            return
        try:
            self.memory.get("strategy_versions", str(active.version_id))
            return
        except KeyError:
            pass
        self.memory.record_strategy_version(
            version_id=str(active.version_id),
            strategy_id=strategy_id,
            edge_validation_record_id=str(active.edge_validation_record_id),
            lesson_id=lesson_id,
            approver=str(active.approver),
            payload={"rationale": str(active.rationale)},
        )

    def _strategy_for_trade(self, trade_id: str) -> str | None:
        try:
            chain = self.tracker.get_chain(trade_id)
            order = self.memory.get("orders", chain["order_id"])
            execution = self.memory.get("executions", str(order["execution_id"]))
            risk = self.memory.get("risk_decisions", str(execution["risk_decision_id"]))
            decision_id = str(risk["decision_id"])
        except (KeyError, TypeError, ValueError):
            return None
        rows = self.memory.connection.execute(
            "SELECT strategy_id FROM strategy_proposals WHERE decision_id=? LIMIT 1",
            (decision_id,),
        ).fetchall()
        if len(rows) == 0:
            return None
        return str(rows[0]["strategy_id"])

    def research_step(
        self,
        lesson_id: str,
        canned_response: Mapping[str, Any] | None,
        *,
        holdout_period: tuple[Any, Any],
        cost_assumptions: Mapping[str, Any],
        strategy_id: str,
    ) -> dict[str, Any]:
        """Validated lesson → hypothesis → gate preregistration → review inbox.

        Canned responses are test-only; live runs call the real provider via
        run_once. Approval never happens here — the review queue waits.
        """
        lesson = self.lessons.get(lesson_id)
        if str(lesson.get("status", "")) != "VALIDATED":
            raise ValueError("lesson %s is not VALIDATED" % lesson_id)
        if canned_response is not None:
            hypothesis = self.generator.generate_from_response(
                canned_response, provider_used="test-fixture"
            )
        else:
            hypothesis = self.generator.run_once(
                None,
                self.exec_config.webhook_url,
                "",
                "operator-configured",
            )
        if hypothesis is None:
            return {"preregistered": False, "reason": "malformed provider output"}
        if hypothesis.excluded_because is not None:
            return {"preregistered": False, "reason": str(hypothesis.excluded_because)}
        record_id = self.generator.preregister(
            hypothesis,
            self.registry,
            holdout_period=holdout_period,
            cost_and_tax_assumptions=dict(cost_assumptions),
            strategy_id=strategy_id,
        )
        self.reviews.submit_for_review(
            record_id, strategy_id, "PENDING", source="AI_RESEARCH",
            candidate_id=hypothesis.candidate_id,
            hypothesis_id=hypothesis.hypothesis_id,
            signal_class=hypothesis.signal_class,
        )
        return {"preregistered": True, "record_id": record_id, "candidate_id": hypothesis.candidate_id}

    # -- kill switch, traceability, account --
    def trip_kill(self, reason: str) -> None:
        self.risk_engine.activate_kill_switch(reason)

    def trace_trade(self, trade_id: str) -> dict[str, Any]:
        """Combined lifecycle chain plus Module 10 backbone reconstruction.

        NORMAL trades bank no lesson by design, so the backbone is partial
        through the lesson leg for those — reported honestly via complete.
        """
        from memory.repository import TraceNotFoundError

        chain = self.tracker.get_chain(trade_id)
        try:
            backbone = self.memory.trace(trade_id)
        except TraceNotFoundError as exc:
            return {"lifecycle": chain, "backbone": None, "complete": False, "gap": str(exc)}
        return {"lifecycle": chain, "backbone": backbone, "complete": True, "gap": None}

    def _account_state(self, symbol: str) -> dict[str, float]:
        holding = self.tracker.open_position(symbol)
        exposure = 0.0
        count = 0
        if holding is not None:
            exposure = float(holding["filled_quantity"]) * float(holding["entry_price"])
            count = 1
        rows = self.tracker.connection.execute("SELECT COUNT(*) AS n FROM positions WHERE closed_at_ms IS NULL").fetchone()
        total_open = int(rows["n"]) if rows is not None else 0
        return {
            "equity": float(self.account["equity"]),
            "peak": float(self.account["peak"]),
            "daily": float(self.account["daily"]),
            "open_notional": exposure,
            "symbol_exposure": exposure,
            "open_positions": total_open,
        }

    def _settle_account(self, trade_id: str) -> None:
        row = self.tracker.connection.execute(
            "SELECT * FROM trades WHERE trade_id=?", (trade_id,)
        ).fetchone()
        if row is None:
            return
        net = float(row["realized_pnl"]) - float(row["fees"]) - float(row["funding"])
        self.account["equity"] = float(self.account["equity"]) + net
        self.account["daily"] = float(self.account["daily"]) + net
        if float(self.account["equity"]) > float(self.account["peak"]):
            self.account["peak"] = float(self.account["equity"])
        self.memory.record_metric(
            metric_id="acct_" + str(uuid4()).replace("-", "")[:16],
            scope="account",
            payload={"equity": self.account["equity"], "daily": self.account["daily"]},
        )

    def persist_pre_risk(self, context: Any, proposals: list[Any], record: Any, decision: Any) -> str:
        """Persist snapshot, edge mirror, decision, proposals, and evidence.

        Split from risk persistence so queued workers can commit the decision
        chain before the risk stage runs. Only called for actionable flows
        with edge-linked proposals (see _process_context).
        """
        snapshot_id = "snap_" + str(uuid4()).replace("-", "")[:16]
        self.memory.record_market_snapshot(
            snapshot_id=snapshot_id,
            symbol=str(context.symbol),
            event_time_ms=int(context.timestamp_ms),
            payload={"valid": bool(context.valid)},
        )
        edge_id = str(proposals[0].edge_validation_record_id)
        try:
            self.memory.get("edge_validation_records", edge_id)
        except KeyError:
            self.memory.record_edge_validation(
                record_id=edge_id,
                strategy_id=str(proposals[0].strategy_id),
                strategy_family=str(proposals[0].strategy_id),
                verdict="PASS",
                snapshot_id=snapshot_id,
                payload={"source": "gate-ledger-mirror"},
            )
        self.memory.record_decision(
            decision_id=str(decision.decision_id),
            symbol=str(decision.symbol),
            action=str(decision.action),
            confidence=float(decision.confidence),
            market_snapshot_id=snapshot_id,
            edge_validation_record_id=edge_id,
            payload={"strategy_version_id": str(decision.strategy_version_id)},
        )
        for proposal in proposals:
            self.memory.record_proposal(
                proposal_id=str(proposal.proposal_id),
                decision_id=str(decision.decision_id),
                strategy_id=str(proposal.strategy_id),
                action=str(proposal.action),
                edge_validation_record_id=str(proposal.edge_validation_record_id),
                payload={"confidence": float(proposal.confidence)},
            )
        index = 0
        for entry in record.evidence:
            self.memory.record_evidence(
                evidence_id="evi_%s_%d" % (str(decision.decision_id)[:8], index),
                decision_id=str(decision.decision_id),
                payload=dict(entry),
                proposal_id=None,
            )
            index = index + 1
        return snapshot_id

    def persist_risk_decision(self, risk: Any, decision_id: str) -> None:
        """Persist one risk verdict; the decision row must already exist."""
        self.memory.record_risk(
            risk_decision_id=str(risk.risk_decision_id),
            decision_id=str(decision_id),
            status=str(risk.status),
            approved_quantity=float(risk.approved_quantity),
            payload={"stop": float(risk.stop), "target": float(risk.target)},
        )

    def _persist_chain(self, context: Any, proposals: list[Any], record: Any, decision: Any, risk: Any) -> None:
        self.persist_pre_risk(context, proposals, record, decision)
        self.persist_risk_decision(risk, str(decision.decision_id))

    def _paper_fills_for(self, request: Any, order_id: str) -> list[Fill]:
        fills: list[Fill] = []
        for paper_fill in self.venue.paper.fills:
            if paper_fill.order_id != request.execution_id:
                continue
            if float(paper_fill.filled_quantity) <= 0:
                continue
            fills.append(
                Fill(
                    fill_id="fill_" + str(uuid4()).replace("-", "")[:16],
                    order_id=order_id,
                    price=float(paper_fill.fill_price),
                    quantity=float(paper_fill.filled_quantity),
                    fee=float(paper_fill.fee_paid),
                    funding=0.0,
                )
            )
        return fills

    def _gate_ok_for_trade(self, trade_id: str) -> bool | None:
        """Resolve whether the trade's strategy holds a current PASS record.

        Walks memory from the trade's entry proposal to its edge record, then
        asks the live gate. Unknown plumbing returns None (fail toward DATA).
        """
        try:
            chain = self.tracker.get_chain(trade_id)
            entry_order = chain["order_id"]
            order = self.memory.get("orders", entry_order)
            execution = self.memory.get("executions", str(order["execution_id"]))
            risk = self.memory.get("risk_decisions", str(execution["risk_decision_id"]))
            decision_id = str(risk["decision_id"])
        except (KeyError, TypeError, ValueError):
            return None
        rows = self.memory.connection.execute(
            "SELECT strategy_id FROM strategy_proposals WHERE decision_id=? LIMIT 1",
            (decision_id,),
        ).fetchall()
        if len(rows) == 0:
            return None
        try:
            return self.registry.get_verdict(str(rows[0]["strategy_id"])) == "PASS"
        except Exception:
            return None

    def _decision_for_request(self, request: Any) -> str:
        row = self.memory.connection.execute(
            "SELECT decision_id FROM risk_decisions WHERE risk_decision_id=?",
            (str(request.risk_decision_id),),
        ).fetchone()
        if row is None:
            return "dec_unknown"
        return str(row["decision_id"])

    def _exit_side(self, symbol: str) -> str:
        holding = self.tracker.open_position(symbol)
        if holding is None:
            raise ValueError("no open position on %s" % symbol)
        if str(holding["side"]).upper() == "BUY":
            return "SELL"
        return "BUY"
