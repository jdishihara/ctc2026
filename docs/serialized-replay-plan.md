# Serialized client replay — declared 2026-10-24 06:51 UTC

## Question

How much does serial REST processing change the current strategy's decisions
on completed recorded markets? The existing capture replay delays order
activation but does not block the strategy while HTTP calls complete.

In completed owned season 241, the journal contains 33 acknowledged orders:
13 pending, 19 filled, and 1 partial. Their responses omit fill quantities.
The filled/partial path in `LiveExchange.place` therefore refreshes the clock,
orders, positions, and trades before it returns. There is also one conversion.
The 34 matched POST request/response durations have median 0.277 seconds,
maximum 1.472 seconds. These are acknowledgement durations, not fill latency;
individual GET durations were not logged in that trial.

## Offline design

- Keep the production strategy and all parameters unchanged.
- Reuse `LiveExchange`, `LiveSession`, and `MarketInbox` with an offline adapter.
  Override every network method; use a dummy key and a non-routable URL. The
  adapter must fail on unsupported endpoints rather than fall back to HTTP.
- Maintain separate exchange books/account state and client quote/account views.
  Advancing the virtual server clock processes incoming recorded quotes/news
  and resting fills, while the client's inbox accumulates news and coalesces
  quotes exactly as the live inbox does. The client sees them on its next drain.
- Model each REST request with a fixed round-trip duration. Execute the server
  operation halfway through that interval, return its captured response at the
  end, and preserve real sequential account-read ordering.
- Return the observed status-only order acknowledgement shape. Filled or
  partial acknowledgements must follow the production refresh path. Pending
  responses reserve capacity until reconciliation. Conversions also require
  reconciliation through the production adapter.
- Use virtual crossing fills against the external recorded top of book, with
  full/half displayed size. Preserve the existing conservative resting-limit
  fill rule. Account for consumed displayed size and do not reveal future news
  or settlements to strategy decisions.
- Treat pending news as a submission veto while the worker is blocked. Keep
  the production quote freshness, history, and identity checks.

## Fixed evaluation

Use only completed captures 241, 242, and 243 with confirmed `ready` settlement
receipts. Do not read future published outcomes from active season 244.

Run all 16 client scenarios per capture: REST round trips of 0, 0.05, 0.25,
and 1 second; displayed-depth fractions 1 and 0.5; baskets off/on. Limits stay
at 10%, rate limit 90, and all strategy parameters remain those of the existing
captured-market comparison. The zero-duration client is the paired reference
for timing effects. The older replay is contextual evidence, because it also
differs in account reconciliation behavior.

The delay grid is a stress test, not a fitted latency distribution. Report all
48 scenarios, including failures, losses, request counts, blocked submissions,
final positions, and drawdown marks. Hash selected frames, receipts, source,
model, and the plan. Freeze source before evaluation and verify hashes after.

## Required checks

1. Incoming quotes during a request update the exchange book without leaking
   into the client view; the next inbox drain supplies the latest quote.
2. Pending news during a request blocks the next submission until processing.
3. A fully or partly filled status-only acknowledgement refreshes real holdings
   and remaining reservations before another order can use position capacity.
4. A fill before cancellation is reflected in post-cancel positions; no future
   settlement is consulted while trading is open.
5. Sequential GETs return snapshots at their respective server times; a fill
   between orders and positions reads is counted conservatively.
6. Conversions respect limits and reconcile all legs; unsupported API paths
   raise, and a network-denial test verifies the complete replay is offline.
7. A real receipt must be closed/ready; all output scenarios are reproducible.

Independent review is required before interpreting results. This diagnostic
does not activate a bot or promote a strategy. Queue priority, own market
impact, server-side processing variability, fees not represented in prices,
and actual conversion execution remain unmodeled. The captured data have
already been examined and are not untouched validation.

## Scheduling contracts frozen after design review, before implementation

- Recorded arrivals and observed closes precede REST operations at the same
  timestamp. Order activation is immediate at the operation midpoint, with
  no second hidden delay. Responses are deep-copied there and delivered after
  the remaining half round trip.
- Only one client step runs at a time. REST clock advancement queues arrivals
  without recursively processing client steps. An idle client wakes at the
  next arrival or after 0.25 seconds, whichever comes first.
- A closed phase persists until observed new-round/open-phase information;
  a valid quote alone cannot reopen that closed round. The terminal fence is
  the last captured frame, with close winning ties. Final news is still
  delivered, while matching and mutations at/after that fence are prohibited.
  Finish outstanding calls and finitely drain queued data, then stop heartbeats.
- Report last-frame cutoff, official ready-receipt time, gap duration, and
  remaining inventory valued at settlement. This is tail truncation, not a
  lower bound on profit: suppressed unobserved trades could help or hurt.
- Order books include external depth plus own resting orders. The production
  adapter subtracts its cached opposite-side orders, so an external-only book
  would incorrectly subtract them twice.
- Unsupported endpoints latch a fatal contract error. Final validation fails
  even if production exception handling catches that error. Calculate marks
  and settlement P&L from server cash/holdings; never expose settlement prices
  through trading responses. Report lowest marked P&L separately from maximum
  peak-to-trough drawdown.
- Conversion reconciliation follows the existing overlay's refresh path;
  there is no additional implicit refresh. Strategy computation is modeled as
  instantaneous. No empirical CPU delay or network-delay distribution is fitted.

## Version 2 correction declared before rerunning results

The first frozen source `b065a8111187a48c183162df97046db88907d397` rejected all
48 scenarios for incomplete model history. No valid P&L was computed. Its
outputs remain at `out/serialized-client-20261024-{241,242,243}`. Independent
review verified all rows, grid combinations, source/input/receipt hashes, and
tail gaps. The original 27 tests and six additional boundary checks passed,
but the full-history test had no quotes and missed the initialization issue.

The driver followed the then-current direct launcher's incorrect ordering:
initialize the strategy with an empty competition ID, then refresh the account.
The first quote callback reset accumulated history while session sequence
tracking retained those messages. Two new complete-history-plus-quotes
regressions, at zero and 0.25-second RTT, fail under that ordering.

Production fix PR #15 confirms a complete account snapshot and nonempty string
competition ID before constructing/initializing the strategy. It was reviewed
and merged independently. Version 2 adopts the same ordering and initial-state
gate. Supervised practice already used the correct order. This change addresses
initialization, not strategy parameters, fill assumptions, or the earlier loss.

Freeze the corrected source, preserve all failed version 1 artifacts, and rerun
the identical 48 scenarios into separate `out/serialized-client-v2-20261024-*`
directories. The paired timing reference, fixed grid, required checks, and
limitations above remain unchanged. Independent review must approve the fresh
results before interpreting or merging the diagnostic.
