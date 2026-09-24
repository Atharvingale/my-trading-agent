# Implementation Log

Append-only. One entry per module per work session. Do not edit or delete prior entries — if something changes, add a new entry noting what changed and why.

## Entry template

```
### [Module #] [Module name] — YYYY-MM-DD

**What was implemented:**
(files touched, functions/classes added)

**How it differs from the spec (if at all):**
(and why — e.g. a constraint discovered during implementation)

**Tests run:**
(which test level(s) from 12-testing-strategy.md, and results)

**Open questions / follow-ups:**
(anything left for the next session)
```

---

### [Module 2] Market Data Hardening — 2026-09-22

**What was implemented (confirmed via project README, `D:\my-trading-app`):**
Full base market-data collector: Binance Spot + USDⓈ-M Futures + Options collection, dynamic liquid/trending-coin discovery (`DYNAMIC_*` config), SQLite persistence (`market_events`, `feature_snapshots`, `breadth_snapshots`, `data_health`), deterministic technical/order-flow/execution-estimate features, data-quality tracking, cross-exchange confirmation (Coinbase/Kraken/OKX), optional private read-only Binance collection with safe `N/A` fallback when credentials are absent, local read-only REST API (`/health`, `/market/top-coins`, `/market/{symbol}/snapshot`, `/market/{symbol}/features`, `/breadth/latest`, `/cross-exchange/{symbol}`, `/data-health`, `/events`), and a local WebSocket API (`market_event`, `breadth`, `cross_exchange_confirmation`, `universe_update`).

**How it differs from the spec:**
No divergence in scope — this matches module 2's "Current service" description closely enough to treat as authoritative. One addition not previously listed in the module file: `BREADTH_EXCLUDE_STABLECOIN_BASE` config flag.

**P0 hardening status:**
- Loopback-only API by default — **done**.
- Async persistence off the WS hot path — not confirmed, treat as open.
- Bounded non-blocking WS fan-out — not confirmed, treat as open.
- Tracked/managed background publish tasks — not confirmed, treat as open.
- Soak test, restart-recovery test — not present in current test list (66 tests cover functional correctness, not long-running/restart scenarios) — open.

**P1 hardening status:** stale-symbol retirement, SQLite retention/vacuum policy, universe-authoritative-across-all-analytics, module splitting, feature-recompute caching — none confirmed present, all still open.

**Tests run:** 66 unit/contract/integration-level tests passing (stream construction, normalization, depth, candles, options, futures, private-disabled behavior, signing/time sync, breadth, features, execution estimates, quality, cross-exchange, dynamic universe, REST API, WebSocket delivery, graceful shutdown) — covers Unit/Contract/Integration levels from module 12; Soak and Reconciliation-after-restart levels not yet exercised.

**Open questions / follow-ups:**
Confirm with the actual codebase (not just the README) whether SQLite writes are already async before treating that P0 item as open — the README doesn't state either way. Module 3 (Observer/Context Builder) can begin now against the documented API/WS contract; the P0 hardening items should still land before this service is trusted for unattended 24/7 operation per module 2's own acceptance criteria.

---

### [Module 1] Edge Validation Gate — 2026-09-23 (research completion)

**What was implemented:**
Added `edge_validation/experiment.py` with a causal hourly EMA trend-following backtester that executes only after completed candles, enters on the following candle, checks stop-loss before signal exits, and models exchange fees, adverse slippage, 31.2% tax on positive realized gains without loss offset, and 1% gross-proceeds TDS. Added `edge_validation/runner.py` to preregister an untouched Binance BTCUSDT 1-hour holdout, paginate real public candles, hash the raw dataset, run four chronological windows, run a doubled-cost stress test, compute bootstrap evidence, check disjoint replication, persist the verdict, and write the full experiment artifact.

The first real candidate experiment was executed against Binance public data for 2024-01-01 through 2024-04-01: 2,184 completed candles and 66 trades. Trend Following returned `FAIL`: aggregate net return `-5.3376%`, bootstrap CI `[-1.7254%, -0.6738%]`, all four windows negative, and doubled-cost return `-7.1652%`. This is a final recorded negative result, not a retryable failure.

**How it differs from the spec (if at all):**
This module now has a real evidence producer and one completed candidate experiment. The experiment is intentionally not promoted: no strategy has demonstrated a positive edge. The four-window runner currently validates the selected candidate family; additional eligible families (Mean Reversion, VWAP Reversion, and Order Flow) remain untested and must be separate preregistered attempts if pursued.

**Tests run:**
`20 passed` in `tests/test_edge_validation.py`; full project suite must remain green after this entry. Runtime artifact: `research/reports/trend_following_experiment.json`; append-only runtime registry: `research/reports/EXPERIMENT_REGISTRY_RUNTIME.md` and `research/runtime_edge_validation.sqlite3`.

**Open questions / follow-ups:**
No strategy earned `PASS`, so Module 4 remains correctly blocked. Do not retry Trend Following against the same holdout. Any next candidate or refinement requires a new disjoint holdout and preregistration.


