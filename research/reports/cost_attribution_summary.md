# Cost Attribution: Raw Signal vs. Cost Structure (Diagnostic, 2026-09-24)

Diagnostic-only. Not gate evidence, not a verdict on any strategy. Method: each
recorded experiment's holdout candles were re-fetched and hash-verified identical
to the artifact (all three SHA-256 match), the trade sequences were reproduced
exactly (66 / 111 / 96 trades, aggregates match to <1e-9), and costs were then
stripped trade by trade with timing held fixed. A zero-cost rerun corroborates
each figure. Bootstrap CIs use the same percentile method as gate evidence
(seed 20260924, 2,000 samples) and are diagnostic-only.

## Per-strategy split

| Strategy (holdout) | Net of costs (recorded) | Pre-tax/pre-fee, same trades (new) | Gap (cost drag) | Raw-signal reading |
|---|---|---|---|---|
| Trend Following (2024-01-01–04-01, 66 trades) | −5.34%, CI [−1.73%, −0.67%] | +0.38%, CI [−0.23%, +1.08%] | 5.72 pts | (b) Mildly positive before costs, pushed negative by the cost structure. Note the pre-cost CI still straddles zero — the raw signal is not statistically positive either. |
| Order Flow (2024-04-02–07-01, 111 trades) | −10.13%, CI [−1.64%, −1.22%] | −0.00%, CI [−0.22%, +0.24%] | 10.13 pts | (a) Flat before costs — the signal itself is approximately zero, costs do the rest. |
| Mean Reversion (2024-07-02–10-01, 96 trades) | −9.49%, CI [−1.86%, −1.23%] | −0.11%, CI [−0.44%, +0.25%] | 9.38 pts | (a) Flat-to-negative before costs — no underlying edge for costs to destroy. |

Zero-cost reruns agree: +0.37% / −0.01% / −0.07%. Trend and Order Flow trade
timing is near-identical with and without costs (1 and 2 exit shifts); Mean
Reversion timing is stop-sensitive (entries sit near stops, so the 0.1% entry
shift cascades), but both estimates agree at the same flat-negative level.

## Where the drag comes from (share of starting notional, cumulative)

| Strategy | Fees | Slippage | 1% TDS turnover drag | VDA tax (31.2% on gains) |
|---|---|---|---|---|
| Trend Following | 3.20% | 3.20% | 16.02% | 3.17% |
| Order Flow | 5.28% | 5.28% | 26.35% | 0.92% |
| Mean Reversion | 4.54% | 4.54% | 22.65% | 1.25% |

The 1% TDS on gross proceeds is the dominant drag at this turnover (111/96
trades recycle the account repeatedly), followed by per-side fees and slippage.
VDA tax is small precisely because there are few gains to tax — consistent with
flat raw signals.

Machine-readable counterpart: `research/reports/cost_attribution.json`.
