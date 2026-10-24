# Production practice supervision on four recorded markets

Source frozen at `5d7d67bc636ed34ad09630812070e37bf12219bb` before the comparison.
Independent final result review is pending. These are offline simulated outcomes,
not a new live practice run.

## What changed in the measurement

The previous sequential REST diagnostic used the core production client. This
comparison also executes the actual `Journal`, `PracticeExchange`,
`PracticeSession`, reduction-only cleanup, and final-receipt validation.
It includes extra account/history requests, individual cancellations, the $250
cumulative loss trigger, and the supervisor's 0.5-second monitoring schedule.
Every run starts a fresh single-season batch with zero prior P&L, 10% client
limits, and a three-hour virtual deadline.

The strategy, model, risk bounds and live defaults are unchanged. The only
change to the earlier diagnostic is an optional virtual-market factory; its
default behavior is preserved. No live account orders were sent.

Protocol: [supervised-replay-plan.md](supervised-replay-plan.md).
Fixed inputs: [supervised-replay-inputs.json](supervised-replay-inputs.json).

## Baseline equivalence before comparison

1. Reran all 64 archived settings from frozen reference `505a5ad`; every
   archived output field matched.
2. Reran those settings with the new average-cost accounting adapter and full
   server limits plus 10% client limits. All 64 again matched every archived
   field and the ordered request/fill trace hashes.
3. Only after that complete gate ran the 64 supervised settings. All three
   phases completed with zero diagnostic errors and unchanged source hashes.

The comparison therefore contains 128 baseline/supervised rows, plus 64 frozen
reference reruns. The reference manifest covers 31 files; baseline and
supervised manifests each cover 33. Each phase binds official receipt, selected
frames, capture identity/year and archived result hashes. A missing completion
summary, modified result, source change or changed capture blocks the next phase.

## Primary setting

Predeclared setting: 0.25-second request RTT, full displayed depth, baskets on.

| Capture | Core client terminal P&L | Supervised final receipt mark | Supervised terminal P&L | Outcome |
| --- | ---: | ---: | ---: | --- |
| 241 | +$118.09 | −$56.64 | −$56.64 | flat; history stop |
| 242 | +$1437.01 | +$810.03 | +$810.03 | flat; history stop |
| 243 | +$431.71 | +$279.33 | +$286.36 | settled; completed |
| 244 | +$628.14 | −$261.00 | −$261.00 | flat; loss stop |

Capture 244 demonstrates the missing execution effect directly: its core-client
result is +$628.14, but a fresh supervised batch samples a loss of $256.26,
stops, and finishes flat at −$261.00. Its position snapshot executes at virtual
t=457.0172 seconds; subsequent audits latch the stop at t=458.1422. Cleanup
starts after the monitor and in-flight worker finish, at t=459.8922, and the
final receipt ends at t=504.8922. The $250 trigger is not a guaranteed loss cap.
Prior accumulated batch profit would change its trigger condition; this
experiment fixes that prior profit at zero.

Capture 243 completes with simulated terminal P&L +$286.36 at official
settlement prices. Its final account
receipt remains marked at last captured prices (+$279.33), under the declared
marking convention. Those two values are different measurements.

## All fixed settings

Each row summarizes four depth/basket settings. “History” and “Loss” count
supervisor stops. Terminal P&L includes cleanup and settlement of any residual
holdings. It does not turn an incomplete trial into a completed trial.