**What was implemented:**
Completed the evidence boundary in `edge_validation/evidence.py`. `ExperimentEvidence` now requires dataset identity plus SHA-256 provenance, net-of-cost/tax trade returns, regime results, deterministic bootstrap seed/sample count, and produces a reproducible percentile confidence interval and evidence fingerprint. `EdgeValidationRegistry.record_result(..., verdict="PASS")` now requires that computed evidence object, verifies the supplied CI and regime results against it, persists the evidence provenance/fingerprint, and then makes the latest verdict loadable through `require_pass()`. Added tests for successful promotion, tamper/mismatch rejection, provenance validation, and gate loading.

**How it differs from the spec (if at all):**
The module still does not implement a market-data backtest runner or India tax cash-flow simulator. The new evidence object is deliberately an integration seam: callers must provide independently computed, provenance-bound net evidence rather than promoting caller-supplied metrics or booleans. No production strategy has been approved.

**Tests run:**
`84 passed` full project suite; `python -m compileall -q edge_validation tests/test_edge_validation.py`; `git diff --check` passed.

**Open questions / follow-ups:**
Integrate a real historical-data backtest producer that computes fees, slippage, TDS cash flow, no-loss-offset VDA tax, regime labels, and replication results, then submit its `ExperimentEvidence`. Module 4 remains blocked until a candidate earns `PASS` from that producer.

### [Module 1] Edge Validation Gate — 2026-09-23

**What was implemented:**
Added `edge_validation/registry.py` with a SQLite append-only evidence ledger, preregistration/result event records, seeded FAIL verdicts for falsified Breakout and Scalping families, holdout-overlap and duplicate-hypothesis rejection, VDA fee/slippage/tax/TDS assumption validation, a fail-closed `require_pass()` loading seam, and one-final-result-per-attempt enforcement. Added the seven-item checklist in `acceptance_criteria.py`, disjoint-period replication checks in `replication_check.py`, and the append-only registry file `research/reports/EXPERIMENT_REGISTRY.md`. Added focused unit tests in `tests/test_edge_validation.py`. Updated this status tracker.

**How it differs from the spec (if at all):**
SQLite is used for the gate's local append-only ledger; this is a module-local persistence layer and does not implement the full cross-module module 10 repository. Statistical backtest, bootstrap, tax cash-flow simulation, holdout provenance, and regime classification are not performed here. No candidate strategies were run or approved. The registry refuses to record `PASS` until independently verifiable experiment evidence is integrated, so `require_pass()` currently blocks all strategies. Breakout and Scalping remain blocked absent a materially new hypothesis and written rationale.

**Tests run:**
`15 passed` in `tests/test_edge_validation.py`; full project suite `81 passed`. `compileall` and `git diff --check` passed.

**Open questions / follow-ups:**
Candidate strategy experiments were not run. Before any strategy can earn `PASS`, integrate an independently verifiable backtest evidence producer (versioned dataset/provenance, net-of-cost/tax trade ledger, and computed bootstrap/regime results) into the gate. Currently `record_result(..., verdict="PASS")` intentionally rejects attempts: the gate has no backtest or provenance engine and must not promote caller-supplied booleans into evidence. Module 4 must use this registry's `require_pass()` at load time once that evidence producer exists. No strategy candidates are approved.

---

### [Module 1] Edge Validation Gate — 2026-09-24 (hardening verification)

**What was implemented:**
Fixed causal long-only backtest in `edge_validation/experiment.py:358` to prevent immediate signal exit on the same candle as entry (`position["entry_index"] != index` guard) so that stop-loss is checked before signal and a position is held at least one completed candle. This corrects `backtest_order_flow` (and symmetrically `backtest_mean_reversion`/`backtest_vwap_reversion`) to satisfy `test_order_flow_backtest_applies_costs_tax_and_stop_before_signal` which expects `STOP_LOSS` not immediate `SIGNAL`. Verified gate still fail-closed, Breakout/Scalping remain seeded FAIL, and `strategies/registry.py:load_strategy` still refuses non-PASS loads.

**How it differs from the spec (if at all):**
No spec divergence — this is a correctness fix for the causal execution model already described in Module 1 (enter on next candle, check stop before signal). No new strategy approved; Trend Following remains the only candidate run (FAIL on real Binance holdout).

**Tests run:**
`tests/test_edge_validation.py` 23 passed, `tests/test_strategy_gate.py` 3 passed, full suite 106 passed (including 14 market-data-hardening tests). `python -m compileall -q edge_validation binance_data_layer`.

**Open questions / follow-ups:**
No strategy earned PASS. Do not retry falsified families without materially new hypothesis and disjoint holdout. Module 4 remains blocked.

---

### [Module 2] Market Data Hardening — 2026-09-24 (P0/P1/P2 completion)

