# Controlled simulated practice

The first batch uses the accepted strategy with 10% of normal per-symbol position
limits, three complete seasons, a $250 cumulative simulated P&L loss trigger, and
a three-hour deadline. These are execution and evaluation bounds. The loss trigger
is not a guaranteed maximum loss: fills in flight and cleanup can add costs.

Start a read-only feed recorder before the season begins. Use one trading process
on the shared account and a new output directory for each explicitly reviewed batch:

```bash
.venv/bin/python bot/practice.py \
  --feed-log recordings/consistency-20261024/feed.jsonl \
  --out recordings/consistency-20261024/batch-01 \
  --fraction 0.1 --loss-trigger 250 --seasons 3 --hours 3
```

The runner reads `.botkey` locally. The key never needs to appear in its process
arguments. Startup requires a flat account, no open orders, full bot-trading mode,
and the Hurricane Season game. It waits for round one with complete history and
an observation age no greater than 40 seconds. All ordinary live history,
pending-news, quote freshness, announcement, and season-identity guards remain.

## Results and stops

- `status.json` records every armed season, current P&L, attempts, position limits,
  deadline, and the latched stop reason. Reusing a run directory is refused.
- `actions.jsonl` records mutation attempts before submission, responses, cleanup,
  and settlement receipts. ETF conversions and lost acknowledgements count as
  activity even if no order ID is returned.
- A completed result requires all three final reports, a closed market, matching
  account identity around the receipt, official settlement prices, finite cost
  bases, and no open orders. Settled totals cannot be overwritten by later marks.
- The cumulative loss trigger includes all attempted seasons. Settlement checks
  enforce it immediately. No failed run is silently discarded or auto-restarted.
- After a stop, the worker finishes before cleanup starts. Cleanup cancels only
  acknowledged owned IDs, verifies cancellation, rechecks the competition and
  account before each reduction, and uses current holdings. Unknown orders or a
  changed competition stop cleanup and leave an explicit `attention` status.
- `final-receipt.json` is attempted even if cleanup fails. An incomplete trial
  includes cleanup costs; a settled trial retains its confirmed settlement score.
- To stop the owned runner normally, send `SIGINT` to its recorded PID. Avoid
  `kill -9`, which bypasses its reconciliation and final receipt.

## Interpretation

Keep the strategy parameters frozen during the batch. Review every season,
including losses, missed starts, data gaps, and execution failures. Three positive
small-size seasons would be encouraging, but would not establish consistent
profitability or full-size competition performance. Changes motivated by these
results need a separate later evaluation; do not tune to future published outcomes
from the season currently being traded.

The earlier full-size midseason failure and its merged fixes are documented in
[practice-loss-review.md](practice-loss-review.md).

## Periodic snapshots and reconnects

Routine snapshots arrive during a healthy live connection. When their round and
sequence checkpoint agree with the complete model history, they preserve the
existing warm-up clock. Treating each checkpoint as a round opening suppressed
otherwise valid signals until another full warm-up interval elapsed.

A disconnect sets a separate pending-warm-up flag. Restoring continuous news can
make the history current before a snapshot arrives; either recovery order must
start reconnect warm-up before new signals are allowed. Missing weather or news
still blocks trading, and actual market reopening still starts warm-up.

This change was reproduced with order-level offline regressions and independently
reviewed. The first live batch remains pinned to `59603dd`, before this change;
its results cannot establish the profitability of the snapshot change.

## Staggered basket hedge submissions

The first ARCH basket in batch 01 created five shares at 00:39:28 EDT and
finished replenishing its components at 00:40:31. Its market trades generated
−$8.73 of cashflow before any separate fees; the final inventory change from the
cycle was zero. The recorded fills are in
[evidence/basket-01-fills.json](evidence/basket-01-fills.json).

Each component hedge was roughly ten seconds behind the previous one. An
offline reproduction confirmed that the shared retry timer delayed legs that
had never been submitted when a slow acknowledgement or pending news interrupted
the first batch of orders. Recovery now tracks each leg separately: unsubmitted
legs can proceed as soon as readiness and fresh quotes return, while previously
submitted legs retain their retry delay and cancellation/reconciliation checks.

This removes an avoidable delay. The recorded loss does not establish what the
same basket would have earned with faster execution. The initial live batch uses
the older implementation; the fix requires a later live evaluation.
