# Competition readiness — 2026-10-24

Status recorded at 05:20 UTC (01:20 EDT). One complete small-size live season
has a verified settlement receipt. The next trial contains mixed activity.

## What the evidence supports

The historical strategy is profitable on average in the local simulator, but
losing seasons remain. The earlier live loss exposed execution defects; those
defects have been fixed and regression-tested. One completed live season was
positive; consistent live profitability has not been established. Neither the historical average nor the test count
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

## Why historical profit overstated the first live result

On the completed first season, historical-price replay at the same 10% limits
earned **+$1,628.94**. Replay of captured live quotes with a 0.25-second order delay,
baskets, and the old snapshot reset behavior earned **+$181.48**, closer to the
actual **+$141.16**. The replays differ jointly in executable prices, spread,
depth, timing, and live session handling; this is not a single-cause estimate.

The updated snapshot-and-basket version earned +$86.32 at a modeled 0.25-second
delay and **−$21.70 at three seconds** on that same captured path. More trading
does not automatically improve results. Queue priority, market impact, serialized
HTTP requests, cancellation races, and conversion delays remain unmodeled.

Full evidence: [recorded-market-diagnostic.md](recorded-market-diagnostic.md).

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