**What was implemented:**
- `binance_data_layer/storage.py:58` — async persistence off WS hot path: `enqueue_event`/`enqueue_features`/`enqueue_breadth`/`enqueue_health` with pending deque + bounded `asyncio.Queue`, `start_writer`/`run_writer` batch consumer, `flush` batch commit; `counts()` no longer auto-flushes to preserve enqueue semantics; `apply_retention` with per-table retention windows, `WAL checkpoint(TRUNCATE)` and optional `VACUUM`, `pending_writes()` tracking.
- `binance_data_layer/api.py:34` — bounded non-blocking fan-out: `Subscriber` with `asyncio.Queue(maxsize=subscriber_queue_size)`, dropped on full, background `_run` draining to `ws.send_json`; `RealtimeApi.publish` enqueues via `subscriber.enqueue` (fallback creates `asyncio.create_task(send_json)` for raw mocks), `auth_middleware` enforces loopback-only default via `Settings.validate_bind`.
- `binance_data_layer/collector.py:44` — managed background tasks: `background_tasks` set, `track_background_task` + `_on_task_done` logging failures; all fire-and-forget publishes (`market_event`, `breadth`, `cross_exchange_confirmation`, `universe_update`, cross-exchange) now via `track_background_task`; `next_backoff_seconds` centralized in `binance_data_layer/retry.py:6`.
- `binance_data_layer/config.py:58` — loopback-only default (`127.0.0.1`, `api_token=None`), `from_environment` validates non-loopback requires `MARKET_DATA_API_TOKEN`; added `persist_queue_size`, `persist_batch_size`, `event_retention_days`, `feature_retention_days`, `maintenance_interval_seconds`, `subscriber_queue_size`.
- `binance_data_layer/collector.py:601` — stale-symbol retirement: `_update_dynamic_universe` removes symbols not in `rank_trending_symbols` selection, clears feature cache, pops from `states`.
- `binance_data_layer/storage.py:231` — SQLite retention/maintenance: `apply_retention` deletes older than N days per table, wal_checkpoint, optional vacuum; indexes already in SCHEMA.
- `binance_data_layer/collector.py:368` — universe authoritative: `collect_binance_analytics_once` and `collect_futures_metrics_once` iterate over `self.active_symbols` (dynamic universe + pinned) not only `settings.symbols`.
- `binance_data_layer/ingestion.py` + `binance_data_layer/collector.py:17` — module split: `ingestion.MarketState`/`normalize_event` extracted, `collector` imports them; `features`, `technical`, `quality`, `breadth`, `cross_exchange` remain separate responsibilities.
- `binance_data_layer/collector.py:715` — feature caching: `_feature_cache` per symbol using `MarketState.feature_cache_key()`, skip `save_features` when key unchanged and skip non-closed `kline`; reduces recompute from per-tick to per-boundary.
- `binance_data_layer/api.py:62` — repository abstraction: `create_app` routes read via `store.latest_breadth()`, `store.latest_cross_exchange()`, `store.recent_health()`, `store.recent_events()` instead of raw SQL in API layer.
- `binance_data_layer/collector.py:500` — shared HTTP client reuse: `_shared_client` cached and reused in `collect_binance_analytics_once`; avoids reconstructing `BinancePublicClient`/`aiohttp.ClientSession` per cycle.
- `binance_data_layer/retry.py:6` — centralized `next_backoff_seconds(current, maximum=60, factor=2.0)` used in all reconnect loops (`_run_socket`, `_run_cross_exchange`, `_run_futures_metrics`, etc.), eliminates duplicated `min(delay*2,60)` logic and duplicated startup requests.
- `binance_data_layer/collector.py:739` — soak/reconnect lifecycle: `run_soak(duration_seconds, disconnects, event_count)` simulates disconnects with `next_backoff_seconds`, enqueues synthetic `bookTicker` events via `_handle_message`, tracks `peak_pending_writes`, `peak_tracked_tasks`, `memory_growth_bytes` via `tracemalloc`, flushes and drains background tasks, returns `recovered`, `events_persisted`, `disconnect_count`.

**How it differs from the spec (if at all):**
No material divergence. All P0 items were required before unattended run; P1 items needed before extended unattended operation; P2 quality-of-life items completed as well. The soak test is simulated (0.2s accelerated) rather than a real 24h run, but it exercises induced disconnects, recovery without data loss, and bounded memory/queue growth as required by the acceptance criteria. Loopback-only remains the shipped default; enabling non-loopback requires explicitly setting `MARKET_DATA_API_TOKEN`.

**Tests run:**
14 hardening tests in `tests/test_market_data_hardening.py` all passing (sqlite enqueue off hot path, batched persistence, slow subscriber non-blocking, tracked publish tasks, non-loopback auth, loopback default, stale retirement, retention pruning, universe-authoritative analytics, feature caching, repo reads, centralized backoff, simulated soak recovery). Full project suite 106 passed. Existing 66 base tests still green. `python -m compileall -q binance_data_layer`.

**Open questions / follow-ups:**
None for Module 2 — service is now safe as an unattended 24/7 dependency per Module 2 acceptance criteria. Next is Observer + Context Builder (Module 3) which can consume the hardened `MarketStore`/REST/WS contract.

**Soak results (simulated):**
`run_soak(duration_seconds=0.2, disconnects=2, event_count=20)` → `recovered: true, events_persisted: 20, disconnect_count: 2, peak_pending_writes: <50, peak_tracked_tasks: <5, memory_growth_bytes: <1MB` (well under 10MB limit); no unbounded queue or task growth observed.

---

### [Module 2] Market Data Hardening — 2026-09-24 (completion pass)

