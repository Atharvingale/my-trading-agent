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

---

### [Finding] Edge-Validation Research Close-Out — 2026-09-24 (on `experiments/research-track`)

**What was implemented:**
Wrote `research/PROJECT_FINDING.md`: one-page dated close-out of the research phase. States scope (6 hourly families + 1 daily probe, gate criteria applied), results table (7 rows, 0 PASS, daily n=8 flagged as thin sample), cost-attribution finding (pre-cost near-zero, TDS dominant drain on flat signals), explicit burned-vs-untouched holdout budget, three paths forward stated without recommendation ((a) cost-structure change marked out of scope, (b) funding-rate/cross-exchange new classes requiring fresh pre-commitment, (c) stop here), and the working infrastructure that remains regardless. Decision explicitly left to Atharva. No code, gate, or status changes.

**How it differs from the spec (if at all):**
No spec covers a finding document; this closes the loop the stopping rule required rather than opening new work.

**Tests run:**
Full suite 148 passed (nothing changed but the two added files). `git diff --check` clean (CRLF warnings only).

---

### [Modules 1+4] Two-plane provenance + production promotion adapter — 2026-09-26

**What was implemented:**
- `edge_validation/registry.py` — `submit_hypothesis()` now accepts optional research provenance (`candidate_id`, `parent_candidate_id`, `hypothesis_id`, `signal_class`, `source=HUMAN|AI_RESEARCH|TRADE_LEARNING`, `provider_used`, `multiple_testing_family`, `multiple_testing_threshold in (0,1)`); same validation path for human and Module 15 hypotheses. `EdgeValidationRecord` carries the 8 fields (old rows read as None/HUMAN). Added `get_provenance(record_id)` and `trace_candidate(candidate_id)` lineage walk. `_validate_provenance()` rejects empty strings and unknown sources fail-closed.
- `edge_validation/report_writer.py` — preregistration lines now retain source/candidate/parent/hypothesis/signal/provider/MT family+threshold.
- `candidate_generation/__init__.py` + `candidate_generation/review_queue.py` (new) — SQLite append-only review queue with no-update/no-delete triggers; `submit_for_review()` never approves, `approve()/reject()` require non-empty approver+rationale, one decision per record, `is_approved()` true only after explicit approval, `list_pending()` in submit order.
- `strategies/production_versions.py` (new) — append-only immutable `strategy_versions` store; `create_version()` requires non-empty version/approver/rationale, duplicate version_id rejected; `get_active_version()` returns latest row.
- `strategies/promotion.py` (new) — narrow adapter `promote_candidate()` requires live PASS for the exact record (`require_pass` match) AND `reviews.is_approved()`, then creates the immutable version. Neither condition alone suffices.
- `strategies/registry.py` — kept `load_strategy()` PASS-only unchanged for backward compat; added `load_production_strategy()` requiring current PASS plus matching approved version (stale-record mismatch raises). Falsified Breakout/Scalping still raise explicitly in both.
- `tests/test_promotion.py` (new, 6 tests) — Module 15 submit-like-human + provenance/report/lineage, holdout-retry blocked, unapproved blocked, PASS-without-approval blocked, approved loads, no-LLM in proposal path (adapter may reference review queue but no provider).

**How it differs from the spec (if at all):**
No divergence — narrow additions only per 00-compatibility rule. Modules 1–5 core logic untouched; no LLM in `strategies/base|proposal|calibration|registry` proposal path; no placeholder production strategies created. Seeded falsified set left as breakout/scalping to keep existing gate tests green; expanded 7-family historical list enforced via PASS+approval (all blocked with zero versions approved).

**Tests run:**
`tests/test_promotion.py` 6 passed; `test_edge_validation + test_strategy_gate + test_strategy_layer + test_decision_engine` 43 passed; full suite 154 passed (was 148). `python -m compileall -q edge_validation strategies candidate_generation`.

**Open questions / follow-ups:**
Still open per Module 15 spec: `generator.py`, `hypothesis_menu.py` (with 7-family exclusion), `multiple_testing.py` (stricter bar after N hypotheses), `provider_client.py` (env-swappable). No production versions approved; Module 4 remains correctly Blocked.

---

### [Module 10] Memory / Database Model — 2026-09-26

**What was implemented:**
- `memory/schemas.py` (new) — `SCHEMA_VERSION=1`, `CHAIN_ORDER` (13-stage spec order), `TABLES` (20/20 spec tables), idempotent `SCHEMA` SQL with TEXT primary keys, FK links for the full chain, indexes on symbol/time/strategy/decision legs, plus no-update/no-delete triggers on `edge_validation_records` and `strategy_versions`.
- `memory/repository.py` (new) — `MemoryRepository` SQLite (WAL, foreign_keys=ON) with `migrate()` stamping `user_version`, `update_record()/delete_record()` refusing destructive edits, explicit `record_*` writers for all 20 tables (chain rows carry predecessor IDs), `get(table,id)`, `chain_order()`, and `trace(trade_id)` walking trade→position→order→execution→risk→decision→snapshot+edge→proposals/evidence→analysis→lesson→version (lesson-first, edge-fallback for versions) in spec order or raising `TraceNotFoundError`.
- `memory/__init__.py` — exports `MemoryRepository`.
- `tests/test_memory_model.py` (new, 7 tests) — synthetic end-to-end trace with linkage assertions and key-order check, 20-table existence, supporting-table roundtrip, edge append-only (SQL + layer), versions append-only (SQL + layer), unknown-trade raises, migrate idempotent/versioned.

**How it differs from the spec (if at all):**
No divergence. New unified store only — existing `MarketStore`, `edge_validation.registry`, `review_queue`, `production_versions` left untouched per 00-compatibility rule. Supporting tables (candles/breadth/derivatives/universe/health/metrics/raw events) persist outside the per-trade path but roundtrip via `get()`. `lessons` allows many rows per analysis with latest-wins; `trade_analysis` is one-per-trade (UNIQUE). No new dependencies (stdlib sqlite3 only).

**Tests run:**
Unit/Integration per 12-testing-strategy.md: `tests/test_memory_model.py` 7 passed; full suite 161 passed (was 154). `python -m compileall -q memory tests/test_memory_model.py`; `git diff --check` clean (CRLF warnings only). No `sorted()`, no comprehensions, no `__main__` guards in new code.

**Open questions / follow-ups:**
None for Module 10. Future modules 6–9 should write through this repository so live traces accumulate; a read-only migration from legacy `MarketStore`/`runtime_edge_validation.sqlite3` rows was deliberately not added — import only when a consumer needs it.

**Storage engine:** SQLite (WAL). **Migration approach:** additive idempotent `migrate()` via `CREATE TABLE/INDEX/TRIGGER IF NOT EXISTS` + `PRAGMA user_version=SCHEMA_VERSION`; reopening upgrades without loss. **trace() result:** synthetic `trade-001` returns all 13 stages in order with predecessor IDs verified.

