# Fixed half-weight recognition blend

**The fixed 50/50 blend is rejected for integration after capture 247.** It
passed its initial offline gates on captures 241–246, but the supplemental
check has twelve negative settings and increased residual exposure in two
cleanup outcomes. Both sets of results are retained. No account orders were
placed, and live account ownership remains unresolved.

The experiment is frozen at `7a2fe81b1167bb1b355357b0d105ea91ed29cd05` under
[repeat-blend-plan.md](repeat-blend-plan.md). The original one-hot candidate
remains rejected; see [repeat-prefix.md](repeat-prefix.md).

## Model and activation

The unchanged recognizer requires at least 21 complete observations, every two
seconds from age zero, and exact agreement in x/y/radius/intensity with one
unique fitted-library track over the entire observed prefix. It reads no
matching column after the latest observed age. Corrections trigger a fresh match
check; gaps, invalid values, ambiguity or divergence restore the ordinary model.

For a valid match, weights are exactly 50% ordinary ensemble plus 50% recognized
track. The ordinary cache continues updating. This changes forecast means,
dispersion and related trading decisions together; the experiment does not
isolate a causal effect of uncertainty alone.

Recognition is not being added to production. The proposed optional
`--repeat-prefix-blend` switch in `bot.practice` and `bot.live` selects only the
tested 0.5 coefficient on the unmerged experimental integration branch.
It is incompatible with nowcast mode. Validation precedes credential/account
I/O, and startup diagnostics record the selection. No limits, history or
ownership checks, sampled loss trigger, cleanup rules or frozen forward
evaluators are changed. The integration plan is
[repeat-blend-integration-plan.md](repeat-blend-integration-plan.md).

## Initial complete comparison

All six closed captures use RTT 0/0.05/0.25/1 second, full/half displayed depth
and baskets off/on: **96 settings per phase**. Limits remain 10%, with 90 actions
per minute, zero prior P&L and the unchanged $250 sampled observed-loss trigger.
Baseline reproduces all 96 archived result rows and 672 original journal files
before candidate evaluation. Both phases finish with zero errors, forbidden
accesses or source changes.

| Metric | Original supervised baseline | Half-weight blend |
| --- | ---: | ---: |
| Mean terminal P&L | $678.13 | $1,139.53 |
| Worst terminal P&L | −$420.64 | +$174.71 |
| Best terminal P&L | $2,236.76 | $2,376.68 |
| Positive / negative settings | 84 / 12 | 96 / 0 |
| Completed / incomplete trials | 84 / 12 | 96 / 0 |
| Settled / flat / attention receipts | 84 / 10 / 2 | 96 / 0 / 0 |

There are 92 improvements and four regressions. All four regressions occur on
capture 245 at zero RTT and remain profitable and settled:

| Depth | Baskets | Baseline | Blend | Change |
| --- | --- | ---: | ---: | ---: |
| Full | Off | $597.20 | $568.74 | −$28.46 |
| Full | On | $692.51 | $665.63 | −$26.88 |
| Half | Off | $505.65 | $486.24 | −$19.41 |
| Half | On | $546.46 | $528.63 | −$17.83 |

Independent fill accounting reconciles each difference: smaller AQUA holdings
and worse RECON sale proceeds outweigh GRID gains and, at half depth, PORT
gains. Conversion requests are identical. Cleanup fills do not explain these
differences. No regression is omitted or treated as zero.

### Fixed primary setting

Primary is unchanged: 0.25-second RTT, full displayed depth, baskets on.

| Capture | Baseline | Blend |
| --- | ---: | ---: |
| 241 | $52.93 | $504.95 |
| 242 | $1,497.40 | $1,698.78 |
| 243 | $286.36 | $622.73 |
| 244 | −$261.00 | $1,336.94 |
| 245 | $362.85 | $406.29 |
| 246 | $1,539.17 | $2,047.19 |

### Interim risk remains material

Candidate server marked P&L reaches **−$257.845** and maximum peak-to-trough
marked drawdown is **$947.425**. Four capture-244 settings at 0.05-second RTT
briefly cross −$250 between supervisor observations. Their minimum observed
supervisor marks are −$194.815 at full depth and −$198.495 at half depth, so no
stop fires. Completing every replay does not mean marks always stayed above
the trigger. The trigger is not a hard bound on realized or terminal loss.

The separate one-hot loss attribution is retained in
`docs/evidence/repeat-blend/onehot-attribution/`. It reconciles capture-244
liquidation losses and an explicitly ex-post valuation of unchanged holdings
at eventual settlement. That diagnostic is not a realizable alternative policy
or evidence that holding through those losses would have been feasible.

## Development fallback and independent verification

All 75 development pairs on seasons 451–525 and all 225 storm scans are
byte-identical to the independently audited one-hot experiment's unmatched
fallback results. No prefix activates. Both modes average $1,476.43, with worst
−$723.10, best $4,132.79 and six negative seasons. This verifies unchanged
fallback on reused data; it establishes no recognition benefit.

