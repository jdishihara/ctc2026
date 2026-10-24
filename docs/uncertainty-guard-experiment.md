# Uncertainty guard experiment — not promoted

The completed fixed comparison does **not** justify replacing the current
strategy. Applying the entropy rule to every fundamental target removed
accepted passive risk additions under high uncertainty, but did not reduce
losing development seasons or the worst loss. It lowered profit in the
three-second development scenarios and on captures 242 and 243.

This is an offline research subclass. The live launcher, default strategy,
position size, and frozen closed-season worker are unchanged.

## Why it was tested

The existing `ent_cut=1.2` check blocks some aggressive additions. Passive
orders and reversals can still add exposure under the same high-entropy
posterior, and previously placed orders can remain executable. The candidate
caps fundamental targets at reductions, caps reversals at flat, and cancels
working orders whose remaining quantity can cross flat. Basket hedges retain
their separate execution path.

The [declared plan](uncertainty-guard-plan.md) fixes the parameters, full grid,
and promotion gates. All results are retained, including unfavorable changes.

## Development results

All 75 development seasons 451–525 were replayed at 10% limits with the same
observed-touch execution profile. Each latency has 75 paired scenarios.

| Delay | Baseline mean | Candidate mean | Losing seasons, before → after | Worst season, before → after |
| --- | ---: | ---: | ---: | ---: |
| 0.25 seconds | $1,434.47 | $1,434.47 | 6 → 6 | −$765.65 → −$765.65 |
| 1 second | $1,434.31 | $1,434.31 | 6 → 6 | −$765.65 → −$765.65 |
| 3 seconds | $1,027.27 | $1,014.18 | 9 → 9 | −$1,097.41 → −$1,097.41 |

The short-delay mean changes are only +$0.00398 each. At three seconds the
change is −$13.09312. Across all 225 pairs, 83 improve, 76 decline, and 66 are
unchanged; the mean change is −$4.36172. These scenarios share seasons and are
not 225 independent market observations.

## Completed captured-market results

Each capture includes all 12 current-snapshot scenarios: delays 0.25/1/3
seconds, full/half displayed depth, baskets off/on.

| Capture | Baseline mean | Candidate mean | Negative scenarios, before → after | Worst, before → after |
| --- | ---: | ---: | ---: | ---: |
| 241 | $34.95 | $34.95 | 3 → 3 | −$21.70 → −$21.70 |
| 242 | $1,837.05 | $1,835.85 | 0 → 0 | $1,462.74 → $1,461.54 |
| 243 | $270.77 | $247.49 | 0 → 0 | $156.65 → $130.96 |

Every capture-241 pair is unchanged. Every capture-242 pair loses $1.20 of
simulated profit; every capture-243 pair declines, by $17.35–$27.95.

The candidate therefore fails the declared development-mean gate at three
seconds and the captured-mean gates for 242 and 243. The lack of additional
negative scenarios does not override those failures.

## Versions and review

- **V1:** frozen source `dbe499e`; 450 development runs and 72 capture runs.
  Review found that an active basket cycle bypassed cancellation of unrelated
  fundamental orders. The input helper also accepted paused or missing-state
  receipts. The actual four input receipts were independently checked and
  were `ready`; the validation omission was still a defect.
- **V2:** fixes in `db12ca4`, evaluated from `859163a118fff1ecce8b3af790e7444865390856`
  after integrating teammate main `870d31f`. It performs a cancellation pass
  before basket, throttle, warm-up, confidence, and missing-quote returns;
  preserves active basket target symbols; and requires a confirmed `ready`
  receipt for completed/development modes. Its manifest includes
  `scripts/observe_market_seasons.py`, omitted from v1.
- The same 522 runs were repeated for v2. **Every result row is byte-identical
  between v1 and v2 on these inputs.** This does not make the reproduced v1
  defects harmless on other paths.
- The 26 uncertainty tests pass. Before the fixes, nine original regression
  cases and eight new review regressions failed. The integrated branch passes
  **497 Python tests**; tests verify specified behavior, not profit.
- Independent review reproduced the real basket/PORT cancellation case, kept
  the MAT hedge, crossed the later PORT quote without a fill, and attacked
  both completed and development receipt validation. Its focused run passed
  57 tests. Approval covers the offline v2 evaluation, not strategy promotion.

## Audit scope and timing limitation

The audit counts newly accepted passive orders that can add exposure under the
latest computed high-entropy posterior. Across development scenarios the count
falls from 470 to zero; the capture counts are 0→0, 24→0, and 36→0. These counts
repeat simulated markets and do not represent unique real account orders.
The audited baseline reproduces every required baseline result exactly.

A zero audit count does not prove removal of every old working order, absence
of future fills, or correctness of forecasts. V2 uses the latest computed
posterior and preserves the model update schedule. Failed cancellation leaves
the exchange outcome uncertain and stops the preflight pass.

Retry spacing applies to **preflight cancellation attempts**. A later
fundamental cancellation after `compute_fair` changes the posterior does not
share that timestamp: a failure at t=120.0 can be retried by preflight at
t=120.1. Review reproduced this limitation; it does not bypass the addition
guard. The plan's wording was narrowed after the frozen v2 run, so its evaluated
hash refers to the original declaration at `859163a`.

## Evidence and limits

All 24 archived metadata/result/summary files match their original output bytes:

- [V1 evidence](evidence/uncertainty-guard/v1/): all 261 pairs before review fixes.
- [V2 evidence](evidence/uncertainty-guard/v2/): all 261 pairs after review fixes.
- [V2 development summary](evidence/uncertainty-guard/v2/dev-summary.json).
- [V2 development results](evidence/uncertainty-guard/v2/dev-results.jsonl).
- [V2 capture 241](evidence/uncertainty-guard/v2/241-summary.json),
  [242](evidence/uncertainty-guard/v2/242-summary.json),
  [243](evidence/uncertainty-guard/v2/243-summary.json).

Metadata includes selected-frame hashes, official receipts, reference-artifact
hashes, source/model hashes, and all 225 development input-file hashes. Each run
verified its recorded source hashes at completion. V1's recorded hashes also
match its frozen commit; its missing validator hash remains a documented
provenance limitation rather than a rewritten manifest.

Development seasons and these captures are reused data. Virtual fills omit
queue priority, market impact, serialized REST processing, cancellation races,
and conversion delays. No active season 244 outcomes were read. None of this
establishes new attributable live profit or consistent competition performance.