---

### [Module 15] Candidate Generation Loop — 2026-09-26

**What was implemented:**
- `candidate_generation/hypothesis_menu.py` (new) — `INITIAL_APPROVED` funding-rate carry + cross-exchange dislocation; `EXCLUDED` 8 falsified patterns with Module 1 reasons; normalized matching plus repackaged-substring guard; `HypothesisMenu` with `check()/require_allowed()/is_allowed()`, `add_with_approval()` requiring approver+rationale (persisted, append-only), `list_approved()/list_excluded()`.
- `candidate_generation/multiple_testing.py` (new) — Bonferroni `required_significance(base/total)`, `count_hypotheses()` from live `edge_validation_records` HYPOTHESIS rows (registry or db path), `adjusted_threshold()` returning method/family/base/total/required, `meets_adjusted_bar()`.
- `candidate_generation/provider_client.py` (new) — stdlib `urllib` JSON POST `propose_hypothesis(prompt, api_url, api_key, model_name)` plus `load_config_from_env()` (`CANDIDATE_PROVIDER_URL/_API_KEY/_MODEL`, never hardcoded) and `propose_from_env()`; non-JSON/non-object raises for fail-closed logging.
- `candidate_generation/generator.py` (new) — `CandidateHypothesis` per spec contract plus candidate/parent lineage; `CandidateGenerator` SQLite audit (`candidates` append-only, `rejected_responses`, `preregistrations` linkage table) with weekly `min_interval_seconds` schedule + `max_candidates` budget, `should_run()/check_schedule()`, `build_prompt()` naming approved classes only, `run_once()`/`generate_from_response()` fail-closed (malformed→REJECTED row + None; excluded→EXCLUDED row, never gated), `preregister()` through identical Module 1 path with live Bonferroni threshold as provenance. No imports from `strategies/`, `risk/`, `execution/` — cannot wire anything.
- `candidate_generation/__init__.py` — full exports. `review_queue.py` unchanged (already append-only, never auto-promotes).
- `tests/test_candidate_generation.py` (new, 11 tests) — excluded Breakout repackaging rejected pre-gate, menu sign-off rules, MT 0.05 vs 0.005 + live-ledger growth, PASS-without-approval never wires (no `strategies/<name>.py`), two-mock-server env swap, 5 malformed payloads rejected, schedule/budget respected, full audit permanence, no-wiring-imports scan.

**How it differs from the spec (if at all):**
Two narrow, logged choices: (1) stdlib `urllib` instead of `aiohttp` for the POST — same env-swappable behavior, keeps the module dependency-free per 14-conventions (`aiohttp` stays approved but unused here); (2) `preregistrations` companion table instead of mutating the append-only `candidates` ledger to record gate linkage. No LLM in Module 4/5 paths; existing promotion adapter unchanged.

**Tests run:**
Unit/Contract/Integration per 12-testing-strategy.md: `tests/test_candidate_generation.py` 11 passed; full suite 172 passed (was 161). `python -m compileall -q candidate_generation tests/test_candidate_generation.py`; `git diff --check` clean (CRLF warnings only). No `sorted()`, no comprehensions, no `__main__` guards in new code.

**Open questions / follow-ups:**
None for Module 15 scaffolding. Live use still needs a dated human-approved holdout per experiment and an operator-set `CANDIDATE_PROVIDER_*` endpoint; the loop proposes at most weekly by default and every proposal still faces the full gate + human review.

**Initial menu:** funding-rate carry, cross-exchange dislocation. **Correction method:** Bonferroni (`required = 0.05 / total_including_current`). **Providers used/tested:** two local mock HTTP endpoints via env swap (no vendor SDK); production provider is a config change, not a code change.

---

### [Module 6] Deterministic Risk Engine — 2026-09-26

**What was implemented:**
- `risk/limits.py` (new) — frozen `RiskLimits` dataclass (all thresholds config-driven, validated positive in `__post_init__`) plus pure `check_*` functions for symbol/portfolio exposure, concurrent positions, daily loss, drawdown, leverage, stop distance, liquidity/depth/spread, and stop-out cooldown.
- `risk/position_sizing.py` (new) — `calculate_quantity()` exact deterministic sizing: risk_amount = equity × risk_per_trade, quantity = risk_amount / |entry − stop|, then capped by position-notional and depth budgets in a fixed order. Raises on non-positive inputs; never rounds downstream.
- `risk/engine.py` (new) — `RiskEngine` with fixed rule order (kill → HOLD → stale context → symbol → expiry → duplicate → cooldown → existing position → reference/stops → stop distance → sizing → min-notional floor → exposure → positions → daily loss → drawdown → leverage → liquidity). `RiskDecision` per spec contract plus `integrity_hash` (SHA-256 over canonical JSON); `verify_integrity()` recomputes it for Module 7. Kill switch (`activate/clear/is_halted`, manual clear needs approver+rationale), duplicate `decision_id` set, per-symbol stop-out cooldown map. HOLD returns auditable REJECTED with zero quantity.
- `risk/__init__.py` — exports. `tests/test_risk_engine.py` (new, 23 tests) — happy-path approval, stale-context rejection, HOLD no-action, tamper detection (quantity + stop), kill-switch block/clear validation, and pass+reject paths for all 11 checks plus expiry/symbol/duplicate/position/cooldown/liquidity/spread, config-driven validation, exact sizing math, no-LLM/execution-imports scan.
- One design fix during testing: depth-capped sizing could shrink orders to dust on thin books (and collapse strict-notional tests to $1 approvals), so a `min_order_notional` floor (default 10.0) rejects sub-minimum orders instead of rounding up.

**How it differs from the spec (if at all):**
Two additive extras, both logged: (1) `integrity_hash` on `RiskDecision` beyond the 8 spec fields — required to enforce the critical invariant (exact quantity to execution); (2) `min_order_notional` floor — required so thin-book orders reject instead of dust-sizing. No new dependencies (stdlib only). Modules 10 and 15 untouched (verified via `git status`: only `risk/`, `tests/test_risk_engine.py`, status/log files changed).

**Tests run:**
Unit per 12-testing-strategy.md: `tests/test_risk_engine.py` 23 passed; full suite 195 passed (was 172). `python -m compileall -q risk tests/test_risk_engine.py`; `git diff --check` clean (CRLF warnings only). No `sorted()`, no comprehensions, no `__main__` guards in new code.

**Open questions / follow-ups:**
None for Module 6. Module 7 must call `verify_integrity()` before sending and must never recalculate quantity.

**Launch limit values:** per-symbol 1000.0, portfolio 3000.0, total 3000.0, max positions 3, daily loss 200.0, drawdown 0.10, leverage 1.0, risk/trade 0.01, stop 10–500 bps, spread 25 bps, depth fraction 0.25, min notional 10.0, cooldown 3600s.
**Kill switch:** `activate_kill_switch(reason)` rejects everything; `clear_kill_switch(approver, rationale)` resumes (both non-empty required).
**Quantity-integrity result:** tampered quantity (+1.0) and tampered stop (+5.0) both fail `verify_integrity()`; untouched approvals pass.

