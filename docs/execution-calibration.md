# Completed-season execution calibration

The first controlled season is officially complete (CID
`6650d983-93c3-45d2-96dd-15209dcd8320`, fictional year 1786, historical season
241). Completion and the matching ready-state receipt were checked before
reading that historical price file. All 12 official settlements match.

## Historical prices differ from captured prices

Interpolate fictional time between consecutive same-round received snapshots,
then interpolate the published minute prices. This matches 16,836 of 16,992
captured quote frames. The 156 excluded frames comprise 37 without both sides,
16 crossing round boundaries, and 103 without surrounding snapshots.

| Symbol | Median absolute midpoint difference | Nearest-rank p95 difference |
| --- | ---: | ---: |
| HAVEN | 2.238% | 13.767% |
| PORT | 1.582% | 5.547% |
| REIN | 0.188% | 0.474% |

Independent review reproduced these results and checked denser storm clocks.
On the same 13,221 frames bracketed by storm observations, HAVEN's median
absolute difference was 2.572% with snapshot clocks and 2.808% with storm
clocks; p95 was 13.975% and 14.021%, respectively. Snapshot granularity alone
does not explain the discrepancy.

These estimates weight each quote update equally. They are retrospective,
approximately aligned comparisons, with receive delays and minute-grid
interpolation. Storm clocks come from the same feed. Midpoints do not establish
executable prices or fill quantities, and this does not isolate the whole P&L
gap. [Full comparison](evidence/season-241-price-path-comparison.json).

## The existing spread calibration is also optimistic for this season

| Symbol | Existing ladder spread | Median observed spread on matched quotes |
| --- | ---: | ---: |
| HAVEN | 0.3096% | 1.0899% |
| PORT | 0.2608% | 0.7642% |
| REIN | 0.2464% | 0.2675% |

This is one completed season. Its observed spreads are not a universal estimate
of future conditions. The next diagnostic keeps model parameters fixed and
tests the existing strategy under these observed costs. It does not change the
frozen 24-scenario evaluation of subsequent captured market paths.

## Fixed historical stress diagnostic

Use 10% position limits, unchanged strategy parameters, and 0.25/1/3-second
latency. Compare the original ladder with (a) spreads widened to at least the
completed season's per-symbol median and (b) that spread with only the observed
median top-of-book quantity available. The spread-only profile shifts deeper
bands by the same half-spread increase so deeper fills cannot get a better
price than the touch. All profiles retain the existing ten-second refill
assumption; displayed replenishment is still modeled, not reconstructed.

Run the completed season first, then the designated development seasons
451–525. Preserve all nine combinations and every season. Season 242's
published prices and outcomes remain excluded from this diagnostic. These diagnostics measure
sensitivity to costs within the historical simulator; they do not validate its
price paths, prove live profits, or choose new live parameters.

### Completed-season result with corrected clock

[PR 6](https://github.com/jdishihara/ctc2026/pull/6) corrects historical order
deadlines and the final close. Independent review approved the fixed development
grid after checking replenishment, price ties, and round boundaries. See
[clock semantics](simulator-timing.md).

| Cost profile | 0.25 s latency | 1 s latency | 3 s latency |
| --- | ---: | ---: | ---: |
| Original ladder | $1,628.94 | $1,628.94 | $1,441.51 |
| Observed median spreads | $1,564.04 | $1,564.04 | $1,382.19 |
| Observed spreads and touch quantities | $1,564.04 | $1,564.04 | $1,382.19 |

All nine totals match the previous scheduler's results in this completed
season. The corrected timestamps are still necessary, but this clock defect
does not explain its historical/live profit gap. Wider static spreads reduce
the estimate modestly; they also do not reproduce the large gap. Historical
price paths and execution assumptions remain material differences.

The original output is preserved in
`out/execution-costs-20261024-completed/`. The final-clock rerun is in
`out/execution-costs-20261024-clock-v2-completed/`, including per-run results,
calibration, fixed parameters, and source hashes. The initial interim clock
rerun is also preserved under `out/execution-costs-20261024-clockfixed-completed/`.

The next officially completed capture is reported separately in
[season 242's recorded-market diagnostic](observed-season-242.md). It uses
captured quotes rather than these synthetic historical cost profiles.

### Development seasons 451–525

All 675 runs completed in 474.47 seconds: the same nine scenarios on all 75
designated development seasons. Every scenario used the original trading logic
and parameters; the proposed executable-entry correction was developed in a
separate worktree and is not included in these results.

| Profile | Latency | Mean P&L | Losing seasons | Worst season |
| --- | ---: | ---: | ---: | ---: |
| Original ladder | 0.25 s | $1,578.47 | 6 / 75 | −$683.35 |
| Original ladder | 1 s | $1,578.32 | 6 / 75 | −$683.35 |
| Original ladder | 3 s | $1,121.19 | 8 / 75 | −$964.49 |
| Observed spreads | 0.25 s | $1,484.12 | 6 / 75 | −$744.18 |
| Observed spreads | 1 s | $1,484.12 | 6 / 75 | −$744.18 |
| Observed spreads | 3 s | $1,040.15 | 8 / 75 | −$1,097.74 |
| Observed spread/touch | 0.25 s | $1,425.86 | 6 / 75 | −$825.39 |
| Observed spread/touch | 1 s | $1,425.68 | 6 / 75 | −$825.39 |
| Observed spread/touch | 3 s | $1,030.14 | 8 / 75 | −$1,097.74 |

These results retain a positive historical average under the tested costs,
while losing seasons and material latency sensitivity remain. They are reused
development data, not an unseen validation set. Fixed median costs also cannot
reconstruct changing live quotes, so these numbers do not establish consistent
live profitability or justify scaling the account.

The repository retains [all 675 rows](evidence/execution-costs/dev-results.jsonl),
[the development summary](evidence/execution-costs/dev-summary.json), and
[parameters, cost profiles, calibration, and source hashes](evidence/execution-costs/dev-metadata.json).
The [completed-season rows](evidence/execution-costs/completed-results.jsonl)
and [metadata](evidence/execution-costs/completed-metadata.json) are also preserved.