Independent capture review verifies all 96 pairs, 746 source/input artifacts,
58 Git blobs and 1,728 journal/profile files. All 864 baseline files match the
prior audit. Seven candidate reruns reproduce every field and all 63 files,
including the four regressions, worst terminal result, capture-244 primary and
capture-246 primary. Checks confirm 1,353 exact half-blend calls and 147 exact
ordinary fallback calls. Full request/fill traces and reconciliations are kept.

The frozen experiment passes 698 tests. Optional launcher integration passes
706 tests; independent review adds 80 synthetic tests and verifies strict
pre-I/O validation, exact model bytes, diagnostics, default compatibility and
selection persistence through account and news-led rollover. History and
ownership gates remain enforced after rollover.

The first candidate command supplied a results file where the driver expected
a baseline directory. It failed before producing candidate output. Both error
logs are retained; the corrected invocation uses the same frozen source.

## Supplemental capture 247: integration rejected

The unchanged model was frozen before capture 247 closed, but this separate
check was declared after its original strategy results were known. It is
supplemental evidence, not an untouched prospective whole-season test. The
[declared plan](repeat-blend-247-plan.md) additionally required all sixteen
settings to be positive, completed and settled. No coefficient or strategy
parameter was retuned.

| Metric | Original supervised baseline | Same half-weight blend |
| --- | ---: | ---: |
| Mean terminal P&L | −$332.11 | −$214.07 |
| Worst terminal P&L | −$573.91 | −$443.52 |
| Positive / negative settings | 1 / 15 | 4 / 12 |
| Completed / incomplete trials | 4 / 12 | 6 / 10 |
| Settled / flat / attention receipts | 4 / 9 / 3 | 6 / 8 / 2 |
| Fixed primary terminal P&L | −$239.99 | −$319.63 |

Thirteen settings improve and three regress: 0.25-second/half-depth/baskets-on
by −$47.63; 0.25-second/full-depth/baskets-on by −$79.64; one-second/half-depth/
baskets-off by −$24.78. Every loss is retained. Candidate minimum server marked
P&L is −$517.15 and maximum marked drawdown is $827.305.

Independent fill accounting reconciles all three regressions. HAVEN contributes
−$244.67 and −$248.15 to the first two differences after reversal to short
exposure and cleanup buybacks. In the third, earlier HAVEN sales contribute
−$123.00 and added RECON exposure −$110.20; gains in other symbols partly offset
those losses. These are contributions to paired differences, not standalone
portfolio returns.

The two zero-RTT/half-depth attention outcomes increase residual exposure over
baseline's REIN −6. With baskets off, the blend retains FERRY −19, GEN +53,
HAVEN −25, REIN −6 and ARCH −5. With baskets on, it retains GEN +1, HAVEN −25,
REIN −6 and ARCH −5. Neither has open orders or any later recorded fills.
Receipt marks −$413.50/−$381.765 become terminal marks −$443.52/−$435.10 through
valuation changes. These outcomes are neither flat nor settled receipts.

This fails both the original increased-residual-exposure rule and the additional
all-positive/completed/settled requirements. Better average and worst terminal
P&L do not override those failures. The reviewed launcher integration stays
unmerged, and production remains unchanged.

Independent review verifies all 32 rows, 288 journal/profile files, 112 original
baseline journals, 175 source/input artifacts and 58 Git blobs. Three reruns
reproduce every result field and all 27 files, including the primary and both
residual-exposure cases. There is no forbidden access, source change or extra
performance run. The retained 146-file review archive has SHA-256
`e374e08743cbcb957c710a24bde7ac15f4edb54102ec65357d8c28887524c15f`.
The supplemental source is frozen at
`95f0f90a48944cd3097420a02d8d2535e991b546` and passes 698 tests.

## Limits

These six captured price paths repeat 18 fitted-library weather tracks. The 96
settings are correlated and have recorded receive-time gaps and truncated
tails. Replays do not establish queue priority, unfamiliar-weather skill,
consistent account profits or winning odds. The only completed clean owned
practice trial remains +$141.16 on one training-weather season.

Capture 247 also exactly repeats three fitted-library tracks, bringing the
observed overlap across these seven captures to 21 complete tracks. Its losses
show why the first six captures alone were insufficient evidence for integration.
The initial 96 positive results must not be presented as the latest complete
comparison or as 96 independent winning seasons.

All initial comparison artifacts are retained in
`docs/evidence/repeat-blend/`, with a 38-artifact SHA-256 manifest, both complete
journal archives, preflight findings, development/capture reviews, integration
review, failing and passing test logs, and the separate loss attribution.
The supplemental comparison is retained separately in
`docs/evidence/repeat-blend-247/`, with its own 20-artifact manifest and both
144-file journal/profile archives. Its failure does not overwrite the original
96-setting results or initial analysis. The underlying frozen production
evaluation is documented in [observed-season-247.md](observed-season-247.md).
