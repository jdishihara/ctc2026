# Experimental final-report-only baseline

Defined on 2026-10-24 before observing the close or outcomes of active season
243. This is an offline research comparison, not a live trading configuration.

## Question

How much profit and downside come from taking positions before all three final
damage reports? Compare the existing strategy with a subclass that receives
every news update but only permits its quote-driven trading once
`model.final_exact_ready` is true. That flag requires round three, all three
final reports, and complete outage history. It does not mean every modeled
settlement price is exact.

## Fixed comparisons

- Keep existing parameters, entry-price corrections, and 10% position limits.
- Historical development: seasons 451–525, the already calibrated observed-touch
  cost profile, and 0.25/1/3-second latency. Retain all 225 candidate outcomes and
  pair them with the same scenarios from the entry-corrected full strategy.
- Completed captured markets: 0.25/1/3-second latency, 100%/50% displayed depth,
  basket off/on, and current snapshot behavior only. Run both strategies and
  keep all 24 outcomes for each completed capture.
- Seasons 241 and 242 have already been examined and are diagnostic data. Read
  no published future files for active seasons. A future observed season can
  be evaluated only after its official closed receipt.
- Report means, losses, worst outcomes, zero-trade cases, and profit sacrificed.
  A smaller loss alone does not establish a better competition strategy.

This experiment does not alter the previously frozen 24-scenario baseline
capture evaluation. It adds a separate research comparison. No automatic live
promotion follows from positive backtests or from one favorable season.

## Results

All 225 development scenarios and 24 replay outcomes for each completed capture
are retained. The captured comparisons contain 12 paired scenarios each; the
development comparisons contain 75 seasons at each of three latencies.

| Development latency | Full strategy mean | Final-reports-only mean | Losses, full → final only | Final-only worst | Final-only zero-trade seasons |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.25 s | $1,434.47 | $82.45 | 6 → 0 | $0.00 | 17/75 |
| 1 s | $1,434.31 | $82.45 | 6 → 0 | $0.00 | 17/75 |
| 3 s | $1,027.27 | $11.18 | 9 → 3 | −$5.90 | 39/75 |

Across the 225 scenarios, waiting gives up an average $1,239.98 relative to the
full strategy. The lower loss count comes with much lower profit and 73
scenarios with no fills or conversions. Those zeros are not profitable seasons.

| Completed capture | Full strategy mean | Final-reports-only mean | Losses, full → final only | Final-only range |
| --- | ---: | ---: | ---: | ---: |
| 241, 12 paired scenarios | $34.95 | $20.00 | 3 → 0 | $19.25 to $22.25 |
| 242, 12 paired scenarios | $1,837.05 | $0.10 | 0 → 6 | −$4.00 to $5.60 |

Every final-only outcome for season 242 is worse than its matched full-strategy
outcome. The final reports do not eliminate losses or execution sensitivity.
This experiment does not support replacing the full competition strategy with
final-report-only trading. It remains a diagnostic baseline, with no live
configuration change.

The historical grid uses quote-update-weighted spread/depth calibration and
static liquidity refill; it does not reconstruct actual exchange fills. The
captured replay omits queue competition, market impact, HTTP serialization,
cancellation races, and conversion delays. Captured news coverage does not prove
complete quote coverage. All of these datasets have already been examined.

[Development summary](evidence/final-reports/dev-summary.json),
[all development pairs](evidence/final-reports/dev-pairs.json),
[season 241 summary](evidence/final-reports/season-241-summary.json), and
[season 242 summary](evidence/final-reports/season-242-summary.json).
The same directory preserves each run's metadata, raw rows, and source hashes.

Independent review verified the gate, representative unchanged default replays,
conversion accounting, every scenario pair, and recomputed summaries. The full
suite passes 378 tests. A provenance limitation remains: the original baseline
and candidate manifests omit the two NPZ model artifacts. A
[retrospective hash check](evidence/final-reports/model-artifact-audit.json)
confirms the current files match the committed model blobs used by the branches;
it is not a contemporaneous runtime measurement of those files.
