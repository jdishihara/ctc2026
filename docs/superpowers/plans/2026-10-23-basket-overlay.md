# Bounded Basket Overlay Plan

**Goal:** Add an independent source of PnL to the accepted fundamental strategy
by closing ETF/basket discrepancies through creation/redemption.

**Authority:** Continuation of the user's repeated instruction to keep improving
the competition algorithm. Native implementation in the existing isolated
branch; no deployment or remote orders. One final independent review covers
this plan and the preceding price/forecast experiments together.

## Evidence and fixed design

The price and cone alternatives failed their PnL gates and remain disabled.
An offline basket-only screen on seasons 301–450 gave mean PnL 1144.89 in deep
liquidity (0 losing seasons), but 127.73 under quarter depth, 60s refill and 3s
latency (22 losing seasons, 3689 timeouts across 150 seasons). There is an
execution-sensitive opportunity; these standalone results are not additive to
the fundamental strategy and do not establish a live profit.

Use an optional `basket_edge` (default 0) with a maximum 10 ETF units, 15s
attempt spacing, 10s partial-fill timeout, and initial limit room 0.1% per leg.
Test exactly entry thresholds 0.5% and 1.0% of basket NAV, net of quoted spreads.
On timeout, cancel all remaining legs and restore the captured starting
positions with limits at most 2% through current touch; retry after another
10s only if necessary. This uses the accepted crossing cap rather than the
unbounded market orders of the research prototype.

Before a cycle, cancel participating symbols' outstanding orders, reconcile,
then capture their positions. Creation/redemption opens a hedge. Place only
the closing legs needed to return to the captured positions. During the cycle,
continue news/model updates but suspend new fundamental orders. Other symbols'
resting orders are not part of the cycle. After completion, resume normal
rebalancing. Missing/unknown account state stalls all cycle actions.

Require fresh quotes for every leg (within 5s live), market open, no participating
paused symbol, a known storm-anchored round clock, elapsed 20–740s, and enough
action headroom for initial cancel/convert/place plus one cancel/restore pass.
Size against temporary conversion inventory and same-side resting reservations.
Never assume a rejected/uncertain conversion changed no inventory: retain the
captured targets until a refreshed account proves the cycle is complete.

## Global constraints

- Existing accepted parameters and launch defaults stay fixed until promotion.
- Tune only 451–525; select by the established score, requiring both means to
  rise and thin p10 deterioration <10%. Freeze one candidate before 526–600.
- Previously inspected confirmation data is reused, not a fresh holdout.
- A promoted candidate must also preserve the improvement at 3s latency on
  tune and improve mean PnL under severe liquidity; report every tail metric.
- No access to future prices or simulator-specific depth in the live overlay.
- Respect 120 actions/minute, position limits and uncertain execution state.
- Tests must demonstrate partial fills, failed cancellations, conversion
  uncertainty, action budget, stale quotes, and resumption after restoration.

### Task 1: Basket state machine and strategy integration

**Files:** `ctc/basket.py`, `tests/test_basket.py`, `ctc/strategies.py`.

- [x] Write failing behavioral tests for profitable and unprofitable baskets,
  temporary inventory limits, stale quotes, partial fills, cancellation races,
  unknown conversion outcome, bounded unwind and normal-strategy suspension.
- [x] Implement disabled overlay; run tests and full suite.
- [x] Compare two fixed thresholds with baseline on all tune seasons/regimes.
- [x] Freeze basket10, confirm/stress, and reject after its failed severe gate.
- [x] Keep fixed-lot defaults disabled; depth-capped promotion is handled in Task 2.
- [x] One independent review over both plans; fix all five Important findings RED→GREEN.
- [x] Publish final evidence and update the existing draft PR.

## Review focus

Partial orders must never be treated as fully filled. Cancel acknowledgements
can contain racing fills. A timeout after conversion may have changed positions.
The overlay must restore actual reconciled starting positions, not nominal lot
sizes. Existing same-side orders and temporary converted inventory consume
limits. A stale symbol cannot borrow freshness from another symbol. Completion
requires no outstanding participating orders as well as restored inventory.

