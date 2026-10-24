# Replay the practice supervisor — declared 2026-10-24 07:30 UTC

## Question

The fixed direct-client replay for capture 244 ended at +$628.14 in its primary
scenario but reached a -$263.29 mark. That replay omits the practice supervisor's
cumulative loss stop, extra identity/history requests, and cleanup. Determine
how these paths affect decisions and the stopped account, using production
`Journal`, `PracticeExchange`, `PracticeSession`, and cleanup functions offline.
Do not change live strategy parameters, the $250 practice loss trigger, account
ownership requirements, or either currently frozen evaluation checkout.

## Implementation boundary

- Extend the reviewed virtual-server model through dependency injection and an
  offline subclass. Default direct-client behavior must remain unchanged.
- Exercise real production supervisor and reduction-only cleanup methods through
  an offline transport in their method-resolution order. Override all HTTP and
  virtual-clock access; use dummy credentials. Do not run the actual websocket
  or key-file startup. Reproduce its fresh-account checks and bot-mode check.
- Reuse production feed-log startup with only the recorded prefix available at
  its virtual read time. Retain its clock GET exactly once and pass its returned
  year, round and seen sequence IDs to the session. Recordings arriving during
  startup remain queued in the existing capture/inbox model. CPU/file reads are
  instantaneous; neither startup replay nor the inbox may reveal future frames.
- Keep the real exchange's full server limits. Apply the practice fraction once
  to client limits; independently verify that orders/positions respect 10% caps.
- Provide complete order history, including filled and canceled orders, and
  individual-order cancellation. Preserve the strict history-envelope and
  500-row saturation checks. The modeled account contains only this run's orders;
  this is not evidence that the actual shared account is exclusive.
- Return finite position cost basis and realized/unrealized components using an
  average-cost ledger driven by fills. Closing and crossing zero must realize
  correct P&L. For cash-neutral ETF conversions, book the component transfers at
  current component marks and the ETF at their summed basket value. This is a
  declared accounting convention, not a claim about the live exchange's cost-
  basis convention. At every mutation, assert that quantities and aggregate
  cash plus marked/settlement P&L equal the virtual exchange's accounting.
- `/symbols` exposes settlement-active prices only at or after the recorded
  official receipt time and the irreversible terminal fence. The strategy must
  never receive future settlements while trading is possible. Matching closes
  at the last captured frame; report its gap to the official receipt.
- `/positions` continues to use last captured marks after settlement becomes
  available; `/symbols` and verified settlement scoring use official prices.
  This is an explicit unverified marking convention. Label stops as occurring
  before the terminal fence, in the terminal-to-receipt gap, or after the receipt,
  and record whether the server market was open when the stop latched.
  Contract/invariant failures anywhere in time advancement, fills, transport or
  cleanup latch a fatal diagnostic error even if production code catches them.

## Stop and cleanup scheduling

Use a fresh single-season batch with no prior accumulated profit, a $250
cumulative loss trigger, a three-hour virtual deadline, and normal strategy
parameters. The one-season completion target only ends the local diagnostic;
it does not change pre-close decisions. Preserve real per-refresh observation
and per-submission permission checks. Record the exact sampled mark and time
that cause any stop; do not substitute the lowest server mark for a polled mark.

The real supervisor checks completion every 0.5 seconds, anchored to monitor
startup after the initial account checks and session construction. Model those
monitor ticks during virtual clock advancement. A tick detecting a latched stop
sets the session cancellation flag, but cannot kill an already running request
or synchronous client step. Cleanup starts at the later of that detection tick
and completion of its last worker. For example, a stop at 0.1, detection at 0.5,
and worker completion at 0.8 starts cleanup at 0.8, not 1.0. If a step returns
before detection, further refresh/cancel steps may begin before the monitor
cancels the driver. Continue these steps with the existing submission veto.

All fills/arrivals during requests and waits continue at the server. Monitor
callbacks only change the stop flag; they never recursively invoke a strategy.
An already submitted request can still execute after stop detection. At equal
times, captured arrivals/terminal close precede the monitor tick, which precedes
the next request operation or client step. Distinguish the positions snapshot's
request midpoint from the later `Journal.observe` time after additional audits;
the latter is when its stale or current mark can latch a stop. Advance production
cleanup sleeps on the virtual clock and retain its real retry limits, individual
cancellations, ownership audits, and reduction-only order rules.

After cleanup, run the production final-receipt validation. Record its marked
P&L, flat/settled/attention status, remaining positions/orders, and every stop
or error. Preserve its separately timed observed position/order snapshots and
distinguish those from server holdings after all receipt requests finish.
Then advance the market without strategy callbacks to the capture's
terminal fence to value any residual holdings. Keep stopped-run receipt P&L
separate from residual terminal settlement P&L; do not call an unflattened
attention result successful cleanup. Outstanding orders can still fill during
this advance; value the resulting account, not frozen cleanup-receipt holdings.
No next-season rollover is simulated. After the official receipt, allow at most
`max(60, 100 * RTT)` further seconds of closed-market polling to obtain normal
completion. Exhaustion is a diagnostic stop, never a fabricated completion;
report no-trial, incomplete-trial and completed-trial outcomes distinctly.

## Fixed comparison

Use only completed captures 241–244 and their already validated official-ready
receipts. Do not read published outcomes for active season 245. Freeze source
and this plan before computing comparative P&L.

For each capture run the same 16 combinations: RTT 0/0.05/0.25/1 seconds,
displayed depth 1/0.5, baskets off/on, with 10% client limits and action cap 90.
Compare the direct-client baseline with the supervised path: 128 scenario rows
across four captures and two execution paths. The primary descriptive setting
remains 0.25-second RTT, full depth, baskets enabled, starting with zero prior
practice P&L. No threshold tuning or best-scenario selection follows.

Before interpreting supervised results, require the baseline adapter to reproduce
every archived direct-client output field on all 64 original grid settings.
Also rerun the frozen reference and compare hashes of ordered requests
(method, path, body, timing and mutation acknowledgements) and fills. Read
response accounting decomposition and server/client limit placement are the
declared differences, so read-response bodies are excluded from trace hashes.
Accounting-field decomposition may differ; trade behavior must not. A failed
equivalence check blocks interpretation and must be retained. Preserve all
errors, early stops, incomplete cleanup, and losses.

## Required regression checks

1. Average-cost fills: add, partial close, flat close, short positions, and
   reversal, including aggregate cash/mark/settlement invariants.
2. Create/redeem accounting remains cash-neutral through long/short crossings.
3. Filled/canceled order IDs remain visible in complete history; foreign IDs,
   saturated histories, and identity changes stop the production supervisor.
4. The $250 condition uses observed account P&L plus prior accumulated results,
   not a server-only minimum; test both stopping and non-stopping boundaries.
5. Once stopped, further strategy orders are vetoed, but owned reduction-only
   cleanup is permitted. Fills before cancellation reconcile correctly.
6. Cleanup refuses unknown orders, refuses exposure increases and new competition
   identities, honors retry limits, and accurately reports remaining exposure.
7. Settlement access is blocked before the terminal fence; all network,
   credential, and downloaded-history access is denied in complete tests.
8. Fresh startup preserves confirmed identity and weather history, and the
   synchronous step completes before cleanup starts.

Independent design and result review are required. The existing virtual-fill,
quote-gap, phase-inference, fixed-RTT, instantaneous-CPU, and no-market-impact
limitations remain. A valid offline result cannot authorize shared-account
trading or establish consistent actual profit.
