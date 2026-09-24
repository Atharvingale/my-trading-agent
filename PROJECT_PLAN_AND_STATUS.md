# Crypto Market-Data Platform: Initial Plan and Maintained Status

Last updated: 2026-09-22 13:14 IST
Project root: `D:\my-trading-app`

This document is the maintained record of the original goals, actual implementation, deviations from the original plan, remaining work, and verification status. Update the sections below whenever a requirement is completed, changed, or intentionally rejected.

## 1. Original objective

The original objective was to build a clean-slate, continuously running crypto market-data and analysis platform that could:

1. Collect broad cryptocurrency market data, not only BTC.
2. Collect detailed realtime and historical Binance data.
3. Cover BTC, ETH, and dynamically selected liquid/trending coins that may offer better opportunities.
4. Analyze supply, demand, liquidity, market structure, price action, order flow, derivatives, options, funding, open interest, liquidations, and related market context.
5. Produce structured BUY, SELL, or HOLD information with targets, risk context, and reasons.
6. Run continuously 24/7 with reconnect logic, durable storage, monitoring, and failure handling.
7. Optionally read private Binance balances, positions, orders, and account events only when the user provides API credentials.
8. Return `N/A` for private data when credentials are not provided.
9. Feed information to Hermes and downstream automation such as n8n through a realtime endpoint.
10. Eventually support a controlled continuous loop: collect data, analyze, generate a decision, optionally trigger automation, execute under safeguards, evaluate closed trades, and learn from outcomes.
11. Use free data sources that provide meaningful analytical value.
12. Preserve local privacy and avoid sending private research, prompts, strategies, portfolios, or credentials to external analytics services.
13. Prevent an AI component from directly and unrestrictedly controlling exchange execution.
14. Avoid claiming guaranteed profits. The goal is risk-adjusted research and survival, not a promise of profitability.

## 2. Current architecture

The project currently contains:

- `main.py`: unified startup command.
- `binance_data_layer/collector.py`: Binance streams, REST analytics, state, dynamic universe, persistence, reconnects, and private-data gating.
- `binance_data_layer/binance_client.py`: public REST methods and conditional signed/private methods.
- `binance_data_layer/breadth.py`: all-market ticker normalization, breadth calculations, and dynamic symbol ranking.
- `binance_data_layer/technical.py`: deterministic closed-candle indicators.
- `binance_data_layer/features.py`: order-flow, spread, imbalance, and feature snapshots.
- `binance_data_layer/execution.py`: deterministic depth/fill/slippage estimates.
- `binance_data_layer/quality.py`: freshness, duplicate, ordering, and sequence-quality checks.
- `binance_data_layer/cross_exchange.py`: Coinbase, Kraken, and OKX public ticker adapters and confirmation logic.
- `binance_data_layer/storage.py`: SQLite schema and persistence.
- `binance_data_layer/api.py`: local read-only REST and WebSocket API.
- `data/market_data.sqlite3`: default persistent database.

Default startup:

```bash
cd /d D:\my-trading-app
python main.py
```

The process starts the collector and the local API together.

## 3. Accomplished

### 3.1 Binance public market collection

Implemented and integrated:

- Spot aggregate trades.
- Spot book ticker.
- Spot partial depth/order-book data.
- Spot 1m, 5m, 15m, 1h, and 4h candles.
- Spot 24-hour ticker data.
- Spot exchange metadata.
- USD-M Futures mark/index price.
- Funding rate and funding history.
- Open interest and open-interest history.
- Liquidation events.
- Global long/short account ratios.
- Taker buy/sell volume.
- Futures basis.
- Futures candles and ticker data.
- Binance Options mark price, IV, Greeks, open interest, and block trades.
- REST bootstrap and recurring analytics snapshots.

Official endpoint corrections completed:

- Binance Spot all-market breadth uses `!miniTicker@arr`.
- Binance Futures market routing uses `/market/stream`.
- Binance Futures private routing uses `/private/ws?listenKey=...`.
- Partial depth payloads support `lastUpdateId`, `bids`, and `asks`.
- Options IV fields map to bid IV, ask IV, mark IV, and risk-free rate correctly.
- Signed requests use Binance server-time synchronization and a bounded `recvWindow`.
- Private listen keys have periodic keepalive handling.

### 3.2 Dynamic top/trending coin coverage

The system now collects more than BTC and ETH.

The official Binance all-market mini-ticker stream is used to discover candidates. The selector:

- Keeps configured symbols pinned.
- Ranks additional symbols by absolute 24-hour price movement and quote volume.
- Applies a minimum quote-volume threshold.
- Supports explicit symbol exclusions.
- Rejects malformed/nonstandard symbol names before creating subscriptions.
- Adds selected symbols to detailed spot streams.
- Adds selected symbols to detailed futures mark-price streams.
- Reconnects the Binance streams when the selected universe changes.
- Publishes the new universe through the realtime API.

Default configuration:

```text
DYNAMIC_UNIVERSE_ENABLED=1
DYNAMIC_UNIVERSE_SIZE=20
DYNAMIC_MIN_QUOTE_VOLUME=5000000
DYNAMIC_REFRESH_SECONDS=300
DYNAMIC_EXCLUDED_SYMBOLS=
```

