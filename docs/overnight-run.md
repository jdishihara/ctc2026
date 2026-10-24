# Overnight practice — October 24, 2026

User goal: keep trading and iterating overnight until the competition starts
around **08:00 EDT / 12:00 UTC on October 24**. Continue evaluating and fixing
problems between bounded batches; a batch stop does not finish the overnight
goal. Preserve every trial, loss, and cleanup cost.

## Current batch

- Version: `59603dd`; strategy parameters frozen.
- Output: `recordings/consistency-20261024/batch-01/`.
- Bounds: 10% position limits, three complete seasons, $250 cumulative net-loss
  trigger, deadline 06:44:57 UTC. The trigger is not a guaranteed maximum loss.
- Existing recorder and trader are already running. Read their process metadata
  and current status before starting anything; never duplicate the trading loop.
- A local-only status archiver records changed batch status and final receipts to
  `recordings/consistency-20261024/account-observations.jsonl`. It began at
  04:36:29 UTC and exits at 12:00 UTC. Earlier P&L marks are only sampled in the
  trader log; do not describe this archive as covering the entire first trial.
- Reviewed snapshot/reconnect fix: `c583144` on `arjun/snapshot-checkpoint`,
  isolated in `.worktrees/snapshot-checkpoint`; 269 tests passed.

## Next decisions

1. Finish or diagnose batch 01. Verify every settlement receipt, any stop reason,
   and account reconciliation. Open-position marks are not completed results.
2. Integrate the reviewed execution change between batches. Keep model and
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
