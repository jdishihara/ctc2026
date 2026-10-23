# Competition PnL continuation

User direction: keep improving the algorithm to compete to win. Baseline for this
continuation: `e8d4307`, including the first efficiency/execution patch. Continue
on `arjun/ctc-efficiency`; preserve the existing draft PR and all evidence.

## Design and rulings

- Optimize measured competition PnL subject to the repository's loss-tail rule.
  Faster computation alone does not finish this continuation.
- The code normally rebalances every 15 seconds. Test 8/4 seconds for reaction
  speed and 30 seconds as a lower-turnover control. Enforce 120 actions/minute in
  every candidate and reference replay, matching the live default.
- Current sizing divides by `edge_full - floor`; a floor above `edge_full`
  collapses the denominator and produces full size immediately above the floor.
  Add an optional minimum excess-edge width (`edge_ramp`) of 0.01 or 0.03. Keep
  zero as the compatibility setting until evidence supports a default change.
- Run these five alternatives plus baseline on all 75 tune seasons, both deep
  and thin. Choose by the existing tune score, requiring both means to rise and
  thin p10 to deteriorate less than 10%. If separate cadence and sizing changes
  pass, test their single combined configuration on tune before freezing a
  candidate. Do not search on verification seasons.
- Compare the frozen candidate with baseline on 526–600 once. Report paired
  uncertainty, per-season outcomes, tails, actions, and rejection counts. Follow
  the repository's same acceptance rule; keep rejected candidates explicit.
- Fix any diagnosed implementation defects with failing regression tests first.
  Keep logs and small reproducible summaries. No fitted model/history changes.
- The exchange accounting discrepancy needs the missing live recordings. They
  are absent from this checkout and the obvious local locations; requested them
  asynchronously. Continue offline work while awaiting them. No remote orders.
- User explicitly requested continued execution; routine design and experiment
  choices above are agent rulings, not a request for another approval.

## Tasks

- [ ] Add behavioral tests for continuous sizing, both signs, compatibility and
  invalid parameters; implement the optional sizing width.
- [ ] Build a deterministic tune experiment runner with real action-budget
  accounting; reproduce baseline output before interpreting alternatives.
- [ ] Evaluate the predeclared candidates, inspect paired results, and freeze a
  single candidate without using verification outcomes to choose it.
- [ ] Verify the frozen candidate and stress action/latency behavior. Promote
  defaults only if the predeclared acceptance rule passes.
- [ ] Investigate the live accounting discrepancy if the requested logs arrive;
  otherwise add a reproducible trade/account audit utility for the missing data.
- [ ] Review consequential changes, verify the complete suite, publish evidence
  and update the existing PR. Continue with the next evidence-supported lead.

## Review focus

Defaults and launch/preflight commands must agree. Sizing must be symmetric and
bounded; no higher order rate may silently assume the simulator's old 300-action
budget. Repeated experiment runs must not mix outputs or overwrite other jobs.
Candidate selection must not consume verification results. Accounting audits
must not manufacture missing fills or confuse round reset with realized profit.

## Progress

2026-10-23, Codex: inspected source and the prior experiment ledger. Existing
parameter grids did not vary rebalance cadence or remove the sizing discontinuity.
Confirmed live recordings and the old scratch realized-PnL script are untracked
and absent locally. The initial PR is complete and remains the baseline.

### First experiment results and next hypothesis

All five alternatives were rejected on tune, without running verification.
Tune score baseline 5016.76; 8s 4471.99; 4s 3839.30; 30s 4845.40; 1% ramp
3375.07; 3% ramp 2178.54. Faster 8s improved means by 172/94 but thin p10 fell
36.6%. The 4s configuration hit the 120-action limit three times. Baseline
matches the existing CSVs and peaks at 42/47 actions, with no rejections.

Ruling: keep default cadence and sizing unchanged; the new ramp is experimental.
The passive-quote rounding discontinuity is real, but replacing it is a strategy
change and the tested replacements reduced PnL substantially.

Next hypothesis: condition historical future radius/intensity on their currently
observed values. Current forecasts match position/path but otherwise keep each
historical analog's strength. Fit age-to-age linear response coefficients only
from the existing 1–450 library, then shift each analog's future strength by its
response to the observed-minus-historical current strength. Preserve the analog
path weights and uncertainty across residual futures. Zero-variance training
ages supply a zero response; constrain radius positive and intensity nonnegative.

Ruling: adding this response fit is permitted for this next experiment; prior
parameters and history stay unchanged. Training-only coefficients improve simple
unconditional radius/intensity predictions by 7–22% RMSE on selected tune-time
horizons, so this is evidence-supported work rather than another sizing grid.
Test one full-strength candidate on both tune regimes. Freeze it only if the
same score/mean/p10 rules pass; do not select on verification.

