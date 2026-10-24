# Preserve valid waits between storms — 2026-10-24

## Observed defect

The frozen production-supervisor comparison at `5d7d67b` produced 40 history
stops in 64 settings. Independent synthetic tests reproduce a false permanent
stop when a valid next `storm_formed` arrives separately from its first weather
observation. `live_history_ready` correctly remains false during that interval;
`PracticeSession.step` currently treats every such false value as corruption.
Do not alter the frozen replay worktree or its recorded results.

## Narrow correction

Scope the correction to `PracticeSession`. Keep model readiness and all order,
conversion, ownership, freshness, pending-news, cancellation and loss guards.
Record provenance of an accepted contiguous transition from a complete final-
reported round to the next round (only 2 or 3). Bind the temporary wait to the
same model object, competition/year and expected round. Permit waiting only
while account and news identities agree, the news prefix and outage history
remain complete, final reports are exactly the completed round prefix, and
the newly formed storm has no initial observation.
Clear waiting when readiness returns or any bound state changes.

Inspect history at each accepted news event during an attempted unfinished
trial, so a later message in the same callback cannot erase an invalid state.
A new-sequence duplicate/restarted/skipped formation must permanently stop the
journal. An ignored same-sequence retransmission or stale message must preserve
a valid wait. Do not weaken the current behavior on news/weather gaps, absent
prior reports, changed account/model/year, or genuine history corruption.

## Required evidence

- Failing regressions for split round-2 and round-3 transitions, repeated idle
  callbacks, and valid combined formation/age-zero batches.
- No orders or conversions while waiting; normal resting-order cancellation
  and warm-up remain in force, and eligibility resumes only with valid age zero.
- Duplicated/restarted/skipped formation, including a duplicate followed by age
  zero in one batch; ignored retransmissions and stale messages.
- Missing news, missing prior report, first weather above age zero, later
  weather gap; recovery messages cannot clear a permanent stop.
- Model/account/year changes cannot inherit a wait; all existing practice and
  live safety tests remain green.
- Pre-existing account/news identity disagreement or unknown account identity,
  and extra future-round final reports, cannot qualify for the exception.
- Independent code review before a new source freeze and fixed comparison.

After the correction, repeat the same captures 241–244 and 16 settings each,
with zero prior P&L, 10% limits, the unchanged $250 trigger, and the existing
baseline/trace/provenance gates. Retain the original comparison and all new
errors, losses, incomplete cleanup and stops. This is a correctness fix tested
on reused paths, not a new untouched strategy evaluation. Do not change any
threshold or choose parameters based on these outcomes. Separately recorded
future captures remain governed by their existing frozen protocols.

Reuse the already verified 64 reference rows and trace hashes from source
`505a5ad` in `out/supervised-replay-v1-20261024/reference`. Its source remains
unchanged. Rerun all 64 baseline settings with the corrected source, require
exact archive/trace equivalence, then run all 64 supervised settings. Include
this correction plan in the new source manifest. The reference input, result
and completion hashes must still pass the existing predecessor checks.
