# Fixed bounded-retry evaluation on later closed captures

Declared 2026-10-24 10:28 UTC, before capture 248's official closing receipt
and before reading any of its future outcomes. The candidate runtime remains
exactly `27ab7c4` and is not retuned. The original 112-setting comparison is
complete and its final independent audit is pending. All existing forward
evaluators remain frozen at their earlier versions.

Evaluate each of captures 248 and 249 if its valid official settlement receipt
appears in the existing receipt ledger before 12:00 UTC. Use the same sealed
complete-line observation/feed inputs and all original forward eligibility,
attempt and final-prefix rules. A missing or rejected receipt is recorded,
not silently replaced. Do not inspect any active published season outcomes.

For each eligible capture, wait for the original reference, baseline and full
supervisor phases to pass their exactness/source gates. Cache only that closed
capture's frames and official receipt, checking their canonical hashes against
the original supervised metadata. Record all archive hashes in an immutable
specification. A separate comparison driver accepts only capture 248 or 249,
requires receipt time at or after this declaration and strictly before the
12:00 UTC cutoff, and preserves the prior comparison's safety checks and body.

Run all sixteen settings: RTT 0/0.05/0.25/1 seconds, full/half displayed depth,
baskets off/on. Keep 10% limits, 90 strategy actions per minute, zero prior
P&L and the $250 sampled loss trigger. Reproduce all original results and seven
standard journal files in the baseline phase before any candidate phase. Keep
all failed attempts, both phases, nine files per setting and all source hashes.

Require identical pre-cleanup requests/fills, stopping decisions and first-five
cleanup requests. Retain all terminal P&L, observed marks, drawdowns, cleanup
times and residual positions. Audit all actual POST/DELETE windows against 180
actions, and extra-pass actions against the conservative 90-event guard.
No live orders, credentials, network or downloaded-history reads are allowed.

Do not tune on either capture. Flag any worse worst P&L, increase in negative
outcomes, nonnegative-to-negative transition, new attention outcome, or
increased absolute residual exposure. Report every individual regression even
if the aggregate rules pass. A new residual reduction is informative but is
not required for a no-op confirmation. The primary stays 0.25 s/full/on.

Independently audit all paired rows and journals, and rerun a primary, a slow
setting and every newly affected attention case. If more than six affected
cases appear, audit all but declare a fixed representative subset before
rerunning. A later negative result triggers a review of promotion; it is not
hidden by the initial 112-setting success.

Receipt time and each selected interval will be compared with the actual
runtime and driver freeze times. Capture 248 began before this declaration,
so it cannot establish a fully prospective capture. Training overlap will be
checked only after closure; chronological freezes do not establish unseen
weather validation. No simulated result becomes an actual account return.