## Rulings

Ruling: test a small coordinated overlay because standalone basket PnL is
positive in both internal regimes. The stress collapse argues for fixed small
lots and explicit cancellation/restore handling. Cost if wrong is a rejected
offline experiment; no live setting changes without the recorded gates.

## Tune selection frozen before confirmation

2026-10-23, Codex: source `369c2a9`, clean invocation, all 75 tune seasons.

| Candidate | Deep mean | Thin mean | Thin p10 | Score | Decision |
|---|---:|---:|---:|---:|---|
| baseline | 8643.98 | 5176.69 | -3729.45 | 5045.61 | Reference |
| basket05 | 9270.13 | 5709.93 | -4291.16 | 5344.45 | Reject: thin p10 down 15.1% |
| basket10 | 9215.25 | 5736.06 | -3054.46 | 5948.43 | Freeze |

All have zero rejected orders/rate blocks. `basket10` peaks at 62/69 actions per
minute, versus the 120 cap; 8.17/8.47 cycles per season, 17/192 timeout restores
over 75 seasons. Freeze `basket_edge=0.01`, lot 10 and all other fixed settings.
Confirm only baseline/basket10 on 526–600. Stress the same pair on tune at 3s
latency in deep/thin, and separately severe liquidity also at 3s latency.

Ruling: freeze the only eligible candidate before inspecting confirmation;
the 0.5% threshold's higher deep mean does not override its failed tail gate.
Cost if wrong is rejecting some profitable opportunities; protects the stated
selection rule from hindsight.

A local HTTP test exposed the mock's conversion route as a no-op. Implemented
atomic inventory changes and limit checks. The live adapter now completes a
real localhost conversion/refresh/three-order cycle and restores its starting
positions with each fill logged once. This is an API integration test, not
evidence about the competition server's actual schema or timing. Full suite:
148 passed. This mock-only fix does not change replay strategy results.

2026-10-23, Codex: frozen fixed-lot basket10 passes ordinary confirmation:
means 10007.57/6507.57 vs 9452.36/5993.53; p10 540.38/-2220.72 vs
-254.55/-2712.92. At 3s tune latency it also improves means, 6890.18/4255.48
vs 6836.01/4034.64. However severe+3s mean falls 987.59 -> 914.35, so
promotion is BLOCKED by the stress gate. No default change is justified yet.

### Task 2: Bound basket size by observed executable depth

**Cause under test:** A fixed 10-unit basket can exceed displayed liquidity in
its doubled component legs, leading to delayed restorations. The prototype
limited size to touch depth, while the coordinated implementation deliberately
had no public depth interface. Add that interface before trusting the overlay.

**Fixed candidate:** keep the frozen 1% threshold and maximum 10 units; cap each
closing leg at half the displayed external quantity executable within its
initial 0.1% limit. Size is the smallest leg capacity after dividing by basket
units. Unknown/failed book reads skip the cycle. No midpoint-only depth estimate
and no simulator-regime flag are allowed in the strategy.

`Sim.liquidity(symbol, side, limit)` exposes remaining current book depth
without consuming it. `LiveExchange.liquidity` reads the existing
`GET /orderbook/{symbol}` route (already used by this repository's testnet
recorder), validates levels, subtracts our same-price resting quantity, and
returns None on unavailable/invalid data. Recheck quote freshness after all
book reads. Calls use the same current limit prices used for closing orders.

- [x] RED→GREEN tests for non-consuming simulator depth, own-order subtraction,
  unknown depth, per-component ratio sizing and freshness after blocking reads.
- [x] Test this one candidate on all tune seasons, normal deep/thin, 3s
  deep/thin, and severe+3s. Require both normal means and thin p10 gate, both
  delayed means, and severe mean improvement before freezing for confirmation.
