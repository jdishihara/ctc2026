# Overnight practice — October 24, 2026

## 09:04 UTC — narrower cleanup refresh experiment rejected

All 80 fixed comparisons and twelve independent representative reruns match.
Skipping a redundant refresh after an empty cancellation pass shortened mean
cleanup by 6.33 seconds, but worsened the worst terminal loss by $13.75 and
increased negative settings from 12 to 13. This fails the rules declared before
performance evaluation. The candidate remains on frozen experimental commit
`74c81f4`; production and forward evaluators remain unchanged.
See [cleanup-empty-cancel.md](cleanup-empty-cancel.md) for all outcomes and hashes.

## 08:53 UTC — training-overlap limitation discovered

All 15 complete storm tracks in already-closed captures 241–245 exactly match
the fitted analog library. These practice paths test execution on familiar
weather. Their chronological source freezes do not establish unseen-weather
validation. Actual receipts and paired execution arithmetic remain unchanged.
The frozen evaluations continue, and no active-season outcomes are read for
this audit. Evidence and corrections: [training-overlap-audit.md](training-overlap-audit.md).

User goal: keep trading and iterating overnight until the competition starts
around **08:00 EDT / 12:00 UTC on October 24**. Continue evaluating and fixing
problems between bounded batches; a batch stop does not finish the overnight
goal. Preserve every trial, loss, and cleanup cost.

## 08:35 UTC: cleanup quote-ordering candidate rejected

Both 80-setting phases completed with zero diagnostic errors. Baseline results
and journals match their archives exactly; candidate pre-cleanup behavior is
unchanged. Later quote retrieval plus a post-quote position check reduces book
age from nine to four RTTs, but three slow cleanup settings take longer and
the worst terminal loss increases from $420.64 to $441.76. Outcomes are better
in 3 settings, worse in 5 and unchanged in 72. Residual holdings are unchanged.
Independent review verified all 80 pairs and reproduced ten representative
runs exactly. Keep the existing runtime. The unpromoted experiment remains
at `5832359`; full negative evidence is in
[cleanup-quote-ordering.md](cleanup-quote-ordering.md).

Before evaluation, review caught a position race in the initial proposal; the
revised candidate verifies the full position vector after reading the quote.
No candidate code was used for live practice. Forward evaluators remain frozen
and continue recording/evaluating later closed seasons under their existing
protocols. Account ownership clarification is still pending.

## 08:12 UTC: capture 245 evaluated with the full supervisor

PR 20 merged the reviewed round-transition fix at 08:10:11 UTC. The next
closed capture's separate supervised evaluation finishes at +$362.85 in the
fixed primary setting. All 16 terminal outcomes are positive, but only 15
complete; one loss-stopped trial finishes flat at +$5.42 after closing fills.
All reference/baseline gates, supervised journals, representative reruns and
archived artifacts passed independent review. See
[observed-season-245.md](observed-season-245.md).

The corrected runtime stays frozen at `cd3eb23`; the separately reviewed
forward driver is frozen at `c5c35a3`. Its protocol records sealed input copies,
upstream archive provenance, every eligible receipt/attempt, and the final
complete-line prefix boundary at 12:00 UTC. Capture 245 began before the runtime
freeze, and its receipt precedes the driver freeze by 1.181 seconds. Do not call
it prospective evidence for the correction. The original frozen worker and
serialized evaluation continue unchanged. No owned live trading restarted.

## 08:03 UTC: corrected round-transition comparison completed

The reviewed narrow correction preserves valid waiting between a new storm's
formation and its first observation; submissions remain blocked during that
wait. All 64 baseline outputs and request/fill traces still match exactly.
The corrected supervisor has zero history stops, 53 completed trials, 11 loss
stops and 12 negative terminal outcomes. Primary results for captures 241–244
are +$52.93, +$1,497.40, +$286.36 and −$261.00. The worst stress outcome is
−$420.64, and two capture-244 cleanup cases retain positions. All 607 tests
passed before source freeze `cd3eb23` at 08:00:15 UTC. Independent result audit
is complete; see [practice-round-transition.md](practice-round-transition.md).
Live account ownership is still unresolved; no new owned live batch ran.

## 07:46 UTC: production-supervisor replay completed

The new fixed comparison retains all 64 supervised settings after exact
64-setting baseline and request/fill-trace checks. It produces 24 losses,
40 history stops, 8 loss stops and only 16 completed trials. Primary capture
244 finishes flat at −$261.00, versus +$628.14 in the core-client replay.
The inter-round history guard requires a separate fix; practice limits and
the loss trigger remain unchanged. Independent final result review is complete;
all 40 history stops were reproduced at valid round-2 or round-3 formations.
See [supervised-client-replay.md](supervised-client-replay.md) for all results
and the six cleanup-attention outcomes. Recording and both frozen evaluations
continue; no new owned live batch has run.

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

Update after the 06:29 UTC close: PRs 5–12 are merged. The entry-price correction is reviewed
and tested; its recorded-market and 675-run development profit effects are
mixed. Final-report-only trading was evaluated and is not promoted. No new live
batch has run, and the shared-account question remains unresolved. The latest
integrated Python suite has 460 passing tests after including teammate commit
`aca0ec4`. Optional HTTP connection reuse
remains off by default. The fixed worker evaluated the third captured season:
all 24 simulated outcomes were positive; the 12 using current snapshot behavior
ranged from $156.65 to $389.27. These are virtual results, not account profit.
The worker continues from frozen source `49a690e`; do not update its source or
HEAD while it runs. Current evidence and limitations are in
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

06:54 UTC research update: the uncertainty guard failed its fixed profit gates
and is not promoted. Both frozen versions completed all 522 runs, and their
results are identical on these inputs. Review corrected old-order cancellation
and closed-receipt validation gaps; the integrated Python suite passes 497 tests.
All evidence, including losses and retry-spacing limits, is in
[uncertainty-guard-experiment.md](uncertainty-guard-experiment.md). No new live
trial has started. A separate offline diagnostic is being prepared to measure
serialized request and account-reconciliation delays.

07:15 UTC update: PR #15 fixes direct-launcher initialization that could erase
loaded history on its first quote callback. Supervised practice already used
the correct order. The sequential REST diagnostic then completed all 48 fixed
scenarios on captures 241–243; one loses $29.72, and timing materially changes
returns. Independent review checked all rows and reproduced eight scenarios
exactly. The combined branch passes 536 Python tests. See
[serialized-client-replay.md](serialized-client-replay.md) for full results,
both archived versions, and the source-manifest limitation. No new live trial
has started; the shared-account ownership question remains unresolved.

07:23 UTC capture update: season 244 closed at 07:18:25 UTC. Its earlier frozen
24-scenario grid is positive throughout, with current behavior ranging from
$1,031.57 to $1,189.38. The later serial grid has 16 positive rows; its primary
scenario earns $628.14 but dips to −$263.29, and does not model supervisor loss
stops or cleanup. Independent reviewers reproduced four cases from each engine
and checked all rows/hashes. The serial source is now frozen at `505a5ad` for
later closes under PR #17's fixed plan. Capture 244 is explicitly carryover for
that plan. Both frozen checkouts remain unchanged; this is offline evidence
and no new owned live trial has occurred. See [observed-season-244.md](observed-season-244.md).
