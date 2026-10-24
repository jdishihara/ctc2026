# Executable entry-price bounds

The previous aggressive-order code forced its limit to cross the displayed
touch, even if doing so exceeded the fair-value price allowed by its edge floor.
For example, with fair value 101 and a 98/102 market, it could buy at 102. The
mirror case could sell below its own fair value.

New risk must now preserve the configured edge at its limit price. A reversal
whose opening leg lacks that edge may flatten the old position, but may not
open the opposite position. Genuine position reductions retain their existing
execution handling. Risk is classified from reconciled positions after a
cancellation, so fills during cancellation cannot turn a reduction into an
unprotected addition.

Outstanding orders are checked before unchanged-target and uncertainty gates.
This includes partially filled orders and pending simulated activations. If a
side's total remaining quantity can cross through flat, every limit on that
side must meet its bound, since execution order is uncertain. A matching
tracked passive quote retains its documented fractional edge floor. Invalid
or unbounded entry limits are canceled. Cancellation must succeed, preserve
competition identity, and leave usable account state before replacement.

When a target needs a new order, existing orders on either side are canceled
and reconciled even if their signed quantities net to zero. This prevents a
new order from turning an older reduction into unprofitable new exposure.

Independent review reproduced the defects and checked the fixes. The full
integrated branch suite passes 368 tests. Completed-recording and fixed
historical development comparisons are reported below.
Execution correctness does not guarantee that the model's fair value is
accurate or that a season will be profitable.

## Completed-capture comparison

The strategy parameters and the existing scenario grids were preserved. All
12 season-241 and all 24 season-242 results are retained before and after the
correction. These previously observed captures are diagnostic data.

With current snapshot behavior, season 241's six outcomes are unchanged,
including the three-second basket result of −$21.70. Its six old-snapshot-reset
ablations each improve by $2.88. This correction does not eliminate that loss.

Season 242 remains positive in every scenario. Across all 24 scenarios, six
improve and 18 decline; the largest decline is $124.53. All 12 older
snapshot-reset cases decline. For the current snapshot behavior, six scenarios
improve and six decline; individual changes range
from −$5.50 to +$14.64. The lowest current-behavior outcome changes from
$1,448.10 to $1,462.74. Across all 24 scenarios, including the older snapshot
behavior, the new minimum is $1,373.10 and maximum is $2,172.95.

The profit effect depends on snapshot behavior and is mixed in these two
recorded markets. The purpose of the fix is to enforce the intended price bounds; these
outcomes do not establish consistent profitability.

[Every paired result](evidence/executable-entry/captured-comparison.json),
[season 241 after](evidence/executable-entry/season-241-after.json), and
[season 242 after](evidence/executable-entry/season-242-after.json).

## Historical development comparison

The identical 675-run grid completed: seasons 451–525, three fixed liquidity
profiles, three latencies, and 10% position limits. These are reused development
seasons, not a new holdout. Each table row summarizes 75 seasons.

| Profile | Latency | Mean after | Mean change | Losses before → after | Worst after |
| --- | ---: | ---: | ---: | ---: | ---: |
| Legacy | 0.25 s | $1,584.50 | +$6.03 | 6 → 6 | −$616.52 |
| Legacy | 1 s | $1,584.35 | +$6.03 | 6 → 6 | −$616.52 |
| Legacy | 3 s | $1,118.30 | −$2.89 | 8 → 8 | −$964.40 |
| Observed spread | 0.25 s | $1,493.88 | +$9.77 | 6 → 6 | −$703.04 |
| Observed spread | 1 s | $1,493.88 | +$9.77 | 6 → 6 | −$703.04 |
| Observed spread | 3 s | $1,037.22 | −$2.93 | 8 → 9 | −$1,097.41 |
| Observed touch | 0.25 s | $1,434.47 | +$8.61 | 6 → 6 | −$765.65 |
| Observed touch | 1 s | $1,434.31 | +$8.62 | 6 → 6 | −$765.65 |
| Observed touch | 3 s | $1,027.27 | −$2.87 | 8 → 9 | −$1,097.41 |

The shorter-delay means improve slightly. Three-second means decline slightly,
and two profiles gain one losing season. Individual changes are larger than
the averages: the largest decline is $213.11 and largest increase is $231.48.
For the separately repeated nine historical scenarios for completed season 241,
every result declines, by $0.05 to $8.57. Those historical results still greatly
overstate that season's captured-market performance.

This is an execution-correctness change with mixed profit effects. It is not a
claim of increased win probability or live readiness. The static historical
cost assumptions and recorded-market limitations still apply.

[All historical pairs](evidence/executable-entry/historical-comparison.json),
[development metadata](evidence/executable-entry/dev-metadata.json),
[all 675 development rows](evidence/executable-entry/dev-results.jsonl),
[development summary](evidence/executable-entry/dev-summary.json),
[completed-season metadata](evidence/executable-entry/completed-metadata.json),
[all nine completed-season rows](evidence/executable-entry/completed-results.jsonl),
and [completed-season summary](evidence/executable-entry/completed-summary.json).
