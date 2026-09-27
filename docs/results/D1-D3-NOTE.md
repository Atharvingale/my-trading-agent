# D1–D3 (cross-exchange dislocation) — record-location note

D1-D3 (cross-exchange dislocation) never existed as rows in
edge_validation_records. They were research-level findings only
(candidates DB + dislocation.evaluate_sufficiency), never promoted to a
Module 1 gate record, because the gate correctly refused to accept an
INCONCLUSIVE-for-missing-data verdict as a valid gate row type. The
CLOSED_UNAVAILABLE closure (research/reports/d1_d3_closure.json,
2026-09-27) is the authoritative and only record of this. Do not search
edge_validation_records for D1-D3 rows — they are not there and this is
expected, not a data-loss bug.