| Capture | RTT (s) | Mean terminal P&L | Worst | Best | Losses | Completed | History | Loss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 241 | 0 | −$46.62 | −$64.77 | −$22.54 | 4/4 | 0/4 | 4 | 0 |
| 241 | 0.05 | −$59.72 | −$72.25 | −$47.19 | 4/4 | 0/4 | 4 | 0 |
| 241 | 0.25 | −$66.69 | −$79.43 | −$53.84 | 4/4 | 0/4 | 4 | 0 |
| 241 | 1 | +$147.12 | +$127.30 | +$157.85 | 0/4 | 4/4 | 0 | 0 |
| 242 | 0 | +$1416.96 | +$1384.41 | +$1455.72 | 0/4 | 0/4 | 4 | 0 |
| 242 | 0.05 | +$1386.87 | +$1357.68 | +$1426.66 | 0/4 | 0/4 | 4 | 0 |
| 242 | 0.25 | +$794.62 | +$779.22 | +$810.03 | 0/4 | 0/4 | 4 | 0 |
| 242 | 1 | +$1350.86 | +$1249.28 | +$1479.88 | 0/4 | 4/4 | 0 | 0 |
| 243 | 0 | +$634.24 | +$578.31 | +$692.74 | 0/4 | 0/4 | 4 | 0 |
| 243 | 0.05 | +$572.60 | +$534.49 | +$611.47 | 0/4 | 0/4 | 4 | 0 |
| 243 | 0.25 | +$250.75 | +$215.14 | +$286.36 | 0/4 | 4/4 | 0 | 0 |
| 243 | 1 | −$150.45 | −$209.79 | −$91.11 | 4/4 | 0/4 | 4 | 0 |
| 244 | 0 | −$294.30 | −$310.74 | −$277.86 | 4/4 | 0/4 | 0 | 4 |
| 244 | 0.05 | +$613.40 | +$470.63 | +$732.64 | 0/4 | 0/4 | 4 | 0 |
| 244 | 0.25 | −$282.17 | −$303.34 | −$261.00 | 4/4 | 0/4 | 0 | 4 |
| 244 | 1 | +$507.10 | +$477.91 | +$559.01 | 0/4 | 4/4 | 0 | 0 |

Across all 64 supervised settings: **40 positive, 24 negative**, mean +$423.41,
range −$310.74 to +$1,479.88. Only **16 complete the full season**; 40 stop on
the history guard and 8 on the loss trigger. All 8 loss stops occur in capture
244. The core-client baseline has 63 positive settings and 1 negative; its mean
is +$707.14. These are sensitivity settings on four reused paths, not 64
independent seasons or a probability of success.

## Stops and cleanup findings

- The 40 history stops expose a production guard issue: a valid next
  `storm_formed` message clears the current observation until the first weather
  message arrives. Submission eligibility correctly pauses, but the practice
  supervisor treats that temporary state as permanent lost history. Delivery in
  separate callbacks can stop the batch. A separate fix must preserve genuine
  missing-history, malformed-transition and duplicate-formation protection.
- Cleanup reports **42 flat, 16 settled, 6 attention**. All 64 final receipts
  verify identity/account/history in the modeled account; verification alone
  does not mean cleanup flattened exposure.
- The 6 attention cases retain holdings. Four are capture 242 at zero RTT,
  leaving GRID shorts of 14 or 18 shares. Two are capture 244 at zero RTT and
  half depth, leaving AQUA −8, GRID −5 and REIN −20. Their terminal results
  include these residual holdings; their cleanup is not called successful.
- Observed final-receipt snapshots and their individual request times are
  retained separately from the server account after all receipt requests finish.
  No additional fills occur after that point in these 64 settings; a regression
  test verifies that an unresolved order can still fill later.
- Every fill, conversion and accepted reservation is independently checked
  against the 10% practice caps. Server limits remain full size. Average-cost
  quantities, cash, marked P&L and final settlement reconcile.
- Timing, additional requests, per-order cancellation, startup replay, stop and
  cleanup change together. The paired difference is the total production-
  supervisor effect under this model, not a separate causal estimate for each
  component.

## Evidence and verification

[evidence/supervised-client](evidence/supervised-client) contains metadata,
results and completion summaries for all three phases; stdout/stderr logs; and
a compressed archive of all 64 supervised journals, observations, startup
prefixes, receipts and per-run results. No failed or stopped scenario was
discarded. The complete source suite passes **578 Python tests**, including
42 new accounting, supervision, timing, cleanup and comparison-gate checks.

The independent code review reproduced timing and provenance defects before
they were corrected, then approved the frozen source. Final result review
checks all rows, source/input/artifact hashes, and representative guarded reruns.

## Practical limits and next action

This remains a virtual-fill model with incomplete knowledge of quote coverage,
no queue priority or own market impact, fixed RTT with midpoint execution,
instantaneous CPU/file reads, and no extra fees. Matching stops at the last
captured frame; official settlement is exposed only at the later recorded
receipt. Position marks continue using captured prices after that receipt.
No subsequent-season rollover is modeled. Captures are reused research data.
This is not an exact reconstruction of batch 01: it uses the frozen current
runtime, fixed request delays and a fresh single-season batch.

The inter-round practice guard needs a narrow, independently reviewed fix and
a new frozen comparison. The loss trigger and practice size remain unchanged.
Actual evidence remains one clean completed practice season at +$141.16;
shared-account ownership is unresolved, so no new live batch is authorized by
these offline results. Consistent live profitability remains unproven.