Wind conditioning was rejected on tune: means 8514.08/5380.58, thin p10 -6813.63,
score 3540.52. Fewer losing seasons does not override the predeclared tail rule.

Next bounded hypothesis: use the existing exact rebuilder settlement formulas
only after the final reports for all three rounds have arrived. Earlier trials
used exact formulas throughout uncertain future storms; this alternative keeps
that behavior unchanged until the season's damage is known. Use exact residuals
only in that same final phase, update the ETF basket consistently, and keep the
choice on each model instance. Evaluate this single candidate on tune first.

Final-only exact formulas passed tune: means 8601.09/5166.86 with unchanged
p10, versus 8577.71/5155.03. A separate training-data audit reproduced a report
reconciliation defect: 75/1500 company/final-report observations differed by more
than .01 points, maximum 2.5564. Saturated sites discarded reported damage, and
snapshots with no track allocated percentages against original capacity rather
than remaining capacity. Four failing regressions reproduced it. Bounded
redistribution now matches all 1500 training reports to 3.4e-11 points.

Ruling: correct report reconciliation before selecting the next strategy; do not
preserve a known conflict with observed official reports for an accidental edge.
Cost if wrong: a changed inferred allocation among sites may affect later-storm
forecasts. Re-evaluate the complete strategy against the original continuation
baseline. With the correction, final-exact tune means are 8615.26/5156.88 and
thin p10 -3712.89; this package still passes the original acceptance bounds.

Next test: after all three final reports, residual uncertainty falls sharply,
but the strategy retains the same 2.5% global entry floor. Evaluate final-phase
floors 0.5% and 1.0%, retaining the per-symbol two-residual-SD floor and original
2.5% before all three reports. Combine with exact final valuations. Select on
tune score subject to the original mean/p10 gates, then freeze once.

Also predeclare one final-phase sizing candidate: 0.5% entry and 1% full-size
edge, retaining the original 3% full-size threshold before all final reports.
The original 3% threshold was tuned for uncertain storms; after final reports,
many symbols' fitted residual is only 0.05–0.10 currency units. Keep the residual
floor in every phase. This hypothesis is declared before the final-edge run
finishes and before any verification result is examined.

Final 0.5%/1% entry alone lost tune score (4964.77/5022.23); 0.5% entry with 1%
full-size passed, score 5033.08, means 8627.18/5168.43. Source inspection explains
why a lower floor alone can lose: when holding a large favorable position, the
new low edge floor enters the rebalance branch and trims it to a small target,
giving up positive expected settlement PnL. Before the gate, uncertainty makes
that reduction defensible; after complete reports the model errors are small.

Confirmed final exact valuation errors on 150 training seasons: RMSE PORT .061,
GRID .050, FERRY .069, GEN .076, ARCH .168, REBLD .077; ISLE/AQUA/RECON/MAT/HAVEN/
REIN .001–.004. Predeclare one final-limit candidate with both entry/full edge
0.5%, still bounded by each symbol's two-residual-SD floor. It takes the allowed
position only when the final settlement edge clears that floor. Compare tune;
this is the last final-phase candidate before freezing a verification run.

## Frozen candidate

Select `final_limit` after tune only: corrected report reconciliation,
`final_exact=True`, `final_edge=0.005`, `final_edge_full=0.005`; all earlier-phase
parameters, 15s cadence, zero sizing ramp, and zero wind conditioning stay as
before. Tune means 8643.9786 / 5176.6919 versus 8577.7072 / 5155.0285; thin p10
-3729.4505 versus -3699.2198 (0.817% worse); score 5045.61 versus 5016.76.
Peak actions 42/47, no rejected orders or rate blocks. It has the best eligible
tune score after enforcing correct report reconciliation.

Run verification 526–600 once for `baseline` (report correction only, an ablation)
and `final_limit`, comparing the frozen full candidate primarily against the
original continuation baseline `e8d4307` CSVs. Do not select among alternatives
using verification. Also stress 2s latency on tune for corrected baseline and the
frozen candidate. Defaults are not promoted until the acceptance check passes.

Accounting utility: 15 regression cases pass, covering flips, duplicates, fees,
opening state and ordering ambiguity. Independently replayed all 323 simulated
fills for season 451; end positions and total PnL match exactly (0.0 error).
Actual testnet discrepancy still awaits the requested recordings.

Current full suite: 78 passed. All new behavioral changes were exercised by
failing tests before implementation. One independent final review remains.
