# Competition readiness — 2026-10-24

Status recorded at 04:31 UTC (00:31 EDT). Live results below are provisional
until official settlement receipts are recorded.

## What the evidence supports

The historical strategy is profitable on average in the local simulator, but
losing seasons remain. The earlier live loss exposed execution defects; those
defects have been fixed and regression-tested. Complete live-season profitability
has not yet been established. Neither the historical average nor the test count
establishes a probability of winning the competition.

## Historical data and evaluation

`data/history` contains 600 complete season directories, each with `feed.jsonl`,
`market.csv`, and `settlement.json`. Model fitting uses seasons 1–450; tuning uses
451–525. Seasons 526–600 were inspected during previous research and are reused
confirmation data, not an untouched holdout.

Latest confirmation at normal simulated position limits:

| Liquidity assumption | Mean season P&L | Losing seasons | Worst season |
| --- | ---: | ---: | ---: |
| Deep | +$9,925.95 | 7 / 75 | −$15,710.93 |
| Thin | +$6,412.88 | 13 / 75 | −$17,076.71 |

These simulated results do not reproduce every live request delay, queue
position, partial fill, or exchange transition. Availability of historical data
does not establish that live code consumes it correctly or that future paths
will be profitable.

## Earlier practice loss

The first full-size attempt lost $2,589.19 including cleanup ($2,589.80 including
earlier smoke trades). It started late with incomplete season history and placed
large positions from unreliable valuations. Delayed requests also allowed stale
decisions. Cleanup added $619.01 to the loss.

Merged fixes enforce complete history, fresh quotes, pending-news checks,
announcement pauses, and consistent season identity before submissions. The
captured failed-start replay now produces zero orders or conversions. Main has
238 passing tests. Details and causal limitations are in
[practice-loss-review.md](practice-loss-review.md).

Three captured advisories differed from the published feed. With complete prior
history, replacing those advisories changed fair value by at most $0.265 per
share across the captured checkpoints. That is a valuation sensitivity result,
not a counterfactual profit calculation.

## Controlled live batch

Batch 01 runs the frozen version `59603dd` with 10% of normal per-symbol limits,
a three-complete-season target, a $250 cumulative net-loss trigger, and a
three-hour deadline ending 06:44:57 UTC. The trigger is not a guaranteed maximum
loss because in-flight fills and cleanup may add costs.

| Trial | Status | Result |
| --- | --- | --- |
| 1 | Round 2 in progress | No official settlement yet |
| 2 | Not started | — |
| 3 | Not started | — |

Live status is in `recordings/consistency-20261024/batch-01/status.json`.
`actions.jsonl` records submissions and settlement receipts; `final-receipt.json`
is written when the batch exits. Inter-round marked profit is not a completed
season result. No future outcomes from the active published season are used to
tune parameters or guide orders.

## Reviewed work awaiting integration

- [PR 4](https://github.com/jdishihara/ctc2026/pull/4): bounded practice supervision,
  reconciliation, and verified settlement accounting; 264 tests passed before
  batch 01 started.
- Branch `arjun/snapshot-checkpoint`, commit `c583144`: healthy periodic
  snapshots preserve completed warm-up. A separate reconnect flag ensures news
  arriving before a reconnect snapshot cannot skip warm-up. Independent review
  approved the fix; all 269 tests passed. It is isolated from batch 01 and has not
  been evaluated for live profitability.

## Remaining evaluation

Complete and retain every result from batch 01, including losses or failed
trials. Reconcile settlement and cleanup before another batch. Evaluate execution
changes in a later run with their own version and bounds. Three positive
small-size seasons would be encouraging; they would not establish consistent
profitability, full-size performance, or performance against unseen competition
seasons and other teams.

Operational details: [controlled-practice.md](controlled-practice.md).
