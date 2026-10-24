# Bounded retries after incomplete cleanup

## Result and scope

The fixed candidate closes all five portfolios that previously retained
positions after cleanup on closed captures 241–247. Across the 112 prescribed
execution settings, positive outcomes remain 85, negative outcomes remain 27,
and the worst terminal P&L remains −$573.91. This is an execution correction;
it does not establish consistent profitability or live cleanup reliability.
Independent final result verification passes the declared integration gates.

All 21 weather tracks in these captures match the fitted analog library. The
seven paths were already inspected before this experiment was declared, and
sixteen settings per path are correlated execution scenarios. They are not
112 independent seasons or an untouched holdout. No owned live orders were
sent during this experiment. Shared-account ownership remains unresolved.

## Diagnosis and fixed change

The three original capture-247 attention outcomes finish their five cleanup
passes at simulated time 2172.5 with REIN −6. Their last REIN quote is already
too old for the replay's five-second freshness rule. The next recorded quote
arrives at 2173.325811: 0.825811 seconds after cleanup ends. Its ask has enough
size for six shares even at half depth. There was no attempted REIN cleanup
order, and observed order-action counts were below the cap. This diagnosis is
conditional on the recorded quote and fill assumptions; it does not prove
that the same liquidity would have been available live.

The candidate preserves every action in the first five passes. It admits
additional passes while elapsed monotonic time since cleanup entry is at most
61 seconds, capped at 62 total passes with the existing one-second sleeps.
Every existing ownership, identity, reconciliation, history, freshness and
position-reduction guard remains in effect. The extra passes can stop earlier
when safely flat or settled.

Extra-pass POST/DELETE operations also require fewer than 90 conservatively
counted mutations in the inclusive preceding 60 seconds. A private shadow
ledger counts existing completed request, cleanup-order and cleanup-cancel
events once; rejected or locally denied operations are conservatively charged.
Request-attempt events are not double-counted. Missing, invalid or backward
monotonic accounting fails closed. A deferral happens before sending an order
or cancellation and does not fabricate a missing acknowledgement. Serialized
journal bytes remain unchanged.

The horizon bounds admission of additional passes. The original five passes
can take longer than 61 seconds, and requests in an admitted extra pass can
overrun the horizon. The new mutation guard applies to extra passes only;
it does not establish a new shared-budget guarantee for the first five.
Forecasting, sizing, the $250 sampled loss trigger and all strategy parameters
are unchanged. Repeated-weather recognition remains disabled.

## Declaration, source freeze and verification

The [plan](cleanup-retry-window-plan.md) was committed as `fb0b6b0` at
10:06:35 UTC, before implementation and candidate performance evaluation.
The source was frozen at `27ab7c4` at 10:09:20 UTC. Only `bot/practice.py`
differs from baseline `cd3eb23` among runtime files. The replay driver adds
trace checks and cleanup/mutation profiles; it does not alter the market model.

The initial regression run had 14 failures and two passes. The first focused
green attempt retained one failure from a test's `Fill.quantity` typo; changing
that test to `Fill.qty` produced 97 passing focused tests. The frozen full suite
passes 652 tests. Raw failing and passing logs are retained. Integration on
main `c0a62b1` also passes 652 tests, with all five frozen plan/source/test files
byte-identical to the experimental source.

Independent source preflight includes the focused tests, 40 additional race
cases, ten exact first-five-pass synthetic comparisons, six clock checks,
25 synthetic driver phases, 20 swallowed-guard attacks and 22 corrupted
prerequisites. It performs no captured-market performance evaluation. The
driver denies network, credentials and historical outcome reads, latches
violations, hashes inputs and source before/after, and rejects changed inputs.

The complete grid is seven captures × RTT 0/0.05/0.25/1 seconds × full/half
displayed depth × baskets off/on. Position limits remain 10%, strategy actions
90 per minute, prior P&L zero and the sampled observed-loss trigger $250.
Baseline finished at 10:19:41 UTC: all 112 original result rows and all 784
original journal files match. Candidate finished at 10:22:47 UTC with zero
diagnostic errors. Each phase preserves 1,008 journal/profile files.

All 112 candidate pre-cleanup request/fill hashes and first-five-pass request
hashes match baseline exactly, including unchanged stopping decisions. The
analyzer and thresholds were fixed before performance evaluation. All declared
promotion rules pass: worst loss and negative counts do not increase, no
nonnegative setting turns negative, no new attention outcome appears, no
symbol's absolute residual exposure increases, and existing residuals decrease.

## Complete comparison

