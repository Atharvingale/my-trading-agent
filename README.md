# Realtime Crypto Market-Data Platform

A continuously running, read-only crypto market-data collector for Binance Spot, USDⓈ-M Futures, and Options, with dynamic liquid/trending-coin discovery, SQLite persistence, deterministic market features, data-quality checks, cross-exchange confirmation, and a local REST/WebSocket API.

Project root:

```text
D:\my-trading-app
```

This implementation does not place, cancel, or modify orders. It does not guarantee profit. Dynamic coins are candidates for analysis, not guaranteed profitable trades.

## Quick start

From Git Bash:

```bash
cd /d/my-trading-app
python main.py
```

From Windows Command Prompt:

```bat
cd /d D:\my-trading-app
python main.py
```

The single command starts:

- Binance Spot WebSocket collection.
- Binance USDⓈ-M Futures WebSocket collection.
- Binance REST bootstrap and recurring analytics.
- Dynamic top/trending-coin discovery.
- SQLite persistence.
- Local read-only HTTP API.
- Local realtime WebSocket API.
- Optional Coinbase, Kraken, and OKX public ticker collection.
- Optional private Binance read-only collection when credentials are supplied.

Default local API:

```text
http://127.0.0.1:8000
```

The process must remain running for the local endpoints to remain available. Press Ctrl+C once to stop it cleanly.

## Requirements

- Python 3.11 or newer.
- Network access to Binance and, when enabled, Coinbase/Kraken/OKX.
- Dependencies from `requirements.txt`:

```text
aiohttp>=3.9,<4
websockets>=15,<16
pytest>=8,<10
```

Install dependencies if required:

```bash
python -m pip install -r requirements.txt
```

## Local API

The API is local and read-only by default. It binds to `127.0.0.1:8000` and is not intended to be exposed directly to the public Internet without authentication and network controls.

Configure the bind address and port with:

```text
MARKET_DATA_API_HOST=127.0.0.1
MARKET_DATA_API_PORT=8000
```

### REST endpoint summary

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Not implemented; returns HTTP 404. Use `/health`. |
| GET | `/health` | Confirms that the local API process is running. |
| GET | `/market/top-coins` | Returns the current pinned plus dynamically ranked universe. |
| GET | `/market/{symbol}/snapshot` | Returns the current in-memory feature snapshot for a symbol. |
| GET | `/market/{symbol}/features` | Alias of the symbol snapshot endpoint. |
| GET | `/breadth/latest` | Returns the newest all-market breadth snapshot. |
| GET | `/cross-exchange/{symbol}` | Returns the newest stored cross-exchange confirmation for a symbol. |
| GET | `/data-health` | Returns recent collector/API health records. |
| GET | `/events` | Returns recent persisted market events. |

The API does not expose order placement, order cancellation, withdrawals, account mutation, or trading execution routes.

### `GET /health`

Example:

```bash
curl http://127.0.0.1:8000/health
```

Response:

```json
{
  "status": "ok",
  "service": "crypto-market-data",
  "timestamp_ms": 1790062848582
}
```

This endpoint reports local API availability. It does not by itself guarantee that Binance is reachable. Check `/data-health` for upstream connection states.

### `GET /market/top-coins`

Returns the current detailed-collection universe.

```bash
curl http://127.0.0.1:8000/market/top-coins
```

Response shape:

```json
{
  "symbols": [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT"
  ],
  "generation": 2,
  "ranked_rows": [
    {
      "symbol": "SOLUSDT",
      "price": 120.0,
      "open": 100.0,
      "change_pct": 20.0,
      "quote_volume": 10000000.0,
      "event_time_ms": 1790062821002
    }
  ],
  "timestamp_ms": 1790062857324,
  "method": "absolute_24h_change_then_quote_volume_with_pinned_symbols"
}
```

Selection behavior:

1. Configured symbols are pinned and retained.
2. Binance all-market `!miniTicker@arr` data is normalized.
3. Symbols below `DYNAMIC_MIN_QUOTE_VOLUME` are excluded.
4. Symbols in `DYNAMIC_EXCLUDED_SYMBOLS` are excluded.
5. Invalid/nonstandard symbol names are excluded.
6. Remaining symbols are ranked by absolute 24-hour percentage change, then quote volume.
7. Up to `DYNAMIC_UNIVERSE_SIZE` symbols are selected.
8. Spot and Futures detailed WebSocket subscriptions are rebuilt when the universe generation changes.

