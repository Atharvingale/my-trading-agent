# Task: Cycle 4 Pre-Work (cont.) — Public Archive OI/Liquidation Coverage Audit

## Status: Human-approved, audit only — no hypothesis, no holdout, no ledger write

The prior audit (`docs/files/oi-liquidation-coverage-audit.md`) checked only
your own collector's ingested data and found effectively no usable coverage
(0 symbols ≥90 days). Before concluding the OI/liquidation-dynamics class is
unviable for lack of data, check one more source: Binance's own public
historical archive at `data.binance.vision`, which is separate from any paid
vendor and separate from your collector's live ingestion.

This task only adds a second data source to the same audit. It does not
change anything else about Cycle 4's sequence — no hypothesis, no menu
approval, no holdout, no ledger write.

---

## What to check

Binance publishes, with no API key required:

- `data/futures/um/daily/metrics/<SYMBOL>/` — daily open interest
  (`sum_open_interest`, `sum_open_interest_value`), top-trader long/short
  ratio, and taker buy/sell volume ratio, per symbol.
- `data/futures/um/daily/liquidationSnapshot/<SYMBOL>/` — forced-liquidation
  order events (side, price, quantity, time), per symbol.
- `data/futures/um/daily/klines/<SYMBOL>/` and
  `data/futures/um/daily/fundingRate/<SYMBOL>/` — price and funding, for
  cross-referencing against what you already have.

Confirm these paths and formats directly against Binance's own
`binance-public-data` documentation/repo before parsing anything — don't
assume the schema from this prompt; verify it.

## Steps

1. **List available symbols** in the `metrics` and `liquidationSnapshot`
   archives — how many USD-M futures symbols are actually published, not
   just BTCUSDT/ETHUSDT.
2. **Per symbol, for `metrics`**: earliest and latest available date,
   number of daily files present vs. expected count for that range (gap
   count), so a symbol with sparse silent gaps isn't miscounted as fully
   covered.
3. **Per symbol, for `liquidationSnapshot`**: earliest and latest available
   date, event count, and whether coverage is genuinely daily-continuous or
   has silent gaps.
4. **Cross-reference against your existing funding/price coverage** (already
   audited) to find, per symbol, the overlapping window where OI-metrics +
   liquidation-snapshot + funding + price ALL exist.
5. **Download and checksum-verify a sample** (don't just trust the file
   listing) — pick 3–5 symbols across different liquidity tiers and
   confirm the actual file contents match the expected schema and aren't
   truncated/corrupted, using the archive's own `.CHECKSUM` sidecars.
6. Produce the same factual summary format as the prior audit:

```text
- N symbols have ≥90 days of full (OI-metrics + liquidation-snapshot +
  funding + price) coverage: [list]
- N symbols have ≥180 days: [list]
- Largest common overlapping window across all covered symbols: [dates]
- Confirmed granularity: OI-metrics = daily, liquidation-snapshot =
  [event-level | state whatever is actually found]
- Any symbols where metrics exist but liquidationSnapshot doesn't, or vice
  versa: [list, don't silently drop them from the count]
```

## Important constraint to note in the report, not to resolve now

This archive is **daily granularity** for OI metrics, not intraday. If this
source is used, any resulting Cycle 4 hypothesis would need to be a
daily-rebalance design, not an hourly one. State this plainly in the report;
do not design around it yet — that decision belongs in the actual
pre-registration step, after human review of this audit.

## Explicit stop conditions (same as before)

- Do not design a hypothesis.
- Do not touch or reserve a holdout window.
- Do not write to `edge_validation_records` or `hypothesis_menu.py`.
- Do not call the multiple-testing alpha calculation.
- Do not touch `strategies/`, `execution/`, or `risk/`.
- If downloading sample files requires network access outside what's already
  configured/approved for this project, stop and report rather than
  requesting broader access unilaterally.

## When done

Report the full coverage table, the factual summary block above, the
checksum-verification result for the sampled files, and an explicit
side-by-side comparison against the internal-collector audit's numbers
(0 symbols ≥90 days) so the human can see clearly whether this second source
changes the Cycle 4 go/no-go picture. Then stop.