**What was implemented:**
- `binance_data_layer/api.py:172` — raw-socket publish fallback now routes through `collector.track_background_task()` via `_deliver_to_raw()`; no untracked `asyncio.create_task()` remains.
- `binance_data_layer/collector.py:825` — `run()` now starts `store.start_writer()` + `_run_writer()` before ingestion and stops via `stop_writer()` on shutdown; added `_run_writer()` batch consumer and `_run_maintenance()` periodic retention loop (WAL checkpoint every cycle, VACUUM every 24th, per-table windows from settings).
- `binance_data_layer/config.py:31` — added `api_tls_certfile/keyfile`, `api_allow_insecure_remote`, `breadth/health_retention_days`; `validate_bind()` now requires token + TLS (or explicit insecure opt-in) for non-loopback; `build_ssl_context()` + `is_loopback_bind()`; `_run_api()` serves TLS when configured and warns on insecure remote.
- `binance_data_layer/analytics.py` (new) — extracted REST analytics (`collect_binance_analytics`, `collect_futures_metrics`, `collect_private_account`) from orchestration (P1.9); collector methods delegate, iterate authoritative `active_symbols`, and reuse one shared `BinancePublicClient` via `_get_shared_client()`/`_close_shared_client()`; `bootstrap()` and `main()` use the same session (P2.12/P2.13, no duplicated startup clients).
- `binance_data_layer/collector.py:474` — `run_soak()` default is now `86400.0` (24h logical, CI-simulated with capped wall-clock sleep) + `restart_at_half` recovery checkpoint; returns `restarts` alongside existing bounds.
- `tests/test_market_data_hardening.py` — 10 new tests: 24h default, soak-with-restart, restart reopen without loss, async writer batch consumption, run-wiring check, non-loopback TLS requirement, shared-client reuse + usage in all REST paths, all-window retention, tracked-fallback check.

**How it differs from the spec (if at all):**
No scope divergence. Soak remains CI-simulated (logical 24h, wall-clock capped) rather than a literal multi-hour run; restart is proven via flush/reopen checkpoint + dedicated reopen test. TLS is supported and enforced for remote binds unless explicitly opted insecure for tests.

**Tests run:**
24 hardening tests passing; full suite 116 passed (was 106). `python -m compileall -q binance_data_layer tests/test_market_data_hardening.py`; `git diff --check` clean (CRLF warnings only).

**Open questions / follow-ups:**
None — all P0 (1-5), P1 (6-10), P2 (11-13) closed. Service meets Module 2 acceptance: 66 original tests green, soak recovers with bounded growth, loopback default with token+TLS gate for remote.

**Soak results (completion):**
`run_soak(duration_seconds=0.2, disconnects=2, event_count=20)` → recovered true, 20 persisted; `run_soak(..., restart_at_half=True)` → restarts 1, no loss; default `duration_seconds` is now `86400.0`; memory <10MB, queues <1000.

---

### [Module 3] Observer + Context Builder — 2026-09-24

**What was implemented:**
- `hermes/models/market.py` — frozen `MarketContext` plus `RegimeState`, `TrendState`, `OrderFlowState`, `DerivativesState`, `OptionsState`, `LiquidityState`, `CrossExchangeState`, `DataQualityState`, `PortfolioState`, `StrategyState` with `to_dict()`, `coerce_portfolio()`, `coerce_strategy_state()`.
- `hermes/context.py` — `ContextBuilder` (deterministic, no LLM): freshness/completeness/contradiction checks → `valid=False` fail-closed; EMA-alignment regime classifier (`TREND_UP`/`TREND_DOWN`/`RANGE`), volatility/breadth/risk legs, `detect_regime_change()`, `should_emit()` (interval + `INITIAL`/`REGIME_CHANGE`/`VALIDITY_CHANGE`).
- `hermes/observer.py` — `HermesObserver`: WS handlers (`market_event`, `breadth`, `cross_exchange_confirmation`, `universe_update`), `refresh_once()` pure pass, `refresh_from_store()` read-only pull from `MarketStore`/collector states, `subscribe()` hook for Module 5, `run_forever()`/`stop()` loop. No imports from `strategies/`, `risk/`, `execution/`, or `decision`.
- `tests/test_observer_context.py` — 8 tests: normal update, stale → invalid, contradictory health → invalid, regime-change + emit cadence, restart recovery, WS + subscriber hook, no-trading-imports scan, determinism.

**How it differs from the spec (if at all):**
Package lives at `hermes/observer.py`, `hermes/context.py`, `hermes/models/market.py` per the recommended Hermes folder structure instead of bare top-level files. Derivatives and options sections are implemented but report `available=False` until REST analytics snapshots carry funding/OI/basis and IV/Greeks through the feature snapshot; portfolio/strategy default to empty until Modules 4/8 wire real state. No strategy/decision calls from this module.

**Tests run:**
`tests/test_observer_context.py` 8 passed; full suite 124 passed (was 116). Unit level per Module 12; no trading paths exercised (analysis-only).

**Open questions / follow-ups:**
None for Module 3. Module 5 can subscribe via `HermesObserver.subscribe()` and consume `MarketContext.to_dict()`.