| Metric | Baseline | Candidate |
| --- | ---: | ---: |
| Positive / negative settings | 85 / 27 | 85 / 27 |
| Mean terminal P&L | $533.81 | $534.10 |
| Worst terminal P&L | −$573.91 | −$573.91 |
| Best terminal P&L | $2,236.76 | $2,236.76 |
| Completed / incomplete trials | 88 / 24 | 88 / 24 |
| Settled / flat / attention receipts | 88 / 19 / 5 | 88 / 24 / 0 |
| Loss-trigger stops | 24 | 24 |
| Mean cleanup duration across loss stops | 59.18 s | 59.76 s |
| Lowest observed marked P&L | −$573.91 | −$573.91 |
| Largest observed marked drawdown | $1,086.61 | $1,086.61 |
| Maximum actual POST/DELETE starts in an inclusive 60 s window | 33 | 33 |

The candidate has 13 actual extra-pass mutations. These traces stay below the
exchange's 180-action ceiling and the extra-pass 90-event guard. This does not
benchmark live GET throughput or prove server latency. Two settings improve,
three worsen, and 107 have identical terminal P&L. Every changed setting is
listed below; no favorable row was selected out of the grid.

| Capture | RTT / depth / baskets | Baseline P&L | Candidate P&L | Change | Cleanup time |
| --- | --- | ---: | ---: | ---: | --- |
| 244 | 0 s / half / off | −$277.86 | −$260.34 | +$17.52 | 5 → 9 s |
| 244 | 0 s / half / on | −$277.86 | −$260.34 | +$17.52 | 5 → 9 s |
| 247 | 0 s / full / off | −$403.97 | −$404.93 | −$0.96 | 5 → 7 s |
| 247 | 0 s / half / off | −$522.38 | −$523.34 | −$0.96 | 5 → 7 s |
| 247 | 0 s / half / on | −$490.71 | −$491.67 | −$0.96 | 5 → 7 s |

Both affected capture-244 outcomes previously retained REIN −20, AQUA −8 and
GRID −5; all are now zero. Each affected capture-247 outcome previously
retained REIN −6; each is now zero. These five results improve the exit state,
but three pay an additional $0.96 to close. The 24 stopped trials still count
as incomplete rather than successful completed seasons.

All seven predeclared primary settings (0.25-second RTT, full depth, baskets
on) have unchanged P&L: captures 241–247 return $52.93, $1,497.40, $286.36,
−$261.00, $362.85, $1,539.17 and −$239.99 respectively.

## Independent final audit

The final audit checks all 112 pairs, 784 original journals, all 2,016 produced
files/profiles, 862 source/input artifacts and every recorded mutation window.
All five changed outcomes reconcile from complete fill cash and terminal
holdings, including unchanged cash-neutral basket conversions. The 107
unchanged outcomes preserve all 749 original journal files byte for byte.
Eighteen synthetic analyzer checks also pass.

Eight authorized unique settings reproduce every result field, all 72 files
and full request/fill traces. These include all five affected attention cases,
the capture-247 primary, capture 244 / 1 s / half / off, and capture 243 /
1 s / half / off. The requested capture-244 slow case was initially mislabeled
as a loss stop; it actually completes at +$559.01 with 21-second settled
cleanup. The additional capture-243 case explicitly checks an unchanged
−$391.47 loss-stop result with 260-second cleanup and no extra mutations.

The review retains its unsuccessful invocations: system Python lacked a
dependency before replay; an initial trace check incorrectly included GET
response bodies; and an initial economic check omitted existing cash-neutral
ARCH inventory conversions. The latter two cases were repeated after fixing
only the audit harness. Both duplicate executions, all failed logs and the
complete successful reruns remain in the 159-file independent review archive.
No strategy parameter or runtime was changed during the result audit.

## Evidence and limitations

The [artifact manifest](evidence/cleanup-retry/artifact-manifest.json) hashes
every packaged result, profile archive, test log, specification, analyzer,
diagnosis and independent review. [analysis.json](evidence/cleanup-retry/analysis.json)
retains every pair, cleanup timing, residual vector and comparison decision.
Its original `pending_independent_review` label is preserved as generated;
the later independent review supplies the final approval.
The two journal archives retain all 2,016 phase files. Paths inside provenance
metadata refer to the original frozen local worktrees and raw capture files;
the sealed raw feeds remain local because of their size.

The $250 trigger is sampled and is not a maximum-loss guarantee. Recorded
quotes, fixed latency, assumed partial fills, missing quote intervals and
unmodeled queue priority/own market impact limit replay conclusions. Higher
test counts establish tested behavior, not profitability. All frozen forward
evaluators retain their original source, so their later results must not be
presented as candidate results. Any new live batch still requires exclusive
account ownership and its own bounds and attributable journal.
