# Capture 247 cleanup: diagnosis and proposed bounded test

**Decision:** approve the design below for a predeclared offline implementation
and test. This is not production approval. No strategy, cleanup policy or
performance simulation was changed or run to prepare this diagnosis.

## Established mechanism

All three original zero-RTT attention cases begin cleanup at relative time
**2167.5**, finish at **2172.5**, and retain **REIN −6**, with no open orders.
The full-depth/basket-off case records five REIN book requests; each half-depth
case records two. No case attempts a REIN cleanup order.

The last REIN quote is at **2154.025929**: it is already **13.474 seconds old**
at cleanup entry. The frozen replay only exposes quote depth at ages <=5 seconds
(`scripts/replay_serialized_client.py:164–177`). The retained full
half-depth/off trace shows empty REIN books at **2170.5 and 2171.5**, with no
REIN cleanup fills. Its other positions reconcile to zero.

The next actually recorded REIN quote is at **2173.325811**, **0.826 seconds
after cleanup ends**. Ask remains $90.16; size changes from 20 to 19. The new
quote supplies 19 units at full depth or floor(19/2)=9 at half depth, exceeding
the six-unit short. The failure is **expired quote freshness followed by retry
exhaustion**, not evidenced consumption of REIN liquidity. This conclusion is
conditional on the replay model, not proof that a live REST book was empty.

| Original attention setting | Observed mutations in final rolling minute | Cleanup orders / cancels | Residual |
| --- | ---: | ---: | --- |
| 0 RTT / full / basket off | 24 | 9 / 1 | REIN −6 |
| 0 RTT / half / basket off | 26 | 10 / 2 | REIN −6 |
| 0 RTT / half / basket on | 26 | 10 / 2 | REIN −6 |

All cleanup order IDs and cancellation acknowledgements are valid. There is
no observed cleanup rejection, unresolved ownership block or post-receipt fill.
These counts are below the 90-action budget. Full request/fill timing is
directly retained for half-depth/off; the other two cases have complete
original journals, request counts and the common recorded quote path.

The unchanged 0.05-RTT/half/off comparator spends 21.15 seconds in cleanup,
submits REIN buy 6 at 2188.825, and fills 1 at $90.12 plus 5 at $91.02 at
2189.352968. It finishes flat, at different and worse prices. This supports an
elapsed-time mechanism; it is not a causal P&L comparison or evidence that
slower execution is desirable.

## Exact proposed loop

1. Capture cleanup-entry time with **`practice.time.monotonic()`**, immediately
   before the existing `CleanupExchange` construction. This is already patched
   to server time in the frozen evaluator; do not introduce a separately
   imported real clock.
2. Retain passes **1–5 exactly**, including existing early returns, HTTP order,
   scope/history checks, cancellation and fill reconciliation, symbol order,
   price limits and one-second sleeps. The new budget guard never gates them.
3. Permit passes **6–62** to begin only while monotonic elapsed time is finite,
   nonnegative and **<=61 seconds**. A regressed or invalid clock disables extra
   passes. Never reset the origin when progress occurs. Total passes are capped
   at 62 even if a faulty clock stops advancing.
4. Extra passes retain existing safety checks and sleeps, with the additional
   mutation guard below. Existing flat/settled/unsafe-account returns remain
   immediate. At loop exhaustion retain the existing final reconciliation and
   truthful flat/attention classification, followed by the final receipt.

This bounds **pass admission and count**, not total wall time. An admitted pass
may finish after 61 seconds; its final one-second sleep, in-flight HTTP and final
reconciliation also take time. Five slow original passes may already exceed the
horizon, in which case no extra pass begins. Do not claim a hard 61-second
wall-clock timeout. A pass beginning at elapsed 61 has crossed the strict
60-second expiry boundary; sleeping until exactly 60 and then stopping would
not do so.

## Cancellation and action-budget resolution

Current `CleanupExchange` constructs a fresh client action deque
(`bot/practice.py:483–488`, `bot/live.py:55–57`). Its direct DELETE calls bypass
`LiveExchange._action_ok` (`bot/practice.py:552–555`), although the replay server
counts them. Therefore adding passes without another guard is insufficient.

### Journal events cover the mutations

Count one conservative charge for each of these **existing** events:

| Event | Charge |
| --- | --- |
| `request`, method POST or DELETE | One; includes ETF conversions and failed/None responses |
| `cleanup_cancel` | One, including None responses |
| `cleanup_order` | One, including a None ID (possibly a local non-send; conservative) |

