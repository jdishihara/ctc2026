# Repeated-weather recognition: one-hot candidate rejected

The optional one-hot recognizer is **rejected under its predeclared risk rules**.
It improves mean offline P&L but worsens the worst loss, increases negative
settings and creates additional cleanup attention outcomes. Production and
all frozen forward evaluators remain unchanged. No account orders were placed.

This experiment is retained at `357d9986babf2b21bd3bbdcc2e69550059f16154`
on `arjun/repeat-prefix`; its code is not part of production. The protocol was
declared before implementation and performance evaluation in
[repeat-prefix-plan.md](repeat-prefix-plan.md).

## What changed

The default-disabled recognizer requires at least 21 complete observations,
ages 0 through 40 and then every two seconds to the current age. All observed
x/y/radius/intensity values must exactly match one unique fitted-library row.
Only then does it replace the ordinary distribution with a one-hot forecast.
Corrections invalidate and recompute the match; missing, ambiguous or divergent
prefixes retain the ordinary model, whose cache continues updating throughout.
Matching never reads a library column after the most recent observed age.

The historical continuation is still a forecast. These six closed captures
have exact training-weather overlap; the experiment measures behavior on
repeated training weather, not generalization. No active capture 247+ outcome
or downloaded current/future-season history was accessed.

## Complete capture comparison

All six closed captures 241–246 are evaluated under the same sixteen settings:
RTT 0/0.05/0.25/1 second, full/half displayed depth and basket off/on. Limits
remain 10%, with 90 actions/minute and the unchanged $250 observed-loss trigger.
That trigger is not a hard bound on realized or terminal loss.

Both phases contain all **96 settings**, with zero diagnostic errors, forbidden
accesses or source changes. Before the candidate ran, baseline reproduced every
archived result field and all **672 original journal files** exactly. Baseline
finished at 09:23:56 UTC; candidate finished at 09:26:00 UTC.

| Metric | Original baseline | One-hot candidate |
| --- | ---: | ---: |
| Mean terminal P&L | $678.13 | $1,093.27 |
| Worst terminal P&L | −$420.64 | −$514.88 |
| Best terminal P&L | $2,236.76 | $2,687.51 |
| Positive / negative settings | 84 / 12 | 82 / 14 |
| Completed / incomplete trials | 84 / 12 | 80 / 16 |
| Settled / flat / attention cleanup receipts | 84 / 10 / 2 | 80 / 10 / 6 |

There are **80 improvements and 16 regressions**. Capture 244 improves in two
zero-RTT/half-depth settings but regresses in its other fourteen settings.
Capture 242 also regresses in the two one-second/basket-off settings: −$185.01
at half depth and −$74.17 at full depth, relative to baseline. Each of the other
four captures improves in all sixteen settings. No regression is excluded.

### Fixed primary setting

Primary remains 0.25 second RTT/full displayed depth/basket on.

| Capture | Baseline terminal P&L | Candidate terminal P&L | Candidate outcome |
| --- | ---: | ---: | --- |
| 241 | $52.93 | $706.62 | Completed, settled |
| 242 | $1,497.40 | $1,632.85 | Completed, settled |
| 243 | $286.36 | $823.00 | Completed, settled |
| 244 | −$261.00 | −$475.83 | Loss stop, flat |
| 245 | $362.85 | $869.86 | Completed, settled |
| 246 | $1,539.17 | $2,183.20 | Completed, settled |

### Capture 244 and attention outcomes

Every candidate capture-244 setting stops early. Four settings newly report
attention: zero RTT/full depth and 0.05 second RTT/half depth, each with basket
off/on. The existing zero-RTT/half-depth attention cases retain more exposure.
Their positive terminal marks of +$92.67 are not completed or flat trials.

The zero-RTT/full-depth attention receipts retain REIN −1 and one remaining
buy unit on order 19. One fill occurs after each final receipt, leaving the
terminal account flat at −$484.81, versus the receipt mark of −$483.77. This
favorable resolution in the recorded tail does not erase the attention state
or justify claiming the receipt was flat.

The primary candidate stops in **round 1**, with latest observed storm age 76,
earlier than baseline's latest observed age 274. Cached fair/dispersion values
at those different times are not a same-time causal comparison. Further loss
attribution must distinguish model uncertainty, price movement and cleanup.

## Development fallback check

The separate development comparison reads only seasons 451–525: 75 seasons,
225 storms, 150 baseline/candidate runs. Its fixed setting is 10% limits,
0.25-second delay, half-size ladder and 30-second refill.

No storm activates the recognizer. All 75 pairs are **exactly identical** except
the enable flag, including fill/P&L trace hashes, cash, positions and round P&L.
Both modes average **$1,476.43**, with worst **−$723.10**, best **$4,132.79** and
six negative seasons. This verifies unchanged fallback on unmatched development
storms; zero activations provides no evidence of recognition benefit.

Independent review verifies all 150 rows, 225 scans, 21 source hashes and 225
input hashes. Its separate streaming matcher checks all 54,225 observed prefixes
without calling the candidate helper, finding zero matches/divergences. Six
guarded reruns—seasons 451, 488 and 525 in both modes—reproduce every result
field and independently reconcile fills/conversions to cash and settlement.
No forbidden access, guard violation or source/input change occurred.

## Verification and retained evidence

All **686 tests** passed before freezing the source. Independent preflight
checked matching bounds, cache behavior and all capture gates. Development
preflight caught and corrected price-copy, history-path and unmatched-result
failure handling before any real development evaluation. Both the failing
synthetic evidence and corrected review are retained.

Independent capture review verifies all 96 pairs, all 1,728 journal/profile
hashes, all 672 original baseline journals and every source/input hash. It
reproduces the complete analysis exactly. Ten requested reruns reproduce every
result field and all 90 files, with zero forbidden accesses. The retained
136-file archive includes full request/fill traces and cached quote observations;
its SHA-256 is
`210bf673a2a3716188648c9d1f264f30210f9c797fb3a21981f2c04277f69067`.

`docs/evidence/repeat-prefix/` retains complete results, metadata, source/input
hashes, logs, all 1,728 journals/profiles, preflight evidence and independent
reviews. The analysis contains all 96 pairs, including every loss and attention
case. The six captured price paths have receive-time gaps and truncated tails;
the simulator does not establish queue priority or actual-account profitability.
Settings on a shared path are correlated, and development data have been reused.

The actual owned completed practice record remains **+$141.16** from one
training-weather season. Live account ownership is still unresolved.
