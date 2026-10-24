# Competition readiness — 2026-10-24

Status updated after the 08:12 UTC capture-245 supervisor evaluation (04:12 EDT). One complete small-size live season
has a verified settlement receipt. The next trial contains mixed activity.
Live practice remains stopped pending shared-account ownership clarification.
Market recording and offline evaluations continue.

## What the evidence supports

The historical strategy is profitable on average in the local simulator, but
losing seasons remain. The earlier live loss exposed execution defects; those
defects have been fixed and regression-tested. One completed live season was
positive; consistent live profitability has not been established. Neither the historical average nor the test count
establishes a probability of winning the competition.

The full production-supervisor replay exposed a false history stop between
storms. A reviewed correction eliminates all 40 such stops in the fixed
comparison: 53 of 64 settings now complete, 11 hit the loss trigger, and
12 finish negative. The worst terminal outcome is −$420.64; two cleanup cases
retain residual positions. The primary capture-244 result remains −$261.00,
versus +$628.14 without the supervisor. All 64 baseline outputs and request/fill
traces match exactly. Independent corrected result audit is complete; full evidence and
limitations are in [practice-round-transition.md](practice-round-transition.md).
The independently reviewed original comparison remains in
[supervised-client-replay.md](supervised-client-replay.md). These offline
findings do not change the actual +$141.16 completed practice record.

The next closed recorded path, capture 245, passed independent audit: its
supervised primary earns +$362.85, all 16 settings finish positive, 15 complete
and one hits the loss trigger then finishes flat at +$5.42. Its interval began
before the corrected-runtime freeze, and the receipt precedes the separate
forward-driver freeze by 1.181 seconds. This is not prospective evidence for
the correction or an untouched holdout. Full results and timing are in
[observed-season-245.md](observed-season-245.md).

## Historical data and evaluation

`data/history` contains 600 complete season directories, each with `feed.jsonl`,
`market.csv`, and `settlement.json`. Model fitting uses seasons 1–450; tuning uses
451–525. Seasons 526–600 were inspected during previous research and are reused
confirmation data, not an untouched holdout.

Earlier confirmation at normal simulated position limits, before the latest
execution-price correction:

| Liquidity assumption | Mean season P&L | Losing seasons | Worst season |
| --- | ---: | ---: | ---: |
| Deep | +$9,925.95 | 7 / 75 | −$15,710.93 |
| Thin | +$6,412.88 | 13 / 75 | −$17,076.71 |

These simulated results do not reproduce every live request delay, queue
position, partial fill, or exchange transition. Availability of historical data
does not establish that live code consumes it correctly or that future paths
will be profitable.

The latest entry-corrected comparison repeats all 675 scenarios on development
seasons 451–525 at **10% limits**, with three liquidity assumptions and three
delays. Shorter-delay means range from $1,434.31 to $1,584.50, with six losing
seasons per 75. At three seconds, means range from $1,027.27 to $1,118.30, with
8–9 losses per 75; the worst is −$1,097.41. Positive means do not imply that every
season, or a competition round, will be positive. Full paired results are in
[executable-entry.md](executable-entry.md).

## Earlier practice loss

The first full-size attempt lost $2,589.19 including cleanup ($2,589.80 including
earlier smoke trades). It started late with incomplete season history and placed
large positions from unreliable valuations. Delayed requests also allowed stale
decisions. Cleanup added $619.01 to the loss.

Merged fixes enforce complete history, fresh quotes, pending-news checks,
announcement pauses, and consistent season identity before submissions. The
captured failed-start replay now produces zero orders or conversions. Details and causal limitations are in
[practice-loss-review.md](practice-loss-review.md).

Three captured advisories differed from the published feed. With complete prior
history, replacing those advisories changed fair value by at most $0.265 per
share across the captured checkpoints. That is a valuation sensitivity result,
not a counterfactual profit calculation.

## Controlled live batch

Batch 01 ran the frozen version `59603dd` with 10% of normal per-symbol limits,
a three-complete-season target, a $250 cumulative net-loss trigger, and a
three-hour deadline ending 06:44:57 UTC. The trigger is not a guaranteed maximum
loss because in-flight fills and cleanup may add costs.

| Trial | Status | Result |
| --- | --- | --- |
| 1 | Completed; official settlement verified | +$141.16 |
| 2 | Interrupted; another trader's orders detected | Mixed account activity; not attributable to this strategy |
| 3 | Not started | — |

