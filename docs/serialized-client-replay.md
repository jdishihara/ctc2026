# Sequential REST execution on three captured markets

## What this evaluates

This diagnostic runs the current strategy through the production account and
session code against a virtual exchange driven by completed recorded quotes and
news. REST calls consume virtual time in sequence. Arrivals during a request
update server books and queue client events; they cannot update the strategy's
view until its next inbox drain. Status-only filled/partial acknowledgements
trigger the production account reconciliation path.

The fixed grid has 16 scenarios per capture: request round trips of 0, 0.05,
0.25, and 1 second, full/half displayed depth, and basket off/on. Position limits
are 10% and the action cap is 90/minute. All other strategy parameters are fixed.
The zero-RTT client is the paired reference. These are reused captures, not
untouched validation or actual live results.

Design and scheduling details: [serialized-replay-plan.md](serialized-replay-plan.md).

## Original failures and correction

Version 1 source `b065a8111187a48c183162df97046db88907d397` followed the old direct
launcher's startup order and rejected **all 48 scenarios** for incomplete model
history. It calculated no valid settlement P&L. Initializing the strategy before
confirming the account ID caused the first quote callback to erase loaded
history while session sequence tracking retained consumed messages.

Production PR #15 fixes that startup ordering and refuses an unavailable or
invalid initial identity. Supervised practice already initialized correctly, so
this finding does not explain its earlier loss. Version 2 adopts the reviewed
production order and adds two full-history-plus-quotes regressions that failed
before the correction. Its source was frozen at
`2369087be5da34ff2b3d26e9cc37feedb74adfc2` before rerunning the same grid.

All version 2 scenarios completed with three reports and complete history.
Selected-frame and receipt hashes are identical to version 1. Both versions'
metadata, results, and summaries are archived in
[evidence/serialized-client](evidence/serialized-client).

## Independently checked results

Each row summarizes four scenarios (depth × basket). Values are simulated
settlement P&L in dollars. The paired change holds depth and basket choice fixed.

| Capture | REST RTT (s) | Mean | Worst | Best | Losses | Mean change vs zero RTT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 241 | 0 | 96.24 | 70.13 | 131.61 | 0/4 | 0.00 |
| 241 | 0.05 | 55.92 | 33.93 | 80.41 | 0/4 | −40.32 |
| 241 | 0.25 | 112.11 | 106.14 | 118.09 | 0/4 | +15.88 |
| 241 | 1 | 171.51 | 91.26 | 247.87 | 0/4 | +75.28 |
| 242 | 0 | 2,191.01 | 2,152.92 | 2,236.76 | 0/4 | 0.00 |
| 242 | 0.05 | 1,473.44 | 1,451.20 | 1,499.81 | 0/4 | −717.58 |
| 242 | 0.25 | 1,423.88 | 1,381.92 | 1,470.84 | 0/4 | −767.13 |
| 242 | 1 | 1,344.97 | 1,185.18 | 1,488.09 | 0/4 | −846.05 |
| 243 | 0 | 501.99 | 409.39 | 597.15 | 0/4 | 0.00 |
| 243 | 0.05 | 246.68 | 190.76 | 287.54 | 0/4 | −255.31 |
| 243 | 0.25 | 293.07 | 150.01 | 431.71 | 0/4 | −208.91 |
| 243 | 1 | 7.44 | −29.72 | 44.59 | 1/4 | −494.55 |

The negative case is capture 243 at one-second RTT, half displayed depth, and
baskets enabled: **−$29.72**, 63 orders, 90 fills, and zero completed conversions.
Its lowest marked P&L is −$65.72; maximum peak-to-trough marked drawdown is
$773.46. These are different risk measures. The raw row also records final
inventory, request counts, and blocked submissions.

Sequential request timing materially changes decisions in this model. It is
not monotonic: capture 241's mean improves at some nonzero RTTs, while means for
242 and 243 decline at every tested nonzero RTT. This does not justify choosing
a delay or other setting from the best reused replay. The earlier activation-
delay replay differs in account reconciliation too, so differences between the
two engines are not an isolated measurement of network latency.

## Execution and recording limits

- A fixed RTT and midpoint server execution are stress assumptions. Recorded
  order acknowledgement durations do not identify every GET's latency or actual
  fill time. The grid is not a fitted latency distribution.
- All 48 scenarios share just three already examined market paths. A count of
  profitable scenarios is not an independent-trial win rate.
- Recorded quote paths contain gaps, and disconnect completeness is unknown.
  The model processes only captured frames. Their hashes identify exactly which
  inputs ran; they do not prove complete coverage of the actual market path.
- Virtual fills omit queue priority, own market impact, extra fees, and variable
  conversion execution. Strategy computation is instantaneous. No additional
  implicit refresh is added to the production conversion path.
- The core direct client is modeled; practice-supervisor ownership/history
  requests, cumulative loss stops, and supervisor cleanup are excluded. HTTP
  connection reuse does not change the fixed RTT. Positive terminal P&L is not
  a prediction for a supervised run that might stop earlier.
- Matching stops at the last selected frame. The gaps to official closing
  receipts are **1.938 s (241), 8.273 s (242), and 2.652 s (243)**. This truncation
  can help or hurt results and is not a profit lower bound. Remaining holdings
  are valued at official settlement only after the server is irreversibly shut.
- No live trader is started, strategy parameter promoted, or live size increased
  by this diagnostic. The separate fixed closed-season worker is unchanged.

## Verification

The corrected source passes **536 Python tests**. New regressions verify that
complete reports and matching account/strategy IDs survive real quote callbacks
at zero and 0.25-second RTT. Independent design/code review approved the startup
correction and passed 38 focused tests before the frozen rerun.

The earlier implementation review passed 27 focused tests and six additional
midpoint/close/cancellation/account-race checks, and verified every archived
version 1 failure, input hash, source hash, and tail gap. Independent version 2
review verified all 48 grid rows and aggregates, zero-RTT pairings, final
inventory caps, selected-frame and receipt hashes, all 26 listed source/model
hashes, and all 18 byte-identical archives. Eight representative reruns matched
every output field, including the negative scenario. Their access audit found
no network, credential, or downloaded-history reads. The eight startup
identities and 92,894 quote callbacks retained matching account/strategy IDs.

The original manifest omitted `bot/control.py`, which is imported by the live
module. A dependency trace found only its module and class definitions ran;
no control constructor, poll, parser, or apply callback executed. Its bytes
match the frozen source commit. Supplemental SHA-256 recorded during review:
`b33ba64f8110eb59ce4a16e8cd987be8365bf0c3db98810f06c58333d4104401`.
This hash was not recorded in the original run manifest. There is no numerical
blocker from this unused-control dependency, but the manifest should include it
in future runs. No profitability-readiness claim follows from these engineering
test counts.