- [x] Freeze parameters and confirm once; promote consistently only if the
  confirmation gates pass. Include in the one final independent review.

Ruling: fix the observed execution-capacity mismatch using only tuning stress
evidence, not the candidate's already-inspected confirmation outcomes. One
fixed 50% participation cap is a conservative design choice, not a parameter
search. Cost if wrong is smaller captured profits or another rejected offline
candidate; the fixed-lot overlay remains unpromoted.

2026-10-23, Codex: depth candidate passes every tuning/stress gate. Source
`aa54469`, clean invocation; 75 seasons per comparison. No rejection/rate block
in any regime. The fixed half-depth cap is frozen before its first confirmation.

| Regime | Baseline mean | Candidate mean | Baseline p10 | Candidate p10 | Peak actions |
|---|---:|---:|---:|---:|---:|
| Deep, .25s | 8643.98 | 9144.20 | -1577.25 | -1127.16 | 52 |
| Thin, .25s | 5176.69 | 5603.77 | -3729.45 | -3443.49 | 54 |
| Deep, 3s | 6836.01 | 6883.22 | -3914.40 | -4087.52 | 58 |
| Thin, 3s | 4034.64 | 4065.70 | -5280.18 | -5078.85 | 59 |
| Severe, 3s | 987.59 | 1285.44 | -8287.64 | -7953.12 | 58 |

Normal tune has no timeout restorations; delayed deep/thin/severe have
408/374/333 across 75 seasons. The normal tune score is 5652.24 versus
5045.61. Freeze `basket_edge=.01`, `basket_participation=.5`, max lot 10.
Only baseline/basket_depth will be inspected on confirmation. A truncated
HTTP book response was also reproduced with a failing test and now returns
unknown depth, skipping a cycle; this live error-path fix does not alter replay.

2026-10-23, Codex: frozen depth candidate passes confirmation. Deep/thin means
9925.95/6412.88 versus 9452.36/5993.53; p10 512.72/-2459.40 versus
-254.55/-2712.92. Worst seasons improve in both regimes, losing counts 7/75
and 13/75, zero normal timeout restorations, rate blocks and rejections.
Launch defaults promoted consistently to basket edge .01 / participation .5,
with edge 0 as the disable switch. Generic constructor remains disabled.

Full suite 157 passed; actual default CLI and diagnostic reproduce season 451
PnL 12007.83 and 381 fills. Local HTTP tests cover depth/convert/refresh/close.
Full local mock replay completes three rounds, 34 fills logged once each, no
HTTP/reconciliation errors. No remote orders. Independent final review remains.

2026-10-23, Codex: final review completed over aa51985..ecd40a5. The reviewer
independently verified 157 tests and all 54 archived result summaries/hashes.
All five Important findings were reproduced and fixed in one pass at 73aed77:
stale-timeout cancellation, freshness/competition checks after blocking calls,
independent quote reception, paused completion and optional passive flip size.
The suite now has 180 tests. No Critical or deferred Minor findings.

Nine clean post-fix comparisons replayed 675 seasons, exactly matching every
frozen row and summary in confirmation, normal tune and 3s deep/thin/severe
stress. All selected parameters remain fixed. Review decisions and all
declined-to-judge rulings are preserved in docs/research-continuation.md and
docs/review-verification.json. No second reviewer was requested. Post-fix live
CLI rehearsal completed all three localhost rounds with 31 fills logged once,
no HTTP/reconciliation errors and clean server exit. Mock PnL is not a benchmark.

2026-10-23, Codex: code and evidence pushed to `arjun/ctc-efficiency`, existing
draft PR #1 updated and confirmed open/mergeable. No hosted checks are configured;
local verification is the 180-test suite, exact replay parity and localhost
rehearsal above. No merge or remote trading. The checkout, data and outputs are
retained; only the two owned temporary execution workspaces are removed after
their decisions and evidence are preserved in the durable reports/plans.