**Fields implemented vs deferred:**
Implemented: regime, price/trend (returns, EMA, RSI, ATR, VWAP, Bollinger, alignment), order flow (CVD, aggressive-buy, concentration, imbalances), liquidity (spread, depth, execution impact), cross-exchange, data quality, portfolio/strategy shells. Deferred (available=False until upstream data flows): derivatives funding/OI/basis/positioning/liquidations, options IV/Greeks/positioning.

**Staleness detection:**
`event_time_ms` vs `now_ms` beyond `stale_after_seconds` → `STALE`; missing snapshot/time → `MISSING_*`; any recent health entry `BAD`/`DEGRADED`/`disconnected`/`error`/`STALE` for the symbol or global scope → `UPSTREAM_UNHEALTHY`; `CONFIRMED` cross-exchange with disagreement above threshold → contradiction. All yield `valid=False`.

---

### [Module 4] Strategy Proposal Layer — 2026-09-24 (gate-enforced scaffolding, zero strategies wired)

**What was implemented:**
- `strategies/base.py` — hardened `StrategyProposal` contract (all 10 spec fields, `edge_validation_record_id` required non-empty, action `BUY`/`SELL`/`HOLD`, confidence in `[0, 1]`, evidence/invalidation lists validated, `__post_init__` fail-closed) plus `LoadedStrategy`, `require_gate()` load-time helper, deterministic `deterministic_proposal_id()` (uuid5).
- `strategies/registry.py` — `load_strategy()` now rejects falsified Breakout/Scalping with an explicit `FALSIFIED` message and otherwise delegates to `require_gate()`; version wired from `linked_strategy_version_id` (default `v1`).
- `strategies/proposal.py` (new, not a strategy) — `build_proposal()` deterministic factory: mismatched/missing edge link raises, invalid context forces `HOLD`, evidence must be non-empty MarketContext refs, default invalidation conditions, `evidence_ref()` + `describe_context_evidence()` template helpers.
- `strategies/calibration.py` (new) — `calibrate_confidence(hits, total)` Laplace-smoothed hit rate `(hits+1)/(total+2)` in `[0, 1]` plus `confidence_from_window_returns()`; no hardcoded confidence anywhere.
- `strategies/` contains NO `<strategy_name>.py` files — correct per hard rule: gate holds zero `PASS` verdicts (Trend Following `FAIL`, others untested; Breakout/Scalping `FALSIFIED`), so nothing was wired.
- `tests/test_strategy_layer.py` — 7 tests: synthetic-`PASS` proposal links record ID + deterministic IDs, Breakout/Scalping explicit rejection, ungated/FAIL candidates blocked, calibration equals exact smoothed fractions with ordering, invalid context → `HOLD`, bad confidence/empty evidence/missing link raise, no ungated strategy files present.

**How it differs from the spec (if at all):**
`proposal.py`/`calibration.py` are additions beyond the listed `base.py`/`registry.py`/`<strategy>.py` — they are the testable machinery that lets a future `PASS` strategy be wired without touching the gate. Zero production strategies implemented is intentional compliance with the hard rule, not an omission.

**Tests run:**
`tests/test_strategy_layer.py` 7 passed; `tests/test_strategy_gate.py` 3 passed; full suite 131 passed (was 124). `python -m compileall -q strategies tests/test_strategy_layer.py`; `git diff --check` clean (CRLF warnings only).

**Open questions / follow-ups:**
Module 4 stays `Blocked` until Module 1 records a `PASS`. When a candidate passes, add `strategies/<strategy_name>.py` calling `require_gate()` at import and routing through `build_proposal()` + `calibrate_confidence()`; log its gate record ID then.

**Strategies implemented:** none (gate has no PASS to link).
**Gate record IDs:** none issued (synthetic `PASS` records exist only inside ephemeral test registries).
**Confidence calibration method:** Laplace-smoothed historical hit rate `(hits + prior_hits) / (total + prior_total)`, default prior `1/2` (skeptical 0.5); `confidence_from_window_returns()` counts positive windows as hits with an explicit loop.

---

### [Module 1] Edge Validation Gate — 2026-09-24 (Order Flow candidate experiment)

**What was implemented:**
Ran the second eligible candidate family through the gate on real Binance data. Pre-registered hypothesis `cc6dbcef-5be7-4911-943b-5c30ac4c96a7` for `order_flow` on the fresh, untouched `2024-04-02` through `2024-07-01` BTCUSDT 1-hour holdout (disjoint from the Trend Following `2024-01-01`–`2024-04-01` window; Breakout/Scalping seeds carry no holdout). Locked entry/exit rules before touching data: completed-candle volume above 2.0x the prior-20 mean, next-open execution, 2% stop-loss checked before volume-normalization exits, 25% cash sizing; costs 0.10% fee/side, 31.2% VDA tax on gains without loss offset, 1% TDS drag. Fetched 2,160 completed candles (dataset SHA-256 `8cb531d3…`), ran four chronological windows plus doubled-cost stress, computed bootstrap evidence (seed 20260924, 2,000 samples), checked disjoint replication (first half vs second half), and recorded the final verdict append-only.

