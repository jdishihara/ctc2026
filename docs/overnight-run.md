# Overnight practice — October 24, 2026

User goal: keep trading and iterating overnight until the competition starts
around **08:00 EDT / 12:00 UTC on October 24**. Continue evaluating and fixing
problems between bounded batches; a batch stop does not finish the overnight
goal. Preserve every trial, loss, and cleanup cost.

## Batch 01 stopped; shared-account conflict under investigation

- Version: `59603dd`; strategy parameters frozen.
- Output: `recordings/consistency-20261024/batch-01/`.
- Bounds: 10% position limits, three complete seasons, $250 cumulative net-loss
  trigger, deadline 06:44:57 UTC. The trigger is not a guaranteed maximum loss.
- First season completed at **+$141.16**. The second was interrupted after an
  external 200-share PORT sale appeared. Our journal's first order was a buy of
  180 shares, reducing that exposure to the intended 20-share limit. This was
  not a reset of our position limits.
- The trading process exited after SIGINT. Cleanup briefly observed a flat
  account, but another unowned order reopened PORT during the final receipt.
  The second trial is mixed activity and cannot establish our strategy's P&L.
- The read-only recorder and local status archiver remain running. No local
  trading Python process remained in the process inventory at 05:00 UTC.
  Resolve the shared-account conflict before another live batch. Do not cancel
  unidentified orders or flatten another trader's positions.
- A local-only status archiver records changed batch status and final receipts to
  `recordings/consistency-20261024/account-observations.jsonl`. It began at
  04:36:29 UTC and exits at 12:00 UTC. Earlier P&L marks are only sampled in the
  trader log; do not describe this archive as covering the entire first trial.
- Reviewed execution fixes are integrated into the PR 4 branch as `b3eb368`
  (snapshot/reconnect handling) and `afe2880` (per-leg basket retry clocks).
  Neither change was in batch 01. The combined branch, including main `bb3a8ff`,
  passed all 312 Python tests.
- Unknown-order and malformed-account guards are implemented in `9584423`.
  These stop further owned trading but cannot provide a server-side account lock.
- Read-only market observer PID 34251 (runtime `4ec85d2`) records clocks and
  official settlement prices into `market-observations.jsonl` until 12:00 UTC.
  It uses only three GET endpoints and relies on the existing feed recorder.
  `caffeinate` PID 34252 keeps the machine awake while that process runs; closing
  the lid still requires the laptop's normal supported awake configuration.

## Fixed recorded-market evaluation plan (05:20 UTC)

Keep strategy parameters and 10% position limits unchanged. After each captured
season is officially closed, evaluate order delays of 0.25, 1, and 3 seconds,
with full and half displayed liquidity, baskets on/off, and periodic snapshot
warm-up reset on/off. Report all 24 combinations, including losses; do not choose
new parameters from these outcomes. Receipt validation must precede outcome use.

These are virtual fills on newly captured market paths. They are not our actual
account profits, and the published historical seasons are not an untouched
model holdout. Quote gaps, missing news, official identity, and settlement
coverage must be reported before interpreting results. Full assumptions are in
[recorded-market-diagnostic.md](recorded-market-diagnostic.md).

## Next decisions

Update at 06:08 UTC: PRs 5–9 are merged. The entry-price correction is reviewed
and tested; its recorded-market and 675-run development profit effects are
mixed. Final-report-only trading was evaluated and is not promoted. No new live
batch has run, and the shared-account question remains unresolved. The latest
integrated suite has 378 passing tests. Current evidence and limitations are in
[competition-readiness.md](competition-readiness.md).

1. Resolve the shared-account conflict before resuming live practice. Detection
   of unknown orders that fill between polls has been strengthened. Preserve the interrupted trial and its raw
   receipts. Open-position marks are not completed results.
2. PR 4 merged at 05:21 UTC as `c9bdd50`. Keep model and
   strategy parameters fixed for its initial live evaluation.
3. Start each later batch in a new output directory after checking account state,
   version, size, loss trigger, available time, and complete-history readiness.
4. Use observed execution failures to guide fixes. Evaluate strategy changes on
   the designated development data and a later live batch. Do not optimize using
   future published outcomes from an active season or call reused data an
   untouched holdout.
5. Consider larger practice size only after completed results and reliable
   execution justify it. Record the reason and changed bounds; do not silently
   increase exposure to recover a loss.
6. Schedule the final batch to finish before the competition, allowing time to
   reconcile, integrate verified changes, and produce a team handoff. Continue
   analysis and readiness work through the remaining time. Practice trading must
   not spill into the competition without a new instruction.

Readiness evidence: [competition-readiness.md](competition-readiness.md).
Runner behavior and shutdown: [controlled-practice.md](controlled-practice.md).