This is a transparent candidate-discovery rule. It is not a profitability prediction.

### `GET /market/{symbol}/snapshot`

Returns the latest in-memory state for a collected symbol.

Example:

```bash
curl http://127.0.0.1:8000/market/BTCUSDT/snapshot
```

The response contains the symbol state and feature snapshot, including available fields such as:

- Symbol.
- Event time.
- Latest price.
- Best bid and ask.
- Bid/ask quantities.
- Spread and spread basis points.
- Order-book imbalance.
- Recent trade statistics.
- Aggressive-buy percentage.
- Rolling CVD.
- Large-trade statistics.
- Depth within 5, 10, and 25 basis points.
- Technical values by timeframe.
- Multi-timeframe alignment.
- Execution estimates for BUY and SELL.
- Data-health status.

A symbol that is not present in the current in-memory state returns HTTP 404:

```json
{
  "error": "unknown_symbol",
  "symbol": "UNKNOWNUSDT"
}
```

Technical indicators use closed candles only. Missing or stale values are not fabricated.

### `GET /market/{symbol}/features`

This is an alias of `/market/{symbol}/snapshot`:

```bash
curl http://127.0.0.1:8000/market/ETHUSDT/features
```

### `GET /breadth/latest`

Returns the newest market breadth snapshot derived from Binance all-market ticker data.

```bash
curl http://127.0.0.1:8000/breadth/latest
```

Response fields include:

```json
{
  "eligible_count": 160,
  "advancing_count": 121,
  "declining_count": 39,
  "unchanged_count": 0,
  "advance_decline_ratio": 3.1025,
  "advancing_pct": 0.75625,
  "aggregate_quote_volume": 77206232546.7177,
  "top_volume_concentration": 0.8204,
  "timestamp_ms": 1790062857324
}
```

If no breadth data has been received:

```json
{
  "status": "N/A",
  "reason": "NO_BREADTH_DATA"
}
```

### `GET /cross-exchange/{symbol}`

Returns the latest stored cross-exchange confirmation record.

```bash
curl http://127.0.0.1:8000/cross-exchange/BTCUSDT
```

The confirmation layer uses public data from:

- Binance.
- Coinbase Advanced Trade.
- Kraken Spot WebSocket v2.
- OKX public WebSocket.

It reports values such as:

- Fresh source count.
- Reference price.
- Disagreement in basis points.
- Confirmation status.

If no confirmation exists:

```json
{
  "status": "N/A",
  "reason": "NO_CROSS_EXCHANGE_DATA",
  "symbol": "BTCUSDT"
}
```

Cross-exchange confirmation is context, not automatic arbitrage or a trade signal.

### `GET /data-health`

Returns recent health records for:

- Spot WebSocket.
- Futures WebSocket.
- Binance REST analytics.
- Futures REST metrics.
- Local API.
- Cross-exchange sources.
- Private account and user streams.

```bash
curl http://127.0.0.1:8000/data-health
```

Records include:

```json
{
  "component": "spot_websocket",
  "symbol": null,
  "status": "connected",
  "observed_time_ms": 1790062857324,
  "details": {
    "url": "wss://stream.binance.com:9443/stream?..."
  }
}
```

Connection errors are recorded and the collector retries with backoff.

### `GET /events`

Returns persisted normalized events from SQLite.

All recent events:

```bash
curl "http://127.0.0.1:8000/events?limit=100"
```

Events for one symbol:

```bash
curl "http://127.0.0.1:8000/events?symbol=BTCUSDT&limit=100"
```

The maximum returned limit is 500. Each record contains:

- `stream`.
- `symbol`.
- `event_type`.
- `event_time_ms`.
- `received_time_ms`.
- Normalized `payload`.

## Realtime WebSocket API

Connect to one symbol:

```text
ws://127.0.0.1:8000/ws?symbol=BTCUSDT
```

Connect to all symbols and derived events:

```text
ws://127.0.0.1:8000/ws
```

The first message is:

```json
{
  "type": "connected",
  "symbol": "BTCUSDT",
  "timestamp_ms": 1790062861423
}
```

Message types:

### `market_event`

Published for normalized high-frequency market events such as trades, book ticker, depth, mark price, and candles.

```json
{
  "type": "market_event",
  "symbol": "BTCUSDT",
  "event_type": "bookTicker",
  "event_time_ms": 1790062861423,
  "payload": {}
}
```

### `breadth`

Published when an all-market breadth snapshot is processed.

```json
{
  "type": "breadth",
  "event_time_ms": 1790062861423,
  "payload": {}
}
```

### `cross_exchange_confirmation`

Published when a normalized cross-exchange ticker updates a symbol’s confirmation state.

```json
{
  "type": "cross_exchange_confirmation",
  "symbol": "BTCUSDT",
  "event_time_ms": 1790062861423,
  "payload": {}
}
```

### `universe_update`

Published when the dynamic detailed-collection universe changes.

```json
{
  "type": "universe_update",
  "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
  "rows": [],
  "generation": 2,
  "timestamp_ms": 1790062861423
}
```

A WebSocket subscription with `?symbol=BTCUSDT` receives BTCUSDT-specific messages plus messages without a symbol, such as breadth and universe updates. A subscription without a symbol receives all published messages.

## Binance data collected

### Spot WebSocket data

For each configured or dynamically selected Spot symbol:

- Aggregate trades: price, quantity, trade ID, and aggressor side.
- Best bid/ask: price and quantity.
- Partial order-book depth.
- 1m candles.
- 5m candles.
- 15m candles.
- 1h candles.
- 4h candles.

Market-wide Spot breadth:

```text
!miniTicker@arr
```

### USDⓈ-M Futures WebSocket data

For each configured or dynamically selected Futures symbol:

- Mark price.
- Index price.
- Funding rate.
- Next funding time.
- Force-order/liquidation stream.

Market-wide Futures breadth:

```text
!miniTicker@arr
```

### Binance REST analytics

The collector periodically stores:

- Spot exchange information.
- Spot 24-hour ticker data.
- Futures 24-hour ticker data where requested.
- Futures mark price.
- Futures open interest.
- Futures funding history.
- Futures global long/short account ratio.
- Futures taker buy/sell ratio.
- Futures open-interest history.
- Futures basis and basis rate.
- Spot and Futures candles.
- Options mark price.
- Options bid IV.
- Options ask IV.
- Options mark IV.
- Options Greeks where supplied by Binance.
- Options open interest by underlying and expiration.
- Options block trades.

The recurring analytics cycle runs approximately every five minutes. Futures metrics run approximately every 60 seconds. High-frequency WebSocket collection remains continuous.

## Derived features

### Technical indicators

Calculated from closed candles:

- Returns.
- EMA.
- Fast/slow EMA relationship.
- RSI.
- ATR.
- VWAP.
- Bollinger bandwidth.
- Volume ratio.
- Multi-timeframe alignment.

Intervals:

```text
1m, 5m, 15m, 1h, 4h
```

### Order flow and liquidity

- Rolling CVD.
- Aggressive-buy percentage.
- Large-trade quantity.
- Large-trade concentration.
- Bid/ask spread.
- Spread stability.
- Order-book imbalance.
- Available depth within 5 bps.
- Available depth within 10 bps.
- Available depth within 25 bps.

### Execution estimates

For a requested direction and quantity, the deterministic execution layer estimates:

- Filled quantity.
- Average fill price.
- Remaining quantity.
- Slippage.
- Price impact.
- Depth sufficiency.
- BUY/SELL execution quality.

These are estimates from observed public order-book data, not orders sent to Binance.

### Quality controls

The quality layer tracks:

- Duplicate events.
- Out-of-order events.
- Depth sequence gaps.
- Event freshness.
- Stale state.
- Missing data.
- WebSocket connection failures.
- REST collection failures.

Downstream logic should treat stale, incomplete, contradictory, or insufficient data as non-actionable/HOLD rather than inventing values.

## SQLite storage

Default database:

```text
data/market_data.sqlite3
```

Override:

```text
MARKET_DATA_DB=data/custom.sqlite3
```

Tables:

### `market_events`

Normalized Spot, Futures, Options, REST, private, cross-exchange, and derived events.

Columns:

```text
id
stream
symbol
event_type
event_time_ms
received_time_ms
payload_json
```