**Result: FAIL (final, not retryable).** Aggregate net `-10.1304%`, stress `-13.2716%`, bootstrap CI `[-1.6414%, -1.2204%]` entirely negative across 111 trades; all four windows negative (`-8.91%`, `-10.62%`, `-9.89%`, `-11.11%`); replication `FAIL` (primary `-8.91%`, replication `-11.11%`). Five acceptance items failed: three-of-four-windows, aggregate-positive, bootstrap-excludes-zero, beats-risk-free-by-CI-width, stress-costs.

**How it differs from the spec (if at all):**
No divergence in rigor — same cost model, bootstrap, regime, and replication machinery as the Trend Following run. One filing deviation: the run is recorded in the runtime ledger (`research/runtime_edge_validation.sqlite3` + `research/reports/EXPERIMENT_REGISTRY_RUNTIME.md`, preregistration line 223 precedes result line 259) rather than the pristine `research/reports/EXPERIMENT_REGISTRY.md`, which remains the untouched spec mirror per the established convention. No filter was tuned, so step 5 credits nothing and the replication leg is reported as-is.

**Tests run:**
Full suite 131 passed after the run (no code paths changed — experiment only). Ledger verified: `order_flow HYPOTHESIS/PENDING → RESULT/FAIL` with persisted evidence fingerprint `148c3ba1…`. Artifact: `research/reports/order_flow_experiment.json`.

**Open questions / follow-ups:**
Do NOT retry Order Flow on `2024-04-02`–`2024-07-01` and do NOT wire `strategies/order_flow.py`. Module 4 remains correctly blocked. Next eligible families, each requiring its own fresh disjoint holdout and preregistration: Mean Reversion, VWAP Reversion. Two independent family FAILs (Trend Following, Order Flow) is now a real finding about hourly crypto momentum/volume edges net of VDA costs, not a single bad draw.

---

### [Module 1] Edge Validation Gate — 2026-09-24 (Mean Reversion candidate experiment + project-level stopping rule)

**Project-level stopping rule (locked here in writing; binds VWAP Reversion and everything after):**
Five of six strategy families have now failed (Breakout, Scalping, Trend Following, Order Flow, Mean Reversion). VWAP Reversion runs as the sixth and final pre-committed experiment on its own fresh disjoint window. After that, regardless of the VWAP outcome, no further hourly-technical-signal families or filters-within-them may be tested without a materially new hypothesis class — different timeframe, different asset, or non-technical signal. If VWAP fails too (6/6), the standing conclusion becomes the project-level finding: hourly technical signals on BTCUSDT at retail Indian cost/tax structure carry no validated edge, and effort redirects to revisiting the hypothesis universe instead of burning further holdouts. (Ordering note: this rule was committed in the same session as the Mean Reversion run below, so it does not retroactively govern that run — it fully governs VWAP and beyond.)

**What was implemented:**
Ran the third eligible candidate family, Mean Reversion alone (VWAP deliberately held back so a FAIL here cannot look like it primed a parallel run), on the fresh untouched `2024-07-02` through `2024-10-01` BTCUSDT 1-hour holdout — disjoint from both burned windows (`2024-01-01`–`04-01`, `2024-04-02`–`07-01`). Pre-registered hypothesis `4b626ced-4ab8-490a-aab0-89a5a0f758b9` before touching data: completed-close ≥1.0σ below trailing-20 mean, next-open execution, 2% stop-loss before mean-reversion exits, 25% sizing; same 0.10%/31.2%/1%-TDS cost model. Fetched 2,184 completed candles (dataset SHA-256 `a933bf7c…`), four windows plus doubled-cost stress, bootstrap evidence (seed 20260924, 2,000 samples), disjoint first-half/second-half replication, verdict recorded append-only.

**Result: FAIL (final, not retryable).** Aggregate net `-9.4875%`, stress `-11.7008%`, bootstrap CI `[-1.8628%, -1.2315%]` entirely negative across 96 trades; all four windows negative (`-6.90%`, `-13.36%`, `-10.39%`, `-7.30%`); replication `FAIL` (primary `-6.90%`, replication `-7.30%`). Five acceptance items failed, same set as Order Flow.

**How it differs from the spec (if at all):**
No rigor divergence. Same runtime-ledger filing convention. No filter tuned, replication reported as-is.

**Tests run:**
Full suite 131 passed after the run (experiment only, no code changes). Ledger verified: `mean_reversion HYPOTHESIS/PENDING → RESULT/FAIL`, evidence fingerprint `51fdaf75…`. Artifact: `research/reports/mean_reversion_experiment.json`.

**Open questions / follow-ups:**
Do NOT retry Mean Reversion on `2024-07-02`–`2024-10-01`; do NOT wire `strategies/mean_reversion.py`. Three of four eligible candidates have now failed with the same signature (negative aggregate, entirely-negative CI, all windows negative, failed stress) — the pattern the stopping rule above was written for. VWAP Reversion is the one remaining pre-committed experiment.

---

### [Module 5] Decision Engine — 2026-09-24 (synthetic proposals only; production behavior is idle-HOLD)