Live status is in `recordings/consistency-20261024/batch-01/status.json`.
`actions.jsonl` records submissions and settlement receipts; `final-receipt.json`
was written when the batch exited. Its clock identity check passed, but the
receipt contains reopened exposure and an unidentified order; it does not
establish successful cleanup or exclusive strategy P&L. Inter-round marked profit is not a completed
season result. No future outcomes from the active published season are used to
tune parameters or guide orders.

## Reviewed work merged in PR 4

[PR 4](https://github.com/jdishihara/ctc2026/pull/4) merged at 05:21 UTC as
`c9bdd50`. It contains the following independently reviewed changes and includes
the team's preceding main (`bb3a8ff`);
all **312 Python tests passed** on the combined code. Tests verify specified
behavior, not profitability.

- Bounded practice supervision, reconciliation, and official settlement receipts.
- Sticky account-ownership checks for unknown filled and open orders, missing
  acknowledgements, malformed account state, and reopened exposure. These checks
  do not lock the server account; another actor can trade between observations.
- Healthy periodic snapshots preserve completed warm-up; reconnects retain their
  required warm-up. Integrated commit `b3eb368` (reviewed source `c583144`).
- Per-leg basket retry clocks resume unsent hedge orders promptly. Integrated
  commit `afe2880` (reviewed source `b6d1111`). The first actual basket took about
  63 seconds and had −$8.73 market-trade cashflow.
- A recorded-market replay and a read-only official-settlement recorder. Neither
  sends orders or treats virtual profits as actual account returns.

The snapshot and basket changes were not in batch 01. Their live profitability
has not been demonstrated.

## Later integrated changes and experiments

- PR 5 preserves the fixed recorded-market evaluation grid.
- PR 6 corrects historical simulator activation times and final-round closure.
- PR 7 retains the execution-cost grid and season-242 capture evidence, including
  its recorder reconnect and uncertainty about quote completeness.
- [PR 8](https://github.com/jdishihara/ctc2026/pull/8) enforces entry-price bounds
  and checks stale partial/pending orders and fills during cancellation. The
  reviewed implementation and paired evidence are merged. Profit effects are
  mixed: shorter-delay historical means improve slightly, three-second means
  decline slightly, and two cost profiles gain an additional losing season.
- [PR 9](https://github.com/jdishihara/ctc2026/pull/9) adds an offline final-report-only
  diagnostic. It gives up most profit and still loses in some scenarios, so it
  does not replace the competition strategy. Future evaluation manifests now
  include model NPZ hashes; the older manifest limitation is documented.
- [PR 10](https://github.com/jdishihara/ctc2026/pull/10) adds the fixed closed-season
  worker, with source/output integrity checks and a final drain at the deadline.
- [PR 11](https://github.com/jdishihara/ctc2026/pull/11) adds optional HTTP connection
  reuse, with no automatic retries, proxy compatibility, and connection cleanup.
  It remains **off by default**. Read-only clock benchmarks and local failure
  tests are documented in [http-connection-reuse.md](http-connection-reuse.md);
  they do not demonstrate higher profit.
- [PR 12](https://github.com/jdishihara/ctc2026/pull/12) audits all 150 development
  scenarios at two delays. Every fill contribution reconciles with the unchanged
  baseline. HAVEN contributes the most to the worst loss and also has the largest
  positive average contribution. This does not justify removing it based on
  selected losses. See [loss-contributions.md](loss-contributions.md).

After integrating the teammate's Mario/Derivatives commit `aca0ec4`, the combined
branch passes **460 Python tests**, including the offline worker's
restart-integrity and cutoff checks. Independent reviews reproduced
representative results and checked every stored scenario pair. Neither the
entry correction nor final-report-only research has a new attributable live
trial. No live size increase or automatic strategy promotion follows from these
merges.

The subsequent uncertainty-guard experiment repeated 225 development pairs and
12 pairs on each of captures 241–243. It is **not promoted**: the three-second
development mean falls by $13.09 without reducing losses, and every scenario
on captures 242 and 243 earns less. Review fixes and all unfavorable evidence
are preserved in [uncertainty-guard-experiment.md](uncertainty-guard-experiment.md).
The research branch, including teammate main `870d31f`, passes 497 Python tests.
The candidate is offline only; the live strategy and frozen worker are unchanged.

The direct launcher also had a startup identity bug: initializing the strategy
before the first account refresh could erase loaded weather history on the
first quote callback. It now confirms the account and season identity before
initialization and refuses startup when that snapshot is unavailable. Supervised
practice already used the correct order; this does not explain its earlier loss.
See [startup-identity-fix.md](startup-identity-fix.md) for reproduction and scope.

## Why historical profit overstated the first live result

On the completed first season, historical-price replay at the same 10% limits
earned **+$1,628.94**. Replay of captured live quotes with a 0.25-second order delay,
baskets, and the old snapshot reset behavior earned **+$181.48**, closer to the
actual **+$141.16**. The replays differ jointly in executable prices, spread,
depth, timing, and live session handling; this is not a single-cause estimate.

The updated snapshot-and-basket version earned +$86.32 at a modeled 0.25-second
delay and **−$21.70 at three seconds** on that same captured path. More trading
does not automatically improve results. That earlier engine does not model
serialized HTTP requests or cancellation races; queue priority, own market
impact, and actual conversion execution remain unmodeled.

Full evidence: [recorded-market-diagnostic.md](recorded-market-diagnostic.md).

A separate production-client replay now models serial REST calls, status-only
acknowledgements, and account reconciliation. Its fixed 48 scenarios on
captures 241–243 completed after the startup identity correction. One loses
$29.72 (capture 243, one-second RTT, half depth, baskets enabled), and request
timing changes returns substantially. Eight independent reruns matched every
output field. These are reused paths under fixed latency assumptions, not
new live trials or 48 independent seasons. Full results, original failures,
and limitations: [serialized-client-replay.md](serialized-client-replay.md).

## Completed captured markets after the entry correction

The later research comparison reran the full strategy with current snapshot
behavior, three delays, full/half depth, and basket off/on: 12 scenarios for each
completed capture. The first three captures below were already examined;
capture 244 was added after its official close by the frozen worker.

| Captured season | Full-strategy range | Negative scenarios | Actual attributable result |
| --- | ---: | ---: | --- |
| 241 | −$21.70 to +$88.19 | 3 / 12 | +$141.16 on earlier runtime |
| 242 | +$1,462.74 to +$2,172.95 | 0 / 12 | None; shared account activity |
| 243 | +$156.65 to +$389.27 | 0 / 12 | None; no owned live trial |
| 244 | +$1,031.57 to +$1,189.38 | 0 / 12 | None; no owned live trial |

Capture 243 was evaluated by the frozen worker after its official 06:29 UTC
closing receipt. All 24 preselected scenarios, including older snapshot
behavior, were positive. News sequences 0–859 are complete; quote-path
completeness remains unproven. [Receipt, all results, and capture limits](observed-season-243.md).

Capture 244's selected interval begins at 06:31:19 UTC, after the earlier
worker's actual 06:11:57 startup (06:06 is its configured eligibility-window
start). All 24 of that worker's scenarios are positive. The serial REST grid
also has 16 positive rows, from $533.32 to $1,238.28. Its predeclared primary
scenario earns $628.14 but reaches a −$263.29 mark; supervisor loss stops and
cleanup are not modeled. For that later serial plan, 244 is carryover whose
receipt precedes its effective freeze, not prospective evidence. Both engines
were independently checked. [Full results, timing, risk, and provenance](observed-season-244.md).

The full older-snapshot ablations and unfavorable changes are also preserved in
[executable-entry.md](executable-entry.md). Waiting for all final reports earns
only $19.25–$22.25 on capture 241 and −$4.00–$5.60 on capture 242; it is retained
as a diagnostic baseline. All pairs and assumptions are in
[final-report-experiment.md](final-report-experiment.md).

## Remaining evaluation

Retain every result from batch 01, including its mixed second trial. Detect
unknown filled orders as well as open orders, and resolve the account conflict
before another live batch. The new ownership checks enforce the observed-history
requirement. A read-only observer now records official completed seasons until
12:00 UTC for offline evaluation. Evaluate execution
changes in a later run with their own version and bounds. Three positive
small-size seasons would be encouraging; they would not establish consistent
profitability, full-size performance, or performance against unseen competition
seasons and other teams.

Operational details: [controlled-practice.md](controlled-practice.md).

Completed-season diagnostic: [season-241-diagnostic.md](season-241-diagnostic.md).
Shared-account incident: [shared-account-incident.md](shared-account-incident.md).
