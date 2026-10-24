# Overnight evaluation window — 2026-10-24

Status: **final; observation boundary sealed 2026-10-24 12:00:00.008254 UTC**.
The first post-cutoff scan sealed 1,596 complete lines (328,628 bytes),
SHA-256 `2a27ffc79c4af550427d06234f8256c38464aa2fed0eaa352dc6baebf0d75837`.
It matched the original append-only source prefix; no partial line or malformed
receipt was present. The 8 official settlement receipts in the prefix produced
6 serialized-client, 5 full-controller and 7 original-worker eligible seasons.
No duplicate receipt, failed run or unfinished attempt remained at the boundary.

## Full practice controller

The frozen forward controller uses 10% limits, a $250 observed loss trigger,
and the same 16 declared execution settings for each season. The primary
setting is 0.25-second REST round-trip time, full displayed depth and baskets
enabled. These are offline outcomes. Each row below is one recorded season;
the 16 settings within it are repeated evaluations of that same path.

| Capture | Primary P&L | Primary trial | Positive / negative settings | Worst setting |
| --- | ---: | --- | ---: | ---: |
| 245 | +$362.85 | completed | 16 / 0 | +$5.42 |
| 246 | +$1,539.17 | completed | 16 / 0 | +$1,439.61 |
| 247 | −$239.99 | incomplete trial | 1 / 15 | −$573.91 |
| 248 | +$985.54 | completed | 16 / 0 | +$295.45 |
| 249 | +$1,760.14 | completed | 16 / 0 | +$1,014.34 |

Four of five primary outcomes are positive, averaging **+$881.54 per season**.
Across 80 repeated settings, 65 outcomes are positive and 15 negative; their
mean is +$811.62. There are 67 completed trials and 13 incomplete trials.
The frozen controller's cleanup states are 67 settled, 10 flat and 3 attention.
Across the five supervised captures, the highest single setting earned
**+$1,937.04** (capture 246); the latest primary result was **+$1,760.14**.
The final independent review checked all 33 result, metadata and summary
bindings, all receipt identities, and 92 unique frozen source files.

These results retain runtime `cd3eb239` and driver `c5c35a30`. The later
[bounded cleanup retry](cleanup-retry-window.md) closes the previously stranded
portfolios in its separate 112-setting comparison. Its [fixed follow-up
comparison](cleanup-retry-forward.md) leaves all outcomes for 248 and 249
unchanged; neither season requires an extra cleanup pass.

## Core client comparison

The separate serialized client window includes the declared capture-244
carryover and captures 245–249: six seasons and 96 repeated settings.
Five primary outcomes are positive, averaging +$684.36; across all settings,
82 outcomes are positive and 14 negative, with a −$738.46 worst setting.
This client comparison does not include the complete practice supervisor.

## Earlier market replay worker

The original frozen market replay covers captures 243–249: seven seasons and
168 repeated settings, including its declared warmup-reset diagnostic. There
are 140 positive settings and 28 negative settings; the worst is −$799.84.
Its source remains `49a690ef`. This is a different execution model from the
serialized client and practice controller, so its results are reported
separately. Its final worker ledger records a clean stop at 12:00:00.020745 UTC.

## What the results establish

All 27 weather tracks in captures 241–249 exactly match fitted training rows.
The available history archive contains 600 complete seasons. The analog
library was fitted on the first 450 (1,350 tracks); the next 75 seasons were
development data, and the final 75 confirmation seasons have already been
examined. None are an untouched holdout for this report. See the
[training overlap audit](training-overlap-audit.md). Training volume alone
does not turn these replays into unfamiliar-weather validation.
The selected intervals and frozen source dates are recorded in the individual
reports. Later collection dates do not establish unfamiliar-weather validation.
Recorded quote gaps and simulated fills also limit transfer to actual execution.

The only completed, clean, owned small-size live trial remains **+$141.16**.
The initial full-size loss remains **−$2,589.80**, including cleanup and the smoke
check. Shared-account activity after our runner stopped is not attributable to
this bot. Live trading has not resumed while account exclusivity is unresolved.

The reviewed competition checkout is `/Users/arjunhans/Documents/ctc2026-competition`.
The systematic runtime and model remain unchanged by this report. See the
[readiness report](competition-readiness.md) and [latest season audit](observed-season-249.md)
for software checks, execution limitations and the other case tools.