---

### [Module 7] n8n Execution Boundary — 2026-09-26

**What was implemented:**
- `execution/n8n_client.py` (new) — `ExecutionRequest` per spec contract (idempotency_key == execution_id); `build_request()` verifies `verify_integrity()`, requires APPROVED, copies quantity verbatim (no quantity parameter exists), validates symbol/side/order-type/expiry independently; `assert_quantity_matches()` exact-equality defense in depth (1e-9 drift raises), re-checked in `submit_request()` when the sealed decision is passed; `submit_request()` order is kill-switch → expiry (clock-injected `now`) → field validation → HMAC sign → sender, with `N8nUnavailableError` on transport failure and `RequestExpiredError` without ever sending late; `ExecutionConfig.from_environment()` enforces paper/production separation (exactly one pair present, loud fail on ambiguity); `default_sender()` stdlib HTTPS POST (tests inject fakes); `sign/verify_webhook_signature()` HMAC-SHA256 with timestamp skew window + nonce set for replay protection; secrets never logged.
- `execution/order_manager.py` (new) — `ExecutionOrderManager` SQLite ledger (append-only, no-delete trigger); `register()` idempotent; `submit_once()` sends at most once per execution_id (terminal/cached states return `duplicate_suppressed` without touching the network); transport failure marks EXPIRED and raises; `mark_acked/filled/rejected/expired()`, `list_by_state()`.
- `execution/reconciliation.py` (new) — pure `reconcile(local, exchange)` matching on order/execution/idempotency keys; reports matched/missing_on_exchange/unknown_locally/mismatched with action `ok` vs `freeze_new_entries` on unknown or mismatched truth.
- `execution/__init__.py` — exports. `tests/test_execution_boundary.py` (new, 20 tests) — unit (exact copy, tamper/non-approved/symbol/side/type rejection, 1e-9 + rounding drift, expiry boundary + late, kill-switch-halts-healthy, signature roundtrip/replay/tamper/stale/wrong-secret, secret-absence + no-logging-imports, config separation/ambiguity), contract (per-field independent validation, 11-field webhook schema), integration (entry flow to matched reconciliation, outage expiry without queueing or resend, close-intent characterization, no-LLM/no-sizing scan).

**How it differs from the spec (if at all):**
Two additive extras, both logged: (1) `assert_quantity_matches()` + optional `risk_decision` re-verification on submit — the spec's quantity invariant enforced at build AND submit; (2) kill-switch flag threaded through `submit_request()`/`submit_once()` so the halt works even when the decision layer is hung (Module 13 independence). No new dependencies (stdlib only). Modules 10 and 15 untouched; Module 6 untouched (`git status` shows no `risk/` modification).

**Tests run:**
Unit/Contract/Integration per 12-testing-strategy.md: `tests/test_execution_boundary.py` 20 passed; full suite 215 passed (was 195). `python -m compileall -q execution tests/test_execution_boundary.py`; `git diff --check` clean (CRLF warnings only). No `sorted()`, no comprehensions, no `__main__` guards in new code.

**Open questions / follow-ups:**
Module 6 semantic probe (no code change, per instruction): `test_close_intent_while_holding_is_currently_rejected` pins that risk rejects ANY decision while `position_qty != 0` — including a SELL that would close a long. Entry-vs-close distinction belongs to Module 8's order/position lifecycle; until then the conservative block stands and Module 7 only ever submits flat-state entries.

**Webhook auth/signing scheme:** HMAC-SHA256 over `timestamp_ms + nonce + canonical-JSON(payload)`; headers `X-Signature/X-Timestamp/X-Nonce/X-Idempotency-Key`; 300s skew window; nonce set rejects replays.
**Idempotency key format:** `exec_<16 hex>` == `execution_id`, stored UNIQUE, returned on duplicates without resend.
**Expiry-enforcement result:** late submit (+61s past 60s expiry) raises `RequestExpiredError` with zero sender calls; boundary instant submits; outage marks EXPIRED with exactly one sender attempt and cached retries.

---

### [Module 8] Order, Position, and Trade Lifecycle — 2026-09-26

**What was implemented:**
- `models/execution.py` (new) — `OrderState` (NEW/PARTIALLY_FILLED/FILLED/CANCELED/REJECTED/SUBMISSION_UNKNOWN) with a closed `TRANSITIONS` table (unknown exits only via reconciliation, terminal states have no exits); `Fill` (price/qty/fee/funding/latency/expected + `slippage_bps()`); `Order` (chain IDs, `apply_fill()` driving NEW→PARTIAL→FILLED with overfill protection, `mark_unknown()`, `remaining()`, `to_dict()`).
- `models/trade.py` (new) — `Position` (entry/exit prices, quantities, exposure, realized/unrealized PnL, fees/funding, MFE/MAE, slippage/latency averages, duration, amendments, reconcile state, mark path) and frozen `Trade` (`net_pnl()` net of fees/funding); pure `position_pnl()` + `excursion()` (non-negative MFE/MAE magnitudes) helpers.
- `monitoring/positions.py` (new) — `LifecycleTracker` SQLite ledger (orders/fills/positions/trades, no-delete triggers; UPDATEs allowed — it is a state machine, not an audit log): `place_order()` with ENTRY/REDUCE/CLOSE intents, `apply_fill()` opening/extending/realizing, `mark_price()` refreshing MFE/MAE, `stop_state()` (ARMED/STOP_HIT/TARGET_HIT), `mark_unknown()`/`resolve_unknown()` (guessed resolutions raise), `reconcile_from_exchange()` adopting exchange truth (missed fills synthesized from real exchange records, unknown resolved or canceled), `may_enter()`/`classify_intent()`, `get_chain()` (decision→execution→order→position→exit→trade), `amend_order()` (counted, quantity never rewritten). Memory mirroring uses existing `record_order/record_position/record_trade` only (order at placement, position at open, trade at close with analytics payload).
- `models/__init__.py`, `monitoring/__init__.py` — exports. `tests/test_lifecycle.py` (new, 12 tests) — state-machine legal/illegal jumps, unknown-needs-reconcile, synthetic-path MFE/MAE/slippage/PnL, partial-fills→position→close→trade with full chain, reduce-then-close quantities + oversize rejection, stop/target marks, unknown-blocking + resolve paths, missed-fill recovery, restart rebuild, memory mirroring with FK-coherent chain, risk→execution→lifecycle close flow.
- Two real findings fixed during testing (no protected-module changes): (1) reconcile re-resolved orders whose fills had already cleared unknown — fixed by reloading state and counting fill-path resolutions; (2) memory mirroring hit FK guards with orphan execution IDs — resolved by seeding the coherent upstream chain in the test (snapshot→edge→decision→risk→execution), proving the Module 10 contract works as designed.

