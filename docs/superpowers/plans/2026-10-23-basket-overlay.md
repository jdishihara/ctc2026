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
- [ ] Compare two fixed thresholds with baseline on all tune seasons/regimes.
- [ ] Freeze one eligible candidate, confirm and stress it; reject if gates fail.
- [ ] Promote live/backtest/preflight/diagnostic defaults consistently only if
  accepted; expose an explicit disable switch.
- [ ] One independent review over both plans; fix important findings RED→GREEN,
  publish all positive and negative evidence, push the existing draft PR.

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
