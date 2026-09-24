# Module 3: Hermes Observer + Context Builder

## Purpose
Consume the (hardened) market-data service and produce a decision-ready, structured `MarketContext` per tracked symbol. This module runs in analysis-only mode — it does not call the Strategy Layer or Risk Engine yet; that's wired in module 5.

## Files to implement
```
observer.py   # subscribes to REST snapshots + WS events from the market-data service
context.py    # builds and refreshes MarketContext objects
models/market.py
```

## Hermes definition (binding constraint)
Hermes, including this module, is a **deterministic/statistical** component. It does not call an LLM to interpret events or produce context fields. If a future news/sentiment layer is added, it is a separate read-only module whose output is one more structured field in `MarketContext`, produced by summarization/classification only — never by free-form reasoning that feeds directly into `action` or `confidence`.

## MarketContext fields (per symbol)
- Market regime: trend/range, volatility state, breadth, risk-on/risk-off indicators
- Price/trend: returns, EMA relationships, RSI, ATR, VWAP, Bollinger state, multi-timeframe alignment
- Order flow: CVD, aggressive-buy ratio, large-trade concentration, order-book imbalance
- Derivatives: funding, open interest, basis, basis rate, positioning, liquidation activity
- Options: implied volatility, Greeks, positioning (where available)
- Liquidity: spread, spread stability, depth, estimated execution impact
- Cross-exchange confirmation
- Data quality: freshness, missing fields, sequence integrity, REST/WS health
- Portfolio state: positions, exposure, unrealized/realized PnL, recent win/loss streak, cooldown state
- Strategy state: current production version(s), recent performance, disabled/degraded strategies

## Observation loop
1. Receive market events and periodic snapshots.
2. Check freshness, completeness, contradiction status — mark context stale/invalid if checks fail (see module 2's data-health signals).
3. Update the active `MarketContext` for each tracked symbol.
4. Detect regime changes or meaningful state transitions.
5. Emit a "context ready" event at controlled intervals and on important transitions — this is the hook module 5 (Decision Engine) subscribes to. Do not call strategy or decision code from this module directly; keep it a pure producer.

## Acceptance criteria
- Runs continuously against the market-data service with no trading calls made — verifiable by the absence of any import from `strategies/`, `risk/`, or `execution/`.
- A stale or contradictory upstream data-health signal produces a `MarketContext.valid = False`, not a best-effort guess.
- Unit tests cover: normal update, stale-data handling, regime-change detection, and recovery after a market-data service restart.

## When done
Log to `docs/implementation-log.md`: which context fields were implemented in this pass, which were deferred (e.g. options/derivatives if that data isn't available yet), and how staleness is detected.