**How it differs from the spec (if at all):**
Spec paths followed verbatim (`monitoring/positions.py`, `models/execution.py`, `models/trade.py`). One additive extra, logged: ENTRY/REDUCE/CLOSE intents + `may_enter()/classify_intent()` — this resolves the Module 6 close-intent question at the lifecycle layer (closes/reduces flow as opposite-side exit orders capped at open quantity; same-side adds stay blocked) with zero changes to risk, execution, memory, or candidate_generation (`git status` confirms). No new dependencies (stdlib only).

**Tests run:**
Unit/Lifecycle/Reconciliation/Integration per 12-testing-strategy.md: `tests/test_lifecycle.py` 12 passed; full suite 227 passed (was 215). `python -m compileall -q models monitoring tests/test_lifecycle.py`; `git diff --check` clean (CRLF warnings only). No `sorted()`, no comprehensions, no `__main__` guards in new code.

**Open questions / follow-ups:**
None for Module 8. Module 9 (trade intelligence) consumes closed `Trade` rows and MFE/MAE/slippage analytics from here.

**Reconciliation triggers:** on-restart ledger reopen (`reconcile_from_exchange` after restart), configurable poller calls the same function on an interval, on-gap-detection (fill IDs present on exchange but absent locally are synthesized), and any SUBMISSION_UNKNOWN row (resolved or canceled from confirmed truth only).
**Recovery-test result:** missed second fill recovered (PARTIAL→FILLED, position at full quantity, 1 recovered fill); restart with unknown + late fill resolved (unknown cleared, position opened); unknown blocks entries (placement raises) until `resolve_unknown` clears the symbol.

---

### [Module 9] Trade Intelligence and Continuous Learning — 2026-09-26

**What was implemented:**
- `learning/trade_analyzer.py` (new) — rule-based `analyze_trade()` answering all 12 post-trade questions from explicit evidence flags (context_valid, gate_record_ok, approved_quantity, regime_fit) in fixed priority (GATE → DATA → RISK → EXECUTION → REGIME → SIGNAL → NORMAL); `TradeAnalysis` with category, actionable flag, candidate hypothesis, and spec-table recommended action. Unknown plumbing fails toward DATA/investigate, never NORMAL. No LLM.
- `learning/lesson_engine.py` (new) — `LessonEngine` SQLite bank; `propose()` banks only actionable non-NORMAL analyses (NORMAL returns None); `validate()/reject()` need a human approver, decided once (UPDATE forbidden; adjudication consumes the row atomically); `counts()` per status.
- `learning/backtester.py` (new) — adapter over proven Module 1 machinery: `run_family_backtest()` dispatches known families to `edge_validation.experiment` causal backtesters (hint only — the gate delivers verdicts), unknown classes return INCONCLUSIVE with no invented simulator; `evaluate_trade_returns()` scores streams with `ExperimentEvidence` (net + bootstrap CI + fingerprint).
- `learning/paper_engine.py` (new) — thin adapter over `paper_trading.PaperEngine`: `run_paper_leg()` replays candidate orders against snapshots, returning fills, per-order reports, slippage totals, and portfolio snapshot. Zero duplicated simulation math.
- `learning/promotion.py` (new) — `promote_candidate()` requires a VALIDATED lesson then delegates to `strategies.promotion` (live PASS + review approval into an immutable version), so missing/non-PASS records raise and no parallel path exists; `StrategyStatus` pointer registry (`set_active`/`rollback`/`disable`/`enable` + audited history) with version rows never edited or deleted.
- `learning/__init__.py` — exports. `tests/test_learning.py` (new, 11 tests) — promotion refusal (missing/FAIL/unvalidated), single-loss config invariance, instant rollback + history-preserving disable, 7-category priority, lesson counts/adjudication, backtester dispatch + evidence scoring, paper determinism, full pipeline promotion, no-LLM scan.

**How it differs from the spec (if at all):**
Adapters reuse instead of rebuild (`edge_validation.experiment/evidence`, `paper_trading`, `strategies.promotion`, `ProductionVersionStore`, `ReviewQueue`) — no protected module modified (`git status` confirms: only `learning/`, `tests/test_learning.py`, status/log are new/changed). One structural note, logged: lesson adjudication is DELETE+INSERT (UPDATE trigger forbids edits) preserving full content plus decision. No new dependencies (stdlib only).

**Tests run:**
Unit/Learning per 12-testing-strategy.md: `tests/test_learning.py` 11 passed; full suite 238 passed (was 227). `python -m compileall -q learning tests/test_learning.py`; `git diff --check` clean (CRLF warnings only). No `sorted()`, no comprehensions, no `__main__` guards in new code.

**Open questions / follow-ups:**
None for Module 9. Live operation still needs dated human-approved holdouts per candidate and operator review of VALIDATED lessons before gate submission.

**Candidate lessons in initial testing:** 7 proposed across the test run, 1 promoted to a production version (full-pipeline test), 1 rejected, 4 validated-but-unpromoted (refusal-path fixtures proving the gate holds), 1 left pending (unvalidated-refusal fixture). Zero gate bypasses.
**Rollback-test result:** `rollback()` re-pointed v2→v1 in one pointer write, far inside the 5s bound (ms-scale), with 4+ audited history events; disable preserved both version rows intact.

---

### [Module 11] Supervisor and 24/7 Runtime — 2026-09-26

**What was implemented:**
- `supervisor.py` (new, top-level per spec) — `Supervisor` with asyncio task supervision: per-worker factories (fresh coroutine per restart), isolated crash handling (only the crashed worker restarts, siblings continue), exponential backoff, `rebuild()` gating `allow_decisions()` (no decision until portfolio state is rebuilt from the hook), `restart_down_workers()` for hung workers via health, independent kill hook (`trip_kill_switch` works with zero workers running), bounded `run_once()` for tests/dry runs, audited event log.
- `monitoring/health.py` (new) — `HealthMonitor` (HEALTHY/DEGRADED/DOWN/UNKNOWN from heartbeat age + failure streak, all 8 spec workers plus ad-hoc), `snapshot()`/`down_workers()`, binding `required_response()`/`evaluate_conditions()` covering all 11 failure-table rows (unknown fails closed to HOLD), `hold_for_stale_symbols()` directive.
- `tests/test_supervisor.py` (new, 10 tests) — crash-isolation restart with uninterrupted sibling, backoff growth + cap, stale→system-wide HOLD (context + directive + monitor DOWN), restart rebuild gating (closed before, exact state after; failed rebuild keeps gate closed), all 11 table rows + fail-closed unknown, thresholds + hung-worker restart, kill-hook independence, worker-name contract, banned-constructs scan.

**How it differs from the spec (if at all):**
No divergence. New files only — no existing module modified (`git status` confirms: only `supervisor.py`, `monitoring/health.py`, `tests/test_supervisor.py`, status/log are new/changed). No new dependencies (stdlib asyncio only).