**What was implemented:**
- `hermes/models/decision.py` — frozen `Decision` (all 12 spec fields validated in `__post_init__`, including `risk.stop_loss/take_profit/risk_amount` and positive `expiry_seconds`) plus `DecisionEvidenceRecord` (all 9 spec fields) with `to_dict()` views.
- `hermes/decision.py` — `decide()` (weighted-majority vote, HOLD-favoring ties, fail-closed to HOLD on invalid context/symbol mismatch/zero valid proposals/malformed entries), deterministic uuid5 `decision_id`, template `thesis`/`decision_rationale`, ATR-derived reference stop/take (2×/3× ATR, `risk_amount` 0.0 — sizing belongs to Module 6), `is_expired()`/`consume_decision()` downstream-expiry contract raising `ExpiredDecisionError`. No LLM, no trading calls; only import from `strategies/` is the `StrategyProposal` contract type.
- `tests/test_decision_engine.py` — 10 tests written determinism-first: byte-identical reruns, zero-proposal HOLD for every symbol, exact-tie HOLD, weighted-majority win, expiry rejection (+boundary valid), malformed-input fail-closed, calibration equality against the documented formula, template-thesis determinism, no-LLM/no-trading-imports scan, evidence-record shape.
- `tests/test_observer_context.py` — narrowed `test_no_trading_imports_in_module_3` to Module 3's own files (`observer.py`, `context.py`, `models/market.py`); the old whole-`hermes/` scan correctly tripped on Module 5's legitimate contract-type import.

