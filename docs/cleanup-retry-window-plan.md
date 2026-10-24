# Bounded cleanup retry experiment

Declared 2026-10-24 10:06 UTC, before implementation or candidate performance
evaluation. This is a diagnosis-driven comparison on already inspected closed
captures 241–247, not an untouched holdout. Production and all existing forward
evaluators remain unchanged during the experiment. No live orders are authorized
while the shared-account ownership question remains unresolved.

## Identified failure

Three original zero-RTT capture-247 outcomes retain REIN −6 after five cleanup
passes finish at simulated time 2172.5. The last quote is too old for the frozen
replay's five-second freshness rule. The next recorded quote arrives at
2173.325811, with sufficient displayed ask size even at half depth. No REIN
cleanup order was attempted and observed action counts were below the cap.
This establishes a retry-timing failure conditional on the replay assumptions;
it does not establish a profitable alternative execution.

## One fixed candidate

1. Preserve all work in the first five cleanup passes, including request order,
   sleeps, safety checks, quoting and price rules.
2. Record cleanup entry using the existing monotonic clock. Allow additional
   passes to start while elapsed time is at most 61 seconds. Cap total passes
   at 62. Keep one-second sleeps. Stop early when safely flat, settled, or when
   any existing identity, ownership, history or reconciliation guard fails.
   Do not reset the deadline on progress. Preserve the existing final refresh.
3. The first five passes may themselves take longer than 61 seconds; requests
   in an admitted extra pass may also overrun the horizon. This is a bound on
   admitting extra passes, not a hard total wall-clock deadline.
4. Maintain a private monotonic mutation ledger from the existing journal event
   stream. Count completed POST/DELETE request events, cleanup cancellation
   events and cleanup order events once each, conservatively including rejected
   or locally denied attempts. Do not also count request_attempt events. Keep
   the serialized journal bytes unchanged. Use timestamps after each operation
   so slow operations are retained conservatively.
5. Only extra-pass mutations consult this shared ledger. Before either a new
   order or direct cancellation, require fewer than 90 counted events in the
   inclusive preceding 60 seconds. Prune only timestamps strictly older than
   now minus 60. Deferral occurs locally before send/place and must not create
   a fake missing acknowledgement. Missing or invalid accounting fails closed.
   The first five passes keep their existing rate behavior; the new guard does
   not retroactively establish a shared-budget guarantee for those passes.
6. No forecasting, position limits, loss trigger, history readiness, settlement,
   account ownership or strategy parameters change. Recognition stays disabled.

The exact shadow-ledger and fail-closed design will receive preflight review
before source freeze. Safety corrections before any performance run are allowed
and must be logged; the 61-second horizon, 62-pass cap and 90-event guard will
not be chosen using candidate P&L.

## Verification before performance

Use failing tests before implementation, then focused and full suites. Exercise
late/no quote refresh, partial fills, cancelled or unconfirmed orders, lost
acknowledgements, foreign orders/fills, rollover, saturated rolling budgets,
strict 60-second expiration, monotonic versus wall-clock changes, slow requests
and the extra-pass horizon. Offline tests deny network/credentials/history.

Freeze and commit runtime, tests and driver. Independently review the exact
source and guard behavior with synthetic inputs before performance evaluation.
The baseline runtime must match frozen cd3eb23 byte-for-byte. Only
bot/practice.py may differ in candidate runtime. Guard exceptions must latch so
production exception handling cannot silently convert a violation to success.

## Complete fixed comparison and decision

Use all seven closed captures 241–247 and all sixteen settings each:
RTT 0/0.05/0.25/1 seconds × full/half displayed depth × baskets off/on.
Both phases contain 112 settings, at 10% limits, 90 strategy actions per minute,
zero prior P&L and the unchanged $250 sampled observed-loss trigger.

Baseline must reproduce every original supervised result and all 784 original
journal files before candidate runs. Preserve immutable input/source hashes and
all failed invocations. Candidate must match all pre-cleanup requests/fills,
stopping decisions and all requests within the first five passes exactly.
Record all cleanup requests, fills, durations, final receipts, residual holdings,
terminal P&L and complete rolling mutation counts. Any guard violation or source
change invalidates the comparison. Audit the exchange's 180-per-minute ceiling
across the entire request stream and the additional 90-event guard for extra
mutations; do not infer it from the fresh CleanupExchange action deque.

Reject if worst terminal P&L worsens, negative outcomes increase, any previously
nonnegative setting becomes negative, any new attention outcome appears, or
absolute residual exposure increases in any symbol/setting. Retain individual
regressions even if aggregate gates pass. Require a strictly reduced residual
position in at least one existing attention outcome to justify integration.
The primary remains 0.25-second RTT/full depth/baskets on.

Independently verify every paired row and journal hash and reproduce affected
attention cases plus a primary and slow-request case. No retuning after seeing
these results; a failed candidate remains unmerged. Successful code would still
require review, explicit report of every limitation and shared-account ownership
resolution before any owned live practice resumes.