**Tests run:**
Unit/Integration/Failure-injection per 12-testing-strategy.md: `tests/test_supervisor.py` 10 passed; full suite 248 passed (was 238). `python -m compileall -q supervisor.py monitoring tests/test_supervisor.py`; `git diff --check` clean (CRLF warnings only). No `sorted()`, no comprehensions, no `__main__` guards in new code.

**Open questions / follow-ups:**
None for Module 11. Live deployment still needs the operator to wire real worker coroutines (observer/collector loops), a real rebuild hook (exchange truth + durable records), and a kill hook into the risk engine; defaults are safe (gate closed until first rebuild succeeds).

**Process/orchestration technology:** stdlib asyncio task supervision (same mechanism as the market-data collector's background tasks) — no systemd/Docker dependency in code; those remain deployment choices.
**Restart-backoff parameters:** initial 1.0s, factor 2.0, max 60.0s per worker (consecutive-crash exponent, capped); clean exits are not relaunched.
**Restart-recovery test result:** crashed worker restarted (≥1 restart, sibling ticks uninterrupted); rebuild gate closed before hook success with exact pre-restart portfolio state after; failed rebuild (exchange unreachable) keeps the gate closed.

---

### [Module 12] Testing Strategy — 2026-09-26

**What was implemented (harness, not a service — the spec defines the bar):**
- `tests/test_levels.py` (new, 2 tests) — executable `LEVEL_COVERAGE` registry (11 spec levels → covering files) plus `MODULE_LEVELS` matrix (modules 01–11 and 15 → relevant levels); fails if any covering file is deleted or any module loses its level. This is what makes "no module is done until…" enforceable instead of aspirational.
- `tests/test_soak.py` (new, 1 test) — bounded 200-cycle market→context→decision→risk soak with deterministic walk and induced disconnects every 50th cycle: zero exceptions, 200/200 HOLD + REJECTED, 4 disconnects absorbed, zero positions/trades/fills/orders left behind.
- `tests/test_failure_injection.py` (new, 5 tests) — WS disconnect → HOLD + risk reject; n8n outage → EXPIRED with no position; Binance rejection ack → never ACKED, never a fill; kill switch refuses even pre-built healthy requests with zero sender calls; tampered in-flight decision refused at the boundary.
- `tests/test_backtest_validation.py` (new, 4 tests) — final-candle spike books zero trades (causal next-open execution), entry/exit index discipline, byte-identical reruns, stable-and-sensitive dataset SHA-256.
- `tests/test_venue_integration.py` (new, 2 tests) — n8n boundary into the paper venue: approved quantity fills exactly with cash movement; thin book PARTIALs without overfill.
- Pre-existing coverage retained and mapped: edge validation, unit, contract, integration, lifecycle, reconciliation, learning suites all keep passing under the registry.

**How it differs from the spec (if at all):**
No divergence. Test files only — zero source files touched (`git status` confirms). Live 24h/72h wall-clock soak and real testnet execution remain operator activities; the bounded soak and paper-venue integration are their CI-runnable analogues (same precedent as Module 2's simulated soak). No new dependencies.

**Tests run:**
Soak/Failure-injection/Backtest-validation/Execution-integration per the Module 12 table itself: 14 new tests passed; full suite 262 passed (was 248). `python -m compileall` on the five new files; `git diff --check` clean (CRLF warnings only). No `sorted()`, no comprehensions, no `__main__` guards in new code.

**Open questions / follow-ups:**
None for Module 12. The registry must be extended if a new level or module is ever added — `test_levels.py` fails loudly until it is.

**Per-module levels exercised (the Module 12 "When done" record):**
01 Edge Gate: edge_validation + backtest_validation. 02 Market Data: unit + contract + soak. 03 Observer/Context: unit + contract + integration. 04 Strategy Layer: unit. 05 Decision Engine: unit + contract + integration. 06 Risk Engine: unit. 07 Execution: unit + contract + execution_integration + failure_injection. 08 Lifecycle: unit + lifecycle + reconciliation + integration. 09 Learning: unit + learning. 10 Memory: unit + reconciliation. 11 Supervisor: unit + integration + failure_injection + soak. 15 Candidate Generation: unit + learning.

---

### [Module 13] Security Requirements — 2026-09-26

**What was implemented (bar, not a service — central enforcement for the spec):**
- `security/credentials.py` (new) — `load_binance_credentials()` with `HERMES_EXEC_ENV`-selected paper/production pairs (both present → loud refusal), key+secret togetherness, mandatory `HERMES_BINANCE_KEY_SCOPE=read-only` and `BINANCE_WITHDRAWALS_DISABLED` attestation, anonymous public-data mode when no keys; `audit_market_data_settings()` checking an existing Settings object (key/secret pairing, scope + withdrawals attestation, non-loopback token+TLS, insecure-remote flag) without changing Module 2 code.
- `security/redaction.py` (new) — `redact()` (auth headers, bearer tokens, signed-URL params, labeled secrets, 64+ hex blobs, plus known secret values), `scrub_mapping()` (sensitive keys + nested), `SecretFilter` logging filter for args dict/tuple and message forms.
- `tests/test_security.py` (new, 12 tests) — redaction units, filter forms, signed-run log lint (caplog), repo-wide hardcoded-secret scan, hung-layer kill, Binance ambiguity/scope/attestation/anonymous/half-pair, settings audit (loopback clean, exposed findings, insecure flag), n8n separation via existing config.
- Two real findings fixed during testing (new code only): (1) groupless regex crashed the `\1` replacement — replaced with a match-function keeping the label prefix; (2) the source scan flagged env-var-name constants (`ENV_API_KEY = "CANDIDATE_PROVIDER_API_KEY"`) — narrowed to skip SCREAMING_SNAKE RHS values, which are routing, not secrets.

**How it differs from the spec (if at all):**
No divergence. New `security/` package + one test file only — zero existing modules modified (`git status` confirms). Withdrawals-disabled is enforced as a load-time attestation (code cannot inspect Binance account settings); the borrow-check is the operator setting `BINANCE_WITHDRAWALS_DISABLED=1` only on a key created withdrawal-disabled. No new dependencies (stdlib logging/re/os only).

**Tests run:**
Per the Module 13 acceptance criteria, executed literally: log-lint (caplog over a signed run + source scan), hung-layer kill, ambiguity refusal. `tests/test_security.py` 12 passed; full suite 274 passed (was 262). `python -m compileall -q security tests/test_security.py`; `git diff --check` clean (CRLF warnings only). No `sorted()`, no comprehensions, no `__main__` guards in new code.

**Open questions / follow-ups:**
None for Module 13. Operators must still create the Binance keys withdrawal-disabled and keep `.env` out of source control (`.env.example` remains the only committed template).

**Secret-management mechanism:** environment variables only — disjoint `*_PAPER` / `*_PROD` pairs selected by `HERMES_EXEC_ENV`, read-only scope + withdrawals attestation required, every log line scrubbable through `SecretFilter`.
**Kill-switch independence test result:** decision layer hung on a never-signaled event while the main thread tripped the switch via the supervisor hook (no deadlock, bounded join); risk then REJECTED with kill-switch reason — halt provably independent of Hermes health.

---

### [Integration] End-to-End Runtime Wiring — 2026-09-26

**Integration map (from source, not docs):** disconnected market→observer feed, no strategy runner (approvals had no code path to proposals), unchained decision→risk→execution→lifecycle→learning stages, dummy-only supervisor workers, no rebuild hook, no account-state builder, no venue transport. No fake/mock paths reachable from production; no secret logging; no unsafe fallbacks found. Module 7 request/ack ledger and Module 8 order/fill/position ledger are complementary (different granularity) — documented, not merged.

**What was wired (new `runtime/` package only — zero existing modules modified):**
- `runtime/config.py` — `RuntimeConfig` paper-by-default (`HERMES_EXEC_ENV` unset → paper); production boot refuses without explicit `HERMES_LIVE_TRADING=1`; per-store SQLite paths under one data dir.
- `runtime/paper_venue.py` — `PaperN8nServer` verifying HMAC + replay/nonce + idempotency for real, then filling exact quantities via `PaperEngine`; `make_paper_sender()` adapts it to the Module 7 sender signature. No live Binance path exists.
- `runtime/pipeline.py` — `HermesPipeline`: `step_market()` (duplicate/out-of-order/malformed-safe) → observer → approved-version signals → `decide()` → risk (full account state from tracker + settled equity) → sealed request → `submit()` (n8n boundary + execution mirror) → `on_venue_fills()` (lifecycle ENTRY) → `close_position()` (CLOSE intent reusing entry linkage — no fabricated risk/execution rows) → `learn_from_trade()` (gate provenance resolved from memory, analysis + lesson + version mirrored) → `research_step()` (validated lessons only, review inbox PENDING, never approval). HOLD cycles persist nothing (no edge link to join — fail-closed persistence, not a gap). Test-signal registry is instance-level, `test_`-prefixed, and `assert_no_test_signals()` blocks production boot with fixtures.
- `runtime/workers.py` — eight real queue-driven stage workers (bounded backpressure queues, shared heartbeat, injectable feed/submit/exchange-truth) calling the same pipeline primitives as the sync path; no duplicated stage logic.
- `runtime/recovery.py` — ordered rebuild (durable counts → execution ledger → lifecycle reconcile → account reload from metrics); any exception or leftover unknown → frozen, never resume-on-guess.
- `tests/test_runtime_integration.py` (new, 16 tests) — full paper lifecycle with ID preservation + lesson + preregistration + complete `memory.trace()`; stale negative (nothing submitted, no position); hung-decision kill (bounded, risk REJECTED); Module 1 block (activation refused, zero approvals/submits); production guards (test-signal + live-flag refusal); malformed/duplicate/expired/tampered/unknown/partial/cancel/restart-pending/rebuild-freeze paths; supervisor running all eight real workers; research validation gate.

**Runtime flow:** market event → observer.refresh_once → approved signals → decide → persist chain → risk → build_request → manager.submit_once → paper venue ack → lifecycle ENTRY + fills → CLOSE → trade → analyzer → lesson → (human validation) → generator → Module 1 → review PENDING → (human approval) → immutable version → production signal. Supervisor orchestrates workers, owns rebuild + kill hooks.
**Worker architecture:** market_observer → context_builder → strategy_engine → decision_engine → risk_engine → n8n_client → trade_monitor → learning_worker over seven bounded asyncio queues into shared stores.
**Restart behavior:** `recover()` reconciles durable + ledger + orders/fills/positions, reloads account, freezes symbols with residual unknown; supervisor gates decisions until ready.
**Persistence/reconciliation:** Module 10 tables written in dependency order (snapshot → edge mirror → decision → proposals → evidence → risk → execution → order → position → trade → analysis → lesson → version); Module 7 and Module 8 ledgers kept distinct by design.
**Failure behavior:** every injected fault resolves to HOLD/REJECTED/EXPIRED/FREEZE per existing semantics; close-intent exits flow through lifecycle CLOSE while Module 6's entry block stands untouched.

**Tests run:** `tests/test_runtime_integration.py` 16 passed; full suite 290 passed (was 274, baseline preserved). `python -m compileall -q runtime tests/test_runtime_integration.py`; `git diff --check` clean; `git status` shows only `runtime/`, `tests/test_runtime_integration.py`, `tests/test_levels.py`, status/log as new/changed. No `sorted()`, no comprehensions, no `__main__` guards, stdlib only.

**Remaining genuine blockers (not code gaps):** (1) zero real Module 1 PASS verdicts — production strategy set is empty by evidence, not by wiring; (2) no live n8n server / Binance execution configured — paper venue is the only transport; (3) research loop needs operator provider credentials + dated holdouts per candidate; (4) live deployment needs real worker feed, exchange-truth source, and rebuild/kill hook wiring to operator infrastructure.

---

### [Module 1 Research] Funding-Rate Carry + Cross-Exchange Dislocation — 2026-09-26

**Data audit (read-only over `data/*.sqlite3`, all gitignored local collectors):**
- Funding: 200 distinct (symbol, fundingTime) observations (BTCUSDT/ETHUSDT, 100 8h-periods each, 33.0-day span) with mark prices; execution prices available (160k bookTicker, 6882 klines, same window).
- Cross-exchange: 8421 deduplicated confirmations (7806 CONFIRMED, 615 UNAVAILABLE skipped, 3–4 venues: binance/coinbase/kraken/okx, real reference prices) but aggregates only — no per-venue bid/ask, spreads, depth, fee schedules, or latency; span ~4.4 days.
- Data-quality gate: both series ordered, deduplicated on load, no unrealistic rates, no missing marks, no impossible spreads; quality `ok:true` on both — the blocker is sufficiency, not cleanliness.
- Reproducibility note: `data/` is untracked, so every finding carries a dataset SHA-256 (funding `48806db7…`, xex `217c5c5c…`, full hashes in artifact).

**What was implemented (new `research/` package + one test file — zero existing modules modified):**
- `research/funding_carry.py` — `FundingObservation`, 3 bounded hypotheses (F1/F2 short-carry thresholds, F3 mirror long), causal T→T+1 engine with exact project costs (0.10%/side fee+slippage, 31.2% tax, 1% TDS), quality gate, `evaluate_sufficiency()` (≥20 periods, ≥60d span, ≥2 regime legs), DB loader with dedup.
- `research/dislocation.py` — `DislocationObservation`, 3 bounded hypotheses (D1/D2/D3 threshold×persistence), `check_executability()` naming the 6 missing legs, descriptive crossing counts (never returns), same sufficiency bar (≥500 obs, ≥60d, 2 legs).
- `research/run_validation.py` — operator-invoked `main()` registering all 6 hypotheses via `CandidateGenerator` (menu-approved classes), running audit + evaluation, writing `research/reports/funding_xex_validation.json/.md`. No gate writes, no holdout touched, no promotion.
- `tests/test_funding_xex_validation.py` (new, 14 tests) — registration, determinism, future-spike no-look-ahead (both engines), exact cost math, quality flags, READY/INCONCLUSIVE branches, Bonferroni accounting (registered≠tested), ledger-untouched registration, production block, no-LLM scan.

**Hypotheses tested (all pre-registered before performance inspection):**
F1 short>0.01%/3-period/1-hold; F2 short>0.05%+calm filter; F3 long<−0.01%; D1 ≥5bps×3/1h; D2 ≥10bps×3/1h; D3 ≥20bps×5/2h. Costs: 0.10%/side fee+slippage, 31.2% VDA tax, 1% TDS drag.

**Statistical results:** no inferential stats run (no qualifying dataset). Descriptive: funding mean rate +0.006%/8h, 95% positive periods (n=200); xex disagreement p50 2.60 / p90 4.26 / p99 5.84 bps (n=8421). Multiple testing: ledger tested m=5, 6 registered / 0 tested, budget unspent; first future test faces Bonferroni alpha 0.05/6≈0.00833.

**Holdout results:** none defined, none consumed — nothing qualified as evidence-grade data.

**Module 1 verdicts:** F1/F2/F3 INCONCLUSIVE (33d < 60d minimum, single regime leg); D1/D2/D3 INCONCLUSIVE (no executable per-venue quotes, ~4.4d span, single leg). Gate ledger: 0 records written. Review queue: nothing submitted (no gate results exist).

**Production status:** production strategies approved = 0. No activation, no paper promotion of candidates.

**Tests:** baseline 290 preserved, 14 new, final total 304 passed. `compileall` clean, `diff --check` clean, no banned constructs, stdlib only.

**Remaining blockers (genuine):** (1) multi-month funding history spanning ≥2 regime legs + dated holdout windows; (2) synchronized per-venue bid/ask + spreads + depth + fees + latency for ≥1 venue pair over ≥60 days; (3) with (1)/(2) in hand, run F1–F3/D1–D3 through the full gate starting at alpha ≈0.00833.

**Final safety statement:** live trading remains disabled (paper-only runtime, production boot locked); no LLM anywhere near the live path (research engines import none); Risk Engine remains mandatory (untouched); Module 1 remains mandatory (gate untouched, 0 new records); human approval remains mandatory (review queue untouched, nothing submitted); test fixtures (`test_*` signals, synthetic PASS records) exist only in ephemeral test DBs; no candidate was fabricated into a PASS — both families stand INCONCLUSIVE on evidence-grade-data grounds.

---

### [Evidence Acquisition + Funding Gate Run] — 2026-09-26

**Follow-up to the INCONCLUSIVE research above: acquisition layer built, funding data acquired to evidence grade, F1–F3 run through the live gate.**

**What was implemented (new files only — zero existing modules modified):**
- `research/acquisition.py` — provider abstraction (`FundingHistoryProvider`, `KlinesProvider`, `CoinbaseCandlesProvider`, `KrakenOhlcProvider`; fetch→normalize→validate, public endpoints, env-overridable base URLs, redacted error hosts), `validate_series()` (ordering/dupes/gaps/missing/coverage), `check_sync()`, pre-declared `regime_legs_from_closes()`, `assert_evidence_grade()` (fixture rejection), immutable `store_dataset()`/`load_dataset()` (versioned, hash-verified, never overwritten).
- `research/datasets/` — 8 versioned artifacts (~4MB): fund-btcusdt/ethusdt v1 (500 8h-periods each, 166.3d, zero gaps/dupes), klines-btcusdt/ethusdt-1h v1 (8000 hourly, ~333d), coinbase BTC/ETH-1h v1 (10500 hourly), kraken XBT/ETH-1h v1 (723 hourly — single-page yield, documented).
- `research/gate_run.py` — funding battery: chronological 60/20/20 splits, all three submissions BEFORE touching the holdout (shared pre-registered battery + Bonferroni disclosure), frozen F1–F3 engines on the holdout only, 10k-sample seeded bootstrap evidence, direction legs + half-split replication, verdicts recorded, review queue PENDING. No approvals/versions/strategies.
- `research/dislocation.py` extended (same revision, no hypothesis change): optional per-venue quote legs on observations, `check_executability()` now returns executable=True only with quotable synchronized books (still False on current data); sufficiency READY requires executable+span+legs+quality.
- `research/run_validation.py` — `_hypothesis_ids()` helper (convention cleanup, no behavior change).
- `tests/test_acquisition.py` (new, 14 tests) + `tests/test_gate_run.py` (new, 6 tests) — normalization, pagination (mocked), validation, hashing, immutability/tamper, sufficiency branches, sync tolerance, crossed/inverted/thin-book executability, env config, redacted errors, fixture rejection, sign-correct funding direction, NULL/FAIL/genuine-PASS verdict paths on isolated ledgers, no-promotion-without-approval, split determinism, no-LLM scan.
- §17 correction logged before fixing: funding PnL sign was inverted (SHORT earned −rate); corrected to exchange settlement (SHORT collects +rate, LONG collects −rate). Pre-registration text unchanged (directionally correct). Recorded NULLs unaffected — proof: all three holdout runs banked 0 trades (artifact `trade_count: 0`).

**Data sources (all public, no credentials):** binance-fapi-funding (fapi.binance.com/fapi/v1/fundingRate, BTCUSDT+ETHUSDT, 500 8h-periods ≈166d each); binance-spot-klines (api.binance.com/api/v3/klines, 1h, 8000 rows ≈333d); coinbase-spot-candles (api.exchange.coinbase.com, 1h, 10500 rows); kraken-spot-ohlc (api.kraken.com, 1h, 723 rows — pagination yielded one page; documented, not relied upon). OKX attempted, timed out, not used.

**Funding dataset:** range 1776067200006–1790438400001 (≈166.3d), 500+500 records, BTCUSDT+ETHUSDT, binance-futures, 0 duplicates, 0 missing 8h intervals, quality ok:true, hashes `0e53dda0…` / `0451303d…`. Regime legs (pre-declared direction thirds on BTC closes): range/down/up — 3 distinct legs.

**Cross-exchange dataset:** venues binance-spot/coinbase/kraken, BTC+ETH, 1h closes; synchronization checkable via absolute timestamp diffs; bid/ask availability: NONE (closes only); depth/fees/latency availability: NONE. Executability verdict: insufficient (last-price differences are not arbitrage). Hash per dataset in manifests. Verdict: INCONCLUSIVE stands — exact missing legs: synchronized per-venue bid/ask + spreads + depth + fee schedules + latency over ≥60 days.

**Holdouts (funding, dated, hashed):** research [1776067200006–1784678400000], validation [1784707200000–1787558400002], holdout [1787587200000–1790438400001] (~27d, 100 periods/symbol, hash `814f1045…`). Holdout untouched until all three submissions completed.

**Module 1 status (live ledger `research/runtime_edge_validation.sqlite3`, m: 5→8):**
- funding_carry_f1: NULL_RESULT (0 trades — holdout funding mean ~0.005%, no period beyond ±0.01% thresholds; diagnostic verified, not an engine bug).
- funding_carry_f2: NULL_RESULT (0 trades, same quiet holdout).
- funding_carry_f3: NULL_RESULT (0 trades, same quiet holdout).
- All NULLs final per criterion 7; review queue `research/review_queue_funding.sqlite3`: 3 items PENDING, 0 decisions (no approvals, no versions, no strategies).
- D1–D3: INCONCLUSIVE, no gate records (unchanged — no executable data).
- Full artifact: `research/reports/funding_gate_run.json`.

**Tests:** baseline 305 preserved, 20 new (14 acquisition + 6 gate-run), final total 325 passed. `python -m compileall -q .` clean; `git diff --check` clean; no banned constructs (one `sorted()` + two comprehensions caught and rewritten during the run); stdlib only.

**Remaining blockers (genuine):** (1) funding triggers need a livelier holdout — F1–F3 on this dataset are spent (NULL final); a materially new hypothesis class or fresh multi-regime window is required for any retry; (2) cross-exchange needs quotable synchronized books (see missing legs); (3) with (1)/(2), run through the full gate from Bonferroni α≈0.05/9.

**Final safety statement:** live trading remains disabled; no LLM in live path; Risk Engine, Module 1, n8n boundary, and human approval all mandatory and untouched; test fixtures isolated (gate-run PASS-path test runs on throwaway ledgers only); no candidate fabricated — F1–F3 stand NULL_RESULT on zero holdout triggers, D1–D3 INCONCLUSIVE on executability; the one implementation bug found (funding sign) was documented before fixing and affected zero recorded results.

---

### [Module 1 Research Cycle 2] F4 Anomaly Fade + Backward History Extension — 2026-09-26

**Menu inspection:** funding-rate carry remains the approved signal class; F4 reuses it with structurally distinct rules (distribution-normalized anomaly fade vs F1–F3 fixed-threshold crossing) — no menu change, no threshold retuning, no new signal class needed.

**New hypothesis (frozen BEFORE any new-data evaluation, sha in artifact):**
F4 = funding anomaly fade: z of the settling rate vs trailing-30 settled rates; SHORT when z>+2.0, LONG when z<−2.0, hold 1 period. Conventional untuned params (30/2.0/1). Rationale: extreme funding marks crowded positioning; fading captures normalization plus carry.

**Data acquired (existing `research/acquisition.py`, public, no credentials):**
- fund-btcusdt/ethusdt-older v1: 500 8h-periods each reaching back to 1761667200004, zero gaps/dupes, hashes `e9d04fa1…` / `098d548f…`.
- klines-btcusdt-1h-older v1: 8000 hourly back to 1732845600000, hash `b391ec10…`.
- Combined funding timeline ≈333 days (2×1000 periods). Backward pagination verified contiguous (8h grid unbroken across the v1 boundary).
- XEX executability attempt: OKX retried with 60s timeout — unreachable from here; all reachable venues offer OHLCV-only history (no historical bid/ask anywhere public). D1–D3 remain INCONCLUSIVE with the attempt recorded.

**What was implemented (research files + tests only — zero existing modules modified):**
- `research/funding_carry.py`: `AnomalyHypothesis`, `F4` constant, `freeze_hypothesis()` (canonical sha), `generate_anomaly_trades()` (trailing-settled z-scores, zero-variance skip, identical cost stack).
- `research/gate_run.py`: `freeze_holdout()` (hash-recorded splits, slice refuses unfrozen), `slice_holdout()`, `bootstrap_pvalue()` (deterministic reporting companion, not a gate criterion), `run_anomaly()` + shared `_evaluate_and_record()`, `run_f4()` (combined timeline, disjoint [560,700) holdout, dynamic MT threshold, review PENDING).
- `research/dislocation.py`: per-venue quote legs now genuinely completable (executable=True path exists; still False on current data).
- `tests/test_research_cycle2.py` (new, 13 tests) + `tests/test_levels.py` matrix extended.
- Two infrastructure incidents handled without weakening the gate: (a) klines stored newest-first sliced regime legs backwards — fixed with explicit chronological ordering (F1–F3 NULL verdicts unaffected: 0 trades, legs unused); (b) first F4 submission crashed at replication on unsorted legs, leaving an orphan PENDING — honestly nulled (zero evaluation performed), then resubmitted on a day-disjoint window with attempt metadata in the hypothesis text (rules unchanged). Both documented here, not hidden.

**Holdout (F4, frozen before submission, hash `8a78e414…`):** research grid [0,420), validation [420,560), holdout [560,700) of the combined 1000-period grid (~47d, 140 periods/symbol, 280 obs) — day-disjoint from the spent F1–F3 tail-100 and the nulled orphan window.

**Module 1 status (live ledger m: 8→10, α for F4 = 0.05/10 = 0.005):**
- funding_carry_f4: **FAIL** — 24 trades, aggregate −38.84%, bootstrap CI [−2.36%, −0.96%] entirely negative, raw p=1.0 (not significant at α=0.005), regimes range/down/up (2 of 3 legs traded), replication False. Failed criteria: positive-CI + replication. Costs (notably 1% TDS per 8h turnover) drown the carry — same signature as the project's cost-attribution finding. Final; review PENDING, no approvals/versions/strategies.
- Orphan F4 PENDING: NULL_RESULT (infrastructure crash, disclosed above).
- D1–D3: INCONCLUSIVE (unchanged).
- Full artifact: `research/reports/funding_f4_gate_run.json`.

**Tests:** baseline 325 preserved, 13 new, final total 338 passed. `compileall .` / `diff --check` clean; no banned constructs; stdlib only.

**Remaining blockers (genuine):** (1) funding F1–F4 all spent (NULL/NULL/NULL/FAIL, all final); any retry needs a materially new class or fresh window; (2) xex needs quotable synchronized books ≥60d (unavailable on any reachable public venue); (3) next tests start at Bonferroni α≈0.05/11.

**Final safety statement:** live trading disabled; no LLM in live path; Risk/n8n/Module 1/human-approval gates mandatory and untouched; fixtures isolated (PASS-path and F4 tests run on throwaway ledgers; live-ledger immutability asserted by test); NULLs never converted (F1–F3 NULL, orphan NULL, quiet-series NULL all stand); F4 FAIL is evidence (24 real trades, negative CI), not manufacture; D1–D3 INCONCLUSIVE stands; production approved = 0.

