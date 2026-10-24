# Authenticated practice rehearsal — October 23, 2026

Follow-up: [practice loss review and fixes](practice-loss-review.md). The original receipts and loss figures below are retained.

## Environment and checks

Used the team's supplied bot key against `https://cornelltradingcompetition.org`.
The key is stored only in the ignored local `.botkey` file with mode `0600`;
it is absent from tracked files and was not passed in a process command line.
The API reported bot mode `full`, competition `90602797-3b9b-406c-8956-e755d14c09fc`,
and initially zero positions and open orders.

- Authenticated preflight: **20 passed, 0 warnings, 0 failures**, including WebSocket data.
- Bounded dry run: connected, consumed snapshots, and proposed orders without submitting them.
- Practice identity: observed news sequence 573 exactly matched published season 239,
  whose fictional year is 1788. The initial short capture contained only snapshots.
  The starter checker expects the rest of the season after the first received message;
  its unfinished-season missing-message result is **not** a complete recording pass.
- First remote smoke: a one-contract resting buy was visible and canceled; a subsequent
  one-contract buy and sell filled. The account returned to zero positions/open orders.
- After the acknowledgement correction below, the same three-order test passed end to end.
- Full Python suite after both corrections: **200 passed**. No strategy parameters changed.

## Bugs found with actual exchange responses

### Fill acknowledgements omit quantities

The exchange returns `order_id`, `status`, `created_at`, and a message, including for
`filled` and `partial` orders. It does not return the fill quantities expected by our
adapter. The first smoke therefore executed successfully at the exchange while the
adapter treated its filled acknowledgement as uncertain.

The adapter now preserves the accepted order ID and refreshes actual positions and
remaining orders for status-only fill acknowledgements. It does not guess the fill.
If reconciliation fails, it retains the ID and blocks further submissions until a
successful account refresh. Explicit contradictory or malformed quantities still fail.
Seven regression cases failed before the correction and pass afterward; they cover
buys, sells, partial fills, complete fills, and a failed reconciliation.

### Closed positions disappeared from reported P&L

The default positions endpoint omits zero-quantity rows, including their realized P&L.
The UI requests `include_zero=true`. Our adapter now requests the same data and handles
the null unrealized P&L returned for closed positions. A regression reproduced the
lost realized P&L before the correction. The first four actual smoke fills reconcile
exactly with the exchange's realized P&L of **-0.61 in simulated currency**.

## Bounded strategy run

Ran the accepted strategy with unchanged defaults and a separate control file. The
stop timer was set to 180 seconds; the final strategy log shows 200 seconds before
shutdown completed. Outstanding synchronous work can delay cancellation. HTTP account
receipts, WebSocket feed, order books, and execution logs were recorded locally.

| Check | Observed result |
| --- | --- |
| Strategy orders accepted | 9 |
| Strategy fill records before cleanup | 45 |
| Additional orders to close the test positions | 8 |
| Fill records including cleanup | 87 |
| P&L change before forced closure | -1,970.18 simulated currency |
| P&L change after closure | **-2,589.19 simulated currency** |
| All smoke tests plus strategy run, realized P&L | -2,589.80 simulated currency |
| API/reconciliation errors in the strategy execution log | 0 |
| Final open orders / nonzero positions | **0 / 0** |
| Fill replay versus exchange positions | Exact match |
| Fill replay versus exchange realized P&L | **0.00 difference** |

The runner stopped the strategy, canceled only its remaining orders, verified that
no other trader had added orders, closed its test exposure, and stopped both recorders.
The loss is a material negative result. The follow-up isolated incomplete startup history and stale execution batches;
this rehearsal does not establish that the strategy is competition-ready.

### Live advisories differ from the published replay

The recording contains 4,375 frames and 132 unique sequenced news messages, sequences
630 through 761 with no missing sequence inside that observed span. Of those messages,
129 match the published feed exactly. Three advisories differ:

- Sequence 664: cone coordinates/spreads, hurricane probabilities, and headline.
- Sequence 698: cone coordinates/spreads, hurricane probabilities, and headline.
- Sequence 733: cone coordinates/spreads and hurricane probabilities.

These are substantive forecast differences, not just timestamp formatting. Their
source and their effect on the strategy have not been established. The original
published history was not modified, and no parameters were tuned to this practice run.
This recording does **not** pass an exact published-feed comparison.

## Evidence and limits

Local receipts and logs are under `recordings/practice-20261024/` (ignored by Git).
Computed results and the tested adapter hash are in [practice-api-rehearsal.json](practice-api-rehearsal.json).
API fill timestamps lack offsets. The audit copies assign `America/New_York` for
sorting; all fills are on the same date, so this constant offset does not affect
replay ordering. Raw timestamps remain in the original receipts.

This is an integration rehearsal, not a full-season performance evaluation. Joining
midseason and deliberately closing positions after a short window do not reproduce
the strategy's intended holding period. Full-season live performance, announcements,
and behavior against competition-day opponents remain unverified.