### `feature_snapshots`

Feature snapshots generated from current symbol state.

Columns:

```text
id
symbol
event_time
created_time_ms
payload_json
```

### `breadth_snapshots`

Market-wide breadth calculations.

Columns:

```text
id
created_time_ms
payload_json
```

### `data_health`

Collector and connection health records.

Columns:

```text
id
component
symbol
status
observed_time_ms
details_json
```

## Dynamic universe configuration

The dynamic universe is enabled by default:

```text
DYNAMIC_UNIVERSE_ENABLED=1
DYNAMIC_UNIVERSE_SIZE=20
DYNAMIC_MIN_QUOTE_VOLUME=5000000
DYNAMIC_REFRESH_SECONDS=300
DYNAMIC_EXCLUDED_SYMBOLS=
```

Recommended behavior:

- Keep BTCUSDT and ETHUSDT pinned unless there is a reason not to.
- Set `DYNAMIC_UNIVERSE_SIZE` according to available bandwidth and CPU.
- Increase `DYNAMIC_MIN_QUOTE_VOLUME` to avoid thin markets.
- Add symbols to `DYNAMIC_EXCLUDED_SYMBOLS` when they are unsuitable for analysis.
- Do not interpret the ranked list as a guaranteed-profit list.

The current baseline rank uses absolute 24-hour movement followed by quote volume. Future improvements are documented in `PROJECT_PLAN_AND_STATUS.md`.

## General configuration

All supported environment variables:

```text
BINANCE_API_KEY=
BINANCE_API_SECRET=

BINANCE_SYMBOLS=BTCUSDT,ETHUSDT
MARKET_DATA_DB=data/market_data.sqlite3
BINANCE_DEPTH_LEVELS=20
TRADE_BUFFER_SIZE=500
SNAPSHOT_INTERVAL=5
STALE_AFTER_SECONDS=30

ENABLE_MARKET_BREADTH=1
BREADTH_QUOTE_ASSETS=USDT,USDC,FDUSD
BREADTH_TOP_N=10
BREADTH_EXCLUDE_STABLECOIN_BASE=1

ENABLE_CROSS_EXCHANGE=1
CROSS_EXCHANGE_MAX_AGE_SECONDS=10

DYNAMIC_UNIVERSE_ENABLED=1
DYNAMIC_UNIVERSE_SIZE=20
DYNAMIC_MIN_QUOTE_VOLUME=5000000
DYNAMIC_REFRESH_SECONDS=300
DYNAMIC_EXCLUDED_SYMBOLS=

MARKET_DATA_API_HOST=127.0.0.1
MARKET_DATA_API_PORT=8000
```

Use `.env.example` as the configuration template. The collector reads environment variables; it does not require a `.env` loader.

Git Bash example:

```bash
export BINANCE_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
export DYNAMIC_UNIVERSE_SIZE=20
export DYNAMIC_MIN_QUOTE_VOLUME=5000000
export MARKET_DATA_API_PORT=8000
python main.py
```

Windows Command Prompt example:

```bat
set BINANCE_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
set DYNAMIC_UNIVERSE_SIZE=20
set DYNAMIC_MIN_QUOTE_VOLUME=5000000
set MARKET_DATA_API_PORT=8000
python main.py
```

## Optional private Binance data

Private collection is disabled unless both values are provided:

```text
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
```

When both are available, the read-only private layer can collect:

- Spot account balances.
- Spot open orders.
- USDⓈ-M Futures account and wallet state.
- USDⓈ-M Futures positions.
- Futures open orders.
- Spot user-data events.
- Futures user-data events.
- Account updates.
- Order updates.
- Execution reports.
- Periodic reconciliation snapshots.

When either credential is missing:

- No signed request is attempted.
- No private listen key is requested.
- No private WebSocket is opened.
- A safe status record is stored:

```json
{
  "status": "N/A",
  "reason": "BINANCE_API_CREDENTIALS_NOT_PROVIDED"
}
```

Credential rules:

- Never commit credentials to Git.
- Use keys with withdrawals disabled.
- Use the narrowest permissions possible.
- Do not print keys, secrets, signatures, or private headers in logs.
- The collector never places, cancels, or modifies orders.

## External Binance endpoints used internally

Spot REST:

```text
https://api.binance.com/api/v3/time
https://api.binance.com/api/v3/exchangeInfo
https://api.binance.com/api/v3/account
https://api.binance.com/api/v3/openOrders
https://api.binance.com/api/v3/userDataStream
https://api.binance.com/api/v3/ticker/24hr
https://api.binance.com/api/v3/depth
https://api.binance.com/api/v3/klines
```

Spot WebSocket:

```text
wss://stream.binance.com:9443/stream
```

USDⓈ-M Futures REST:

```text
https://fapi.binance.com/fapi/v2/account
https://fapi.binance.com/fapi/v1/openOrders
https://fapi.binance.com/fapi/v1/listenKey
https://fapi.binance.com/fapi/v1/ticker/24hr
https://fapi.binance.com/fapi/v1/premiumIndex
https://fapi.binance.com/fapi/v1/openInterest
https://fapi.binance.com/fapi/v1/fundingRate
https://fapi.binance.com/fapi/v1/klines
https://fapi.binance.com/futures/data/globalLongShortAccountRatio
https://fapi.binance.com/futures/data/takerlongshortRatio
https://fapi.binance.com/futures/data/basis
https://fapi.binance.com/futures/data/openInterestHist
```

USDⓈ-M Futures WebSocket:

```text
wss://fstream.binance.com/market/stream
wss://fstream.binance.com/private/ws?listenKey=...
```

Options REST:

```text
https://eapi.binance.com/eapi/v1/mark
https://eapi.binance.com/eapi/v1/openInterest
https://eapi.binance.com/eapi/v1/blockTrades
```

These are upstream Binance endpoints used by the collector. Consumers should normally use the local API rather than calling these endpoints directly.

## Cross-exchange public sources

When enabled:

```text
Coinbase Advanced Trade:
wss://advanced-trade-ws.coinbase.com

Kraken Spot WebSocket v2:
wss://ws.kraken.com/v2

OKX public WebSocket:
wss://ws.okx.com:8443/ws/v5/public
```

These sources are used for public ticker comparison and confirmation only. They are not used for order execution.

## Health, reconnects, and shutdown

The collector continuously retries failed WebSocket and REST tasks with bounded backoff. Typical network warnings include:

```text
no close frame received or sent
getaddrinfo failed
Cannot connect to host ...
```

These mean a socket, DNS lookup, or upstream request failed. The collector records the failure in `data_health` and retries. Check:

```bash
curl http://127.0.0.1:8000/data-health
```

A DNS error is a machine/network problem, not evidence that the API routes are broken. The local `/health` endpoint can remain available while Binance is unreachable.

Stop cleanly with:

```text
Ctrl+C
```

The CLI handles cancellation without exposing an asyncio traceback.

## Testing and verification

Run the complete test suite:

```bash
python -m pytest -q
```

Compile the project:

```bash
python -m compileall -q binance_data_layer main.py
```

Latest recorded verification:

```text
66 tests passed
Python compilation passed
```

The test suite covers:

- Binance stream construction.
- Event normalization.
- Symbol inference.
- Partial depth.
- Candles and closed-candle indicators.
- Options fields and deduplication.
- Futures endpoints.
- Private-data `N/A` behavior.
- User-stream keepalive.
- Time synchronization and signing.
- Breadth filtering.
- Technical features.
- Execution estimates.
- Data quality.
- Cross-exchange normalization and confirmation.
- Dynamic universe ranking and symbol validation.
- REST API routes.
- WebSocket event delivery.
- Graceful Ctrl+C handling.

## What is not implemented

The following are not currently part of the production implementation:

- Guaranteed-profit or guaranteed-accuracy signals.
- A validated BUY/SELL/HOLD strategy engine.
- Backtesting and walk-forward validation.
- Paper-trading execution.
- Binance testnet execution.
- Live order execution.
- n8n webhook contract.
- Portfolio risk service and position sizing.
- Automatic strategy promotion or continuous model retraining.
- Macro-economic data.
- General news and social-media sentiment.
- Blockchain-wide on-chain analytics.
- Token-unlock calendars.
- Wallet identity/concentration data.
- BTC dominance and total crypto-market capitalization.

The planned work, original requirements, implementation differences, and maintenance log are documented in:

```text
PROJECT_PLAN_AND_STATUS.md
```
