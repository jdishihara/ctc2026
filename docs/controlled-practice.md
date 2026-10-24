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
arguments. Startup requires a flat account, no pre-run order history, no open orders, full bot-trading mode,
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
- Filled and cancelled order IDs are checked as well as open orders. Any observed
  unknown ID, missing acknowledged history, malformed history, or full 500-row
  page blocks practice and cleanup. There is no adoption of pre-run order IDs,
  including after rollover; start on a fresh unused season. Missing or invalid
  mutation acknowledgements leave ownership unresolved and prevent automatic
  flattening. A position already outside the practice limit stops strategy orders.
- `final-receipt.json` is attempted even if cleanup fails. An incomplete trial
  includes cleanup costs; a settled trial retains its confirmed settlement score.
  Separate fields report clock identity, observed-history ownership, flatness,
  and exposure reopened after cleanup. A clock match alone is not a clean exit.
  Sticky ownership blocks survive other stop reasons and mark unfinished trials
  as unattributable when account activity is mixed.
- To stop the owned runner normally, send `SIGINT` to its recorded PID. Avoid
  `kill -9`, which bypasses its reconciliation and final receipt.

## Interpretation

Keep the strategy parameters frozen during the batch. Review every season,
including losses, missed starts, data gaps, and execution failures. Three positive
small-size seasons would be encouraging, but would not establish consistent
profitability or full-size competition performance. Changes motivated by these
results need a separate later evaluation; do not tune to future published outcomes
from the season currently being traded.

The order-history endpoint currently returns a bounded list without pagination
metadata. The checks detect observed foreign activity and suspicious gaps; they
do not prove exhaustive history or provide exclusive account control. Another
trader can act between polls, and an external conversion may leave no order ID.
One active trader on this team account remains an operational requirement.
The incident that motivated these checks is in
[shared-account-incident.md](shared-account-incident.md).

The earlier full-size midseason failure and its merged fixes are documented in
[practice-loss-review.md](practice-loss-review.md).