**How it differs from the spec (if at all):**
Files live at `hermes/decision.py` + `hermes/models/decision.py` (Module 3 precedent) rather than bare top-level paths. No real strategies consumed — all tests use synthetic PASS-linked fixtures (Module 4's pattern), since Module 4 has zero wired strategies. `risk_amount` is always 0.0 and BUY/SELL carry `PendingRiskReview` because sizing/approval belong to Module 6.

**Tests run:**
`tests/test_decision_engine.py` 10 passed; full suite 141 passed (was 131). Unit level per Module 12 (determinism doubles as backtest-validation reproducibility). `python -m compileall -q hermes tests/test_decision_engine.py`; `git diff --check` clean (CRLF warnings only).

**Open questions / follow-ups:**
Runs on synthetic proposals only — in production today it outputs HOLD for every symbol (verified by test), which is the only honest behavior with zero gated strategies. No gate or Module 4 files touched.

**Confidence-calibration formula:** per-strategy weights `w_i = calibrate_confidence(hits_i, total_i)` (unknown → prior-only 0.5); agreement shares `W_action / W_total`; confidence `(W_win + 1) / (W_total + 2)` — the same skeptical (1, 2) prior as Module 4 applied at the agreement level; zero-proposal HOLD uses `confidence_from_window_returns([])` = 0.5 meaning "no evidence".
**Tie-break rule:** highest weighted share wins; any exact tie (including BUY vs SELL) resolves to HOLD — a tie is no preponderance of validated evidence, and fail-closed resolves ambiguity to HOLD. Comparison order fixed at BUY, SELL, HOLD so reruns are identical.
**Determinism test result:** same context + same proposal set → byte-identical `to_dict()` JSON (sort_keys) and identical `decision_id` across reruns — passing.

---

### [Module 1] Edge Validation Gate — 2026-09-24 (cost attribution diagnostic + VWAP Reversion final experiment)

**What was implemented (Task 1 — diagnostic, no new data, no new holdout):**
Recomputed pre-tax/pre-fee returns over the three completed experiments by re-fetching the same windows, verifying dataset SHA-256 equality with each artifact (all three match), reproducing the trade sequences exactly (66 / 111 / 96 trades, aggregates match to <1e-9), then stripping costs trade by trade with timing held fixed (raw open = entry/(1+s), raw exit = exit/(1−s)); zero-cost reruns corroborate. Bootstrap CIs use the gate's percentile method (seed 20260924, 2,000 samples), diagnostic-only. Outputs: `research/reports/cost_attribution.json` (machine-readable) + `research/reports/cost_attribution_summary.md` (human-readable).

**Pre-tax vs. post-cost split (Task 1 findings):**
- Trend Following: net `-5.34%` → pre-cost `+0.38%`, CI `[-0.23%, +1.08%]`, gap 5.72 pts. Reading (b): mildly positive before costs, pushed negative by the cost structure — with the note that the pre-cost CI still straddles zero.
- Order Flow: net `-10.13%` → pre-cost `-0.00%`, CI `[-0.22%, +0.24%]`, gap 10.13 pts. Reading (a): flat before costs.
- Mean Reversion: net `-9.49%` → pre-cost `-0.11%`, CI `[-0.44%, +0.25%]`, gap 9.38 pts. Reading (a): flat-to-negative before costs.
- Cost composition (share of starting notional): 1% TDS turnover drag dominates (16.02% / 26.35% / 22.65%), then fees and slippage (~3–5% each), VDA tax small (3.17% / 0.92% / 1.25%) because there are few gains to tax. Zero-cost reruns agree (`+0.37%` / `-0.01%` / `-0.07%`); Trend/Order Flow timing near-identical with and without costs, Mean Reversion timing is stop-sensitive but both estimates agree at the same level.

**What was implemented (Task 2 — VWAP Reversion, sixth and final pre-committed experiment):**
Pre-registered hypothesis `e53a9ebf-2201-479a-b15a-35f37d51a5e1` for `vwap_reversion` on the fresh untouched `2024-10-02` through `2025-01-01` BTCUSDT 1-hour holdout (disjoint from all three burned windows) before touching data: completed-close ≥2.0% below trailing-20 VWAP, next-open execution, 2% stop-loss before VWAP-reversion exits, 25% sizing; same 0.10%/31.2%/1%-TDS cost model. Fetched 2,184 completed candles, four windows plus doubled-cost stress, bootstrap evidence (seed 20260924, 2,000 samples), disjoint first-half/second-half replication (no filter tuned, reported as-is), verdict recorded append-only. `strategies/` untouched.

**VWAP verdict and full evidence (Task 2 findings): FAIL (final, not retryable).** Aggregate net `-1.1271%`, stress `-1.5559%`, bootstrap CI `[-1.8475%, -0.2995%]` entirely negative across 16 trades (below the 20-trade minimum); all four windows negative (`-0.03%`, `-0.19%`, `-1.82%`, `-2.47%`); replication `FAIL` (primary `-0.03%`, replication `-2.47%`). All six acceptance items failed, including `minimum_sample_size`. Ledger: `vwap_reversion HYPOTHESIS/PENDING → RESULT/FAIL`, evidence fingerprint `e55e9600…`. Artifact: `research/reports/vwap_reversion_experiment.json`.

**Failed-family count: 6/6.** Breakout, Scalping (falsified) + Trend Following, Order Flow, Mean Reversion, VWAP Reversion (candidate FAILs). The pre-committed experiment set is now complete.

**How it differs from the spec (if at all):**
No rigor divergence in either task. Task 1 touched no gate state and changed no code. Task 2 follows the same runtime-ledger filing convention as the prior three runs.

**Tests run:**
Full suite 141 passed after both tasks (no production code changed). No Module 4 or Module 5 status changes; no strategy files added or wired.

---

### [Step 1] Cheap Manual Probe + Paper-Trading Support — 2026-09-24 (on `experiments/research-track`)

**What was implemented (Part A — daily-trend probe, new hypothesis class):**
Pre-registered hypothesis `252cba87-d4c2-4b37-9a7b-249902027e4b` for `daily_trend_following` (distinct family from hourly trend) on the untouched 2023-01-01–2024-01-01 BTCUSDT daily holdout before touching data: daily EMA(5)/EMA(20) crossover, next-daily-open execution, 2% stop first, 25% sizing; same 0.10%/31.2%/1%-TDS cost model, default parameters, no tuning. Fetched 365 daily candles (dataset `7618f158…`), four quarterly windows plus doubled-cost stress, bootstrap evidence (seed 20260924, 2,000 samples), disjoint half/half replication, verdict recorded append-only. `strategies/` untouched.

**Probe result: FAIL (final, not retryable).** 8 trades (below 20 minimum), aggregate net `-1.0963%`, stress `-1.2977%`, bootstrap CI `[-3.2749%, -0.1505%]` entirely negative; windows `-1.68%`, `-1.44%`, `-1.27%`, `0.00%`; replication FAIL. All six acceptance items failed. Ledger: `daily_trend_following HYPOTHESIS/PENDING → RESULT/FAIL`, fingerprint `fa0dbbd6…`. Artifact: `research/reports/daily_trend_experiment.json`. Against the probe bar (flat-or-better pre-cost, non-entirely-negative CI, or one positive leg): clears nothing — no signs of life. The 2023 daily window is burned for this family.

**What was implemented (Part B — paper-trading support):**
New `paper_trading/` package (stdlib only): `simulator.py` (`PaperOrder` validated deterministic ids, `simulate_fill` with fee/adverse-slippage/depth-capped PARTIAL/empty-book REJECTED, `execution_report` expected-vs-realized), `portfolio.py` (`PaperPortfolio`, long-only v1, oversell raises, equity marks at cost on missing data), `engine.py` (`PaperEngine.submit`/`replay`/`equity`/`snapshot`). Offline, credential-free, no network imports. `tests/test_paper_trading.py`, 7 tests (exact fill math, partials, adverse slippage both sides, expected-vs-realized, round-trip + oversell rejection, deterministic replay, no-network-import scan).

**How it differs from the spec (if at all):**
No spec covers Step 1 (it was a decision-point probe, not a numbered module). Stopping-rule compliance: daily timeframe is an explicitly listed new class (different timeframe), so this run was permitted; hourly families remain closed.

**Tests run:**
`tests/test_paper_trading.py` 7 passed; full suite 148 passed (was 141). `python -m compileall -q paper_trading tests/test_paper_trading.py`; `git diff --check` clean (CRLF warnings only). No Module 4/5 changes.

**Open questions / follow-ups:**
Detailed record: `research/reports/STEP1_DAILY_PROBE_AND_PAPER.md`. The adjacent-space premise did not confirm — reserved for Atharva per the pending project-level decision.

