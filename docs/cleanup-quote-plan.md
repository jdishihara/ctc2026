# Cleanup quote ordering diagnostic

Declared 2026-10-24, before running an alternative cleanup implementation.
Parent: `cca972e1088374b151c3a6b4235b5fe3599d90c8` (PR #21).

## Observed problem

Two instrumented reruns of frozen runtime
`cd3eb239bd7bad97b34f10a8f2bb0b2e1c0f5026` reproduced every archived
result field and all seven journal files byte for byte. Network, credentials,
downloaded history and premature settlement reads were blocked.

| Scenario | Cleanup elapsed | HTTP requests | Time in requests | Quote age at closing POST |
| --- | ---: | ---: | ---: | ---: |
| Capture 243, 1 s RTT, half depth, basket on | 238 s | 236 | 236 s | 9 s for all 9 orders |
| Capture 245, 1 s RTT, full depth, basket off | 228 s | 223 | 223 s | 9 s for all 6 orders |

The cleanup loop fetches a book, then performs a four-request account refresh,
a two-request ownership check, and another two-request check inside `send`
before the closing POST. Thus the chosen price is nine round trips old at
execution, even when all requests succeed. Request counts include the final
receipt. These are virtual replay timings, not measured live latencies.

## Candidate and invariant

Move the per-symbol book read after the existing account refresh, scope check,
open-order/market-open check and nonzero-position check. Retain the ownership
audit inside `send`, all reconciliations, cancellation behavior, retry count,
position sizing, limit-price cushion, rate limit and strategy parameters.
Expected book age is three RTTs, subject to transport timing. Do not remove
safety checks or assume reduced quote age guarantees better P&L or faster
flattening.

Tests must show the freshest book follows reconciliation; a competition
change, unknown order, market closure, or invalid book still prevents a new
closing order. A position filled during reconciliation must not be reopened.

## Fixed comparison before any outcome selection

Use all 80 archived supervised settings from complete captures 241–245:
RTT 0, 0.05, 0.25 and 1 s, full/half displayed depth, basket off/on.
Use exactly the archived selected frames and official closed receipts,
10% limits, 90 actions/minute, $250 observed-loss trigger, zero prior P&L,
and unchanged trading parameters. Record candidate source hashes before
execution. Frozen runtime, forward driver and forward evaluators are untouched.
Capture 246 remains excluded until its official closure, and is not part of
this candidate-selection comparison.

Compare all rows, including errors and adverse outcomes. Verify that
pre-cleanup actions and stop conditions are identical to the archived runtime;
retain request traces, quote ages, cleanup duration, fill timing, terminal
P&L, residual positions, open orders, attention states and final receipts.
No favorable subset may substitute for the full comparison. The chosen
primary setting remains 0.25 s RTT/full depth/basket on.

Use safety regressions, full-suite checks and independent review as merge
gates. If the comparison exposes additional safety failures or worse residual
exposure, investigate before merging. P&L movement is descriptive evidence on
reused paths, not an untouched holdout or evidence of consistent live profits.
Any further cleanup optimization requires a separate declared hypothesis.

## Baseline instrumentation retained locally

- `/tmp/practice_cleanup_243_profile.py`
- `/tmp/practice_cleanup_245_profile.py`
- `/var/folders/5_/4_9w4ch971l2mm9c6fqtg5400000gn/T/practice-cleanup-243-profile-r6f5_c0_/`
- `/var/folders/5_/4_9w4ch971l2mm9c6fqtg5400000gn/T/practice-cleanup-245-profile-ift92t6c/`

These extend the independently guarded reproduction harnesses with a separate
request call-stack/timing list; server request records are not mutated. They
retain exact archived-result and journal assertions. Preserve the artifacts
and their hashes with the eventual comparison report.
