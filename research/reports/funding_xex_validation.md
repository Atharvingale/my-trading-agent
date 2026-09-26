# Funding-Rate Carry + Cross-Exchange Dislocation — Module 1 Validation

Run date: 2026-09-26. Verdicts: funding INCONCLUSIVE, dislocation INCONCLUSIVE.
Gate records written: 0. Holdout consumed: none. Production approved: 0.

## Multiple testing
Method: bonferroni, base alpha 0.050, ledger tested 5, registered 6, tested 0.
Registered candidates consume no budget until tested; the first future test faces alpha 0.008333.

## Funding-rate carry — INCONCLUSIVE
Observations: 200, hash `48806db72e6bd7f6`.
Quality: {"duplicates": 0, "gaps_over_9h": 0, "missing_marks": 0, "n": 200, "ok": true, "ordered": true, "reasons": [], "span_days": 32.99999998842593, "symbols": ["BTCUSDT", "ETHUSDT"], "unrealistic_rates": 0}.
Descriptive: {"fraction_positive": 0.95, "mean_rate": 6.025314999999996e-05, "n": 200}.
Evaluation: {"dataset_hash": "48806db72e6bd7f69d4f43d80b65effe455be70880f9f58327ebeb2bcb3529b6", "hypotheses_registered": 3, "hypotheses_tested": 0, "ledger_tested_elsewhere": 5, "n": 200, "note": "registered hypotheses consume no multiple-testing budget until tested", "reasons": ["span 33.0 days below 60-day gate minimum", "only 1 regime leg(s), need 2"], "regime_legs": ["single-33d-window"], "span_days": 32.99999998842593, "verdict": "INCONCLUSIVE"}.
Missing for gate evidence: multi-month funding history spanning at least two regime legs (have 33 days / one leg), longer per-symbol series, dated holdout windows.

## Cross-exchange dislocation — INCONCLUSIVE
Observations: 8421, hash `217c5c5c3ad57dba`.
Quality: {"duplicates": 0, "gaps_over_1h": 8, "impossible_spreads": 0, "n": 8421, "ok": true, "ordered": true, "reasons": [], "span_days": 4.396761319444445, "symbols": ["BTCUSDT", "ETHUSDT"], "unavailable": 615}.
Threshold crossings (descriptive, not returns): [{"crossings": 18, "hypothesis_id": "D1", "note": "descriptive count only; no executable prices, no returns computed", "persistence": 3, "threshold_bps": 5.0}, {"crossings": 1, "hypothesis_id": "D2", "note": "descriptive count only; no executable prices, no returns computed", "persistence": 3, "threshold_bps": 10.0}, {"crossings": 0, "hypothesis_id": "D3", "note": "descriptive count only; no executable prices, no returns computed", "persistence": 5, "threshold_bps": 20.0}].
Evaluation: {"dataset_hash": "217c5c5c3ad57dbab0fe962f88d94ac5f88cd9a6feda245467f8f4e16ef52e31", "hypotheses_registered": 3, "hypotheses_tested": 0, "ledger_tested_elsewhere": 5, "n": 8421, "note": "registered hypotheses consume no multiple-testing budget until tested", "reasons": ["missing executable data: per-venue bid quotes with synchronized timestamps", "missing executable data: per-venue ask quotes with synchronized timestamps", "missing executable data: per-venue spread at signal time", "missing executable data: per-venue depth at signal time", "missing executable data: venue-pair fee schedule for the traded symbols", "missing executable data: transfer/settlement latency assumption between venues", "span 4.4 days below 60-day gate minimum", "only 1 regime leg(s), need 2"], "regime_legs": ["single-4d-window"], "span_days": 4.396761319444445, "verdict": "INCONCLUSIVE"}.
Missing for gate evidence: synchronized per-venue bid/ask quotes with spreads, depth, fee schedules, and latency assumptions, spanning at least two regime legs (have ~4.4 days of aggregate disagreement only).