The ranking is candidate discovery, not a prediction of profit. A large move can represent opportunity or elevated risk.

### 3.3 Breadth and market context

Implemented:

- Advancing, declining, and unchanged counts.
- Advance/decline ratio.
- Advancing percentage.
- Aggregate quote volume.
- Top-volume concentration.
- Stablecoin-base filtering.
- Separate breadth snapshots in SQLite.
- Spot and Futures all-market mini-ticker ingestion.

### 3.4 Technical, order-flow, and execution features

Implemented:

- Returns.
- EMA and fast/slow EMA relationships.
- RSI.
- ATR.
- VWAP.
- Bollinger bandwidth.
- Volume ratio.
- Multi-timeframe alignment.
- Closed-candle-only technical calculations.
- Rolling CVD.
- Aggressive-buy percentage.
- Large-trade quantity and concentration.
- Spread stability.
- Depth within 5, 10, and 25 basis points.
- Estimated fill price.
- Estimated slippage and price impact.
- Insufficient-depth detection.
- Execution-quality estimates for both BUY and SELL directions.

### 3.5 Quality and fail-closed behavior

Implemented detection for:

- Duplicate events.
- Out-of-order events.
- Depth sequence gaps.
- Stale data.
- Missing data.
- Reconnect/error health states.

Unreliable inputs are intended to result in non-actionable/HOLD-style downstream behavior rather than fabricated confidence.

### 3.6 Cross-exchange confirmation

Implemented public adapters for:

- Coinbase Advanced Trade.
- Kraken Spot WebSocket v2.
- OKX public WebSocket.

The confirmation layer includes Binance as the reference source and evaluates:

- Fresh source count.
- Reference price.
- Cross-source disagreement in basis points.
- Confirmation status.

Confirmation is fail-closed when the required fresh sources are unavailable or disagree beyond the configured tolerance.

### 3.7 Private Binance data safeguards

Implemented conditional private collection for:

- Spot balances.
- Spot open orders.
- Futures account state.
- Futures positions.
- Futures open orders.
- Spot and Futures user-data streams.
- Reconciliation snapshots.

When either credential is missing:

```json
{
  "status": "N/A",
  "reason": "BINANCE_API_CREDENTIALS_NOT_PROVIDED"
}
```

No authenticated request or private socket is attempted without both credentials. Credentials are not logged or stored in the repository. The current implementation remains read-only and does not place, cancel, or modify orders.

### 3.8 Realtime API

Implemented local read-only REST endpoints:

```text
GET /health
GET /market/{symbol}/snapshot
GET /market/{symbol}/features
GET /market/top-coins
GET /breadth/latest
GET /cross-exchange/{symbol}
GET /data-health
GET /events?symbol=BTCUSDT&limit=100
```

Default base URL:

```text
http://127.0.0.1:8000
```

Implemented push WebSocket:

```text
ws://127.0.0.1:8000/ws?symbol=BTCUSDT
ws://127.0.0.1:8000/ws
```

The WebSocket publishes live:

- `market_event`.
- `breadth`.
- `cross_exchange_confirmation`.
- `universe_update`.

The API is read-only. It does not expose order placement, cancellation, withdrawal, or account mutation routes.

### 3.9 Verification completed

Latest recorded verification:

```text
65 tests passed
Python compilation passed
```

Live checks completed:

- Local API returned HTTP 200 for `/health`.
- Local API returned HTTP 200 for `/breadth/latest`.
- WebSocket accepted a client and delivered a live market event.
- `/market/top-coins` returned dynamically ranked symbols.
- Detailed Spot and Futures stream URLs included dynamically selected symbols.

## 4. Remaining work

### Priority 1: signal and analysis layer

Not yet completed:

- A formal deterministic BUY/SELL/HOLD signal engine.
- A documented signal schema with entry, invalidation, target, confidence, and reason codes.
- Regime classification combining breadth, trend, volatility, derivatives, and cross-exchange context.
- Multi-horizon scoring rather than relying primarily on 24-hour movement.
- Backtesting with fees, spread, slippage, latency, and survivorship-bias controls.
- Walk-forward and out-of-sample validation.
- Paper-trading evaluation before any live execution.

### Priority 2: dynamic universe quality improvements

The current selector is deliberately simple and explainable. It should be extended with:

- Multi-window momentum instead of only absolute 24-hour movement.
- Relative volume acceleration.
- Spread and depth thresholds before admission.
- Estimated slippage for a configured notional.
- Data-freshness and quality gating before admission.
- Abnormal-move and liquidation-spike filters.
- Listing-age and trading-status checks from exchange metadata.
- Separate ranking for momentum, mean reversion, and breakout candidates.
- Hysteresis/cooldown rules to reduce universe churn.
- Persistence of inclusion/exclusion reasons for later analysis.

### Priority 3: external free data sources

Not yet integrated:

- Macro-economic calendar and rates data.
- News and official project announcements.
- Sentiment sources.
- On-chain metrics.
- Token unlocks and supply changes.
- BTC dominance and global crypto market capitalization.
- DeFi/stablecoin liquidity data.
- Fear-and-greed style sentiment indexes.
- Mempool and network-fee data.

These require separate source adapters. They should remain optional, rate-limited, cited, and privacy-safe.

### Priority 4: continuous learning and trade review

Not yet completed:

- Closed-trade journal schema.
- Decision/reasoning snapshot storage.
- Feature snapshot at entry and exit.
- Mistake taxonomy.
- Post-trade attribution.
- Strategy versioning.
- Offline evaluation loop that prevents repeating known mistakes.
- Safe model/parameter promotion process.

Learning must not silently rewrite production behavior. Any new strategy or parameter set requires evaluation and explicit promotion.

### Priority 5: automation and execution integration

Not yet completed:

- n8n webhook contract.
- Signed decision payloads and idempotency keys.
- Paper-trading execution adapter.
- Binance testnet adapter.
- Deterministic risk service.
- Position sizing and portfolio exposure limits.
- Daily loss, drawdown, and kill-switch controls.
- Human approval mode.
- Auditable execution records.

Live order execution is intentionally not part of the current collector.

### Priority 6: operational hardening

Remaining operational work:

- Service manager configuration for automatic restart.
- Health monitoring and alert delivery.
- Log rotation.
- Database backup and retention policy.
- SQLite maintenance/compaction strategy.
- API authentication if exposed beyond localhost.
- Rate-limit and resource monitoring.
- Integration tests covering long-lived reconnects.
- Deployment documentation for a 24/7 host.

## 5. What was done differently from the original plan

1. The original idea included a full automated loop that could decide, trigger n8n, execute on Binance, review trades, and learn continuously. Implementation deliberately stopped at a read-only market-data, feature, quality, and API layer. This reduces financial and operational risk until the signal and execution layers are validated.

2. The original plan discussed broad crypto-market collection. Implementation began with Binance as the primary authoritative source instead of integrating every external source immediately. This produced a stable foundation before adding optional macro, news, sentiment, and on-chain adapters.

3. The original plan focused on all available data. Implementation prioritized high-value Phase 1 data first: breadth, technical features, order flow, execution estimates, quality checks, and cross-exchange confirmation. Lower-confidence or lower-priority sources were deferred.

4. The original plan anticipated a realtime endpoint, but the first collector implementation stored data in SQLite without an HTTP server. A local read-only REST API and WebSocket were added later and are now integrated into the same `python main.py` process.

5. The original plan expected top/trending coin coverage. The initial implementation was configured mainly for BTCUSDT and ETHUSDT. Dynamic discovery was then added using Binance's all-market mini-ticker stream, with pinned symbols plus liquid movers.

6. The first dynamic ranking implementation used a transparent baseline—absolute 24-hour movement plus quote volume—instead of claiming to identify the most profitable assets. More robust multi-window and execution-aware ranking remains future work.

7. The original plan included AI-driven analysis. The current implementation uses deterministic calculations and does not allow an AI model to directly control orders. This is intentional until data quality, signal validity, and risk controls are proven.

8. The original plan included private Binance information when available. The implementation goes further on safety: private collection is completely disabled without both credentials and returns an explicit `N/A` record rather than guessing or fabricating values.

9. Cross-exchange confirmation was added even though it was not part of the minimum Binance-only collector. It provides context and disagreement detection, not an automatic arbitrage or trading decision.

10. The implementation uses SQLite and an in-memory live-state cache rather than sending private data to external cloud analytics. This matches the local-privacy requirement and keeps the realtime API fast.

## 6. Explicit non-goals and safeguards

- No guaranteed profit claim.
- No assumption that the largest price mover is the best trade.
- No order placement from the collector.
- No withdrawal capability.
- No private-data request without credentials.
- No fabricated macro, sentiment, on-chain, or tokenomics fields.
- No signal considered reliable when required data is stale, contradictory, or insufficient.
- No external cloud analytics for private strategies, prompts, portfolios, or research.

## 7. Maintenance procedure

Update this document whenever any of the following occurs:

1. A requirement is added, removed, or redefined.
2. A module or endpoint becomes operational.
3. A limitation is discovered or resolved.
4. A source, schema, ranking rule, or safety rule changes.
5. Verification status changes.

For every update:

- Change `Last updated`.
- Add a short entry to the changelog below.
- Update the relevant accomplished or remaining section.
- Record the exact test command and result when behavior changes.
- Record live verification separately from unit-test verification.
- Never mark a feature complete based only on code existence; exercise it.

## 8. Maintenance changelog

### 2026-09-22

- Added graceful Ctrl+C handling through `run_asyncio_entrypoint`.
- Both `python main.py` and `python -m binance_data_layer.collector` now stop without exposing an asyncio cancellation traceback.
- Added a regression test for CLI interrupt handling.
- Verification: 66 tests passed; Python compilation passed.

Future entries should use this format:

```text
### YYYY-MM-DD

- Change:
- Reason:
- Verification:
- Remaining impact:
```