Exclude `request_attempt`: its POST is already represented by `request`.
Exclude GET/status/final-state/budget-wait diagnostics. Count across all CIDs
in this run conservatively; this does not replace the expected-CID ownership
fence. No cleanup POST is also logged as a `request`: cleanup uses its separate
adapter, so these counted categories do not overlap in the frozen source.

### Use monotonic observation, not a wall-clock file scan

`Journal.event` persists `at=time.time()` (`bot/practice.py:144–146`). Those
timestamps cannot safely be compared to a monotonic clock. Completion-based
event timestamps are conservative relative to server acceptance only when
their clock is sound. Do **not** approve a raw `actions.jsonl` wall-time scan as
an unconditional runtime rate guarantee.

Instead, initialize a **private monotonic shadow ledger at Journal creation**.
Observe the existing event calls using `practice.time.monotonic()` without
changing their JSON payloads or request behavior. Record counted events at
completion-event entry, before the file write. Completion follows transport
acceptance, so aging from completion can overcount but cannot expire an
observed accepted action too soon. The journal is already required to start
in a fresh directory; no wall-time reconstruction or resume is needed.

Track outstanding `request_attempt` diagnostics separately: pair them with the
subsequent POST `request` using CID/path/body under the single-owner execution
model. An unmatched or inconsistent attempt disables extra mutations. Neither
such diagnostics nor their completion are counted twice.

### Gate only additional-pass mutations

Immediately before **each extra-pass direct DELETE**, and before **each
extra-pass `place()`**, expire ledger entries only when age **>60 seconds**.
Require fewer than **90** unexpired entries. Equality at 60 still counts, just
as in the existing client/server limiters. Keep existing limiter checks too.

Cleanup runs after the original worker is joined and has one synchronous
mutation owner. No other mutation can interleave between this preflight and
the existing completion event. The next mutation sees that completion charge,
including a rejected or uncertain response. If this ownership model changes,
atomic reservations would be required; this design does not authorize that.

When full, **do not call `send()` or `place()`**. Defer mutations, keep existing
orders reserved, reconcile/read only and follow the existing sleep before
another eligible pass. A new non-mutation budget-wait diagnostic may be logged.
Do not fabricate a None response or a counted cleanup-order/cancel event for
this intentional non-send: that can be misclassified as uncertain ownership.

Ledger absence/schema failure, unresolved attempts, invalid/regressed monotonic
time or a journal-write exception disables extra mutations. An exception must
not be swallowed and followed by further mutations. Existing lost-ACK,
foreign-history, rollover, reconciliation and strict-reduction failures still
terminate through their present safety paths. Register acknowledged IDs before
status-only-fill refresh as today.

This guard does not retroactively repair the original five passes or guarantee
a venue-wide budget in the presence of another actor. Its scope is preventing
the extension from adding unbudgeted mutations by this run.

## Required predeclared checks

- Exact original request/fill prefix through the first five passes, including
  unchanged successful early exits; no changes to models or pre-stop trading.
- Fresh quote arrives after the old fifth pass; never arrives before the new
  bounds; partial size and cancelled-order racing fills remain reconciled.
- 89 entries allow one mutation; 90 defer **both POST and DELETE**; age 60 does
  not expire; age greater than 60 does. Include original trading, conversions
  and the first five cleanup passes in the ledger.
- POST attempt/completion pairs count once, cleanup None outcomes count
  conservatively, and local budget deferral does not manufacture lost ACKs.
- Wall-clock jumps leave the monotonic budget unchanged; bad/missing ledger,
  lost ACK, foreign activity, rollover and market close remain fail-closed.
- Slow initial passes suppress extras past 61; pass-count cap remains effective
  with a nonadvancing test clock. Report admitted-pass overrun honestly.
- Evaluate the entire predeclared grid and retain all losses, attention states,
  residual holdings, final-receipt/terminal differences and mutation counts.

The 61-second choice is structural, not a threshold fitted from this failure.
The next recorded depth makes the hypothesis testable; no extended-policy fill
or P&L is established here.

## Evidence

`diagnosis.json` retains exact quote records, request/fill excerpts, all three
journal summaries, the proposed design and input/source hashes.
`hash-receipt.json` binds this document, the JSON and `build_evidence.py`.
The previous independent audit archive remains unchanged at SHA256
`8930064de48813f53025be67a6d0db6e00019e86631b36b6e176d38dc9329b93`.
