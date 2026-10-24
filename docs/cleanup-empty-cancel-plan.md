# Cleanup refresh after an empty cancellation pass

Declared 2026-10-24 08:48 UTC, before implementation and alternative performance
runs. Author: Codex, Arjun's systematic-equities workstream.

## Hypothesis

The existing cleanup loop refreshes and audits the account, cancels each open
order, then immediately repeats the same refresh and audit even when there were
no open orders. A refresh costs four GETs and the ownership audit costs two.
Skipping that second pair in one narrow case may shorten cleanup without
changing submission safeguards. Timing changes can still worsen fills or P&L.

The candidate skips the second refresh/audit only when the first reconciled
snapshot has no open orders, has nonzero exposure, and the ownership audit says
the market is running. Any cancellation attempt, flat snapshot, or closed
market retains both refreshes. Every prospective closing order still obtains
its book, refreshes positions/open orders, checks scope, and passes the existing
send-time scope and reduction-only checks. No cached check replaces a
submission-time check. The rejected quote-order candidate is not included.

## Invariants and preflight

- Preserve strategy, model, parameters, limits, action rate, loss trigger,
  history/identity checks, five-pass retry bound and price cushion.
- Preserve the post-cancellation refresh whenever the first snapshot contains
  any open order, including failed or uncertain cancellation.
- Keep both refreshes before reporting an initially flat or closed account.
- Fresh reconciliation before POST must handle flattening, reversal, partial
  conversion, newly working orders, foreign fills, season rollover and closure
  during the book request. The final send-time audit still applies.
- Write meaningful failing tests for the reduced request path before modifying
  production code. Run existing cleanup safety tests and full Python suite.
- Obtain independent code/guard review before evaluating capture performance.
  Freeze the reviewed candidate and comparison driver in a commit first.

## Fixed comparison

Use baseline `cd3eb239bd7bad97b34f10a8f2bb0b2e1c0f5026` and the same immutable
241–245 input/archive specification as the completed quote-order experiment:
`out/cleanup-quotes-v1-20261024/spec.json`, SHA-256
`8d08de8cca753d3333f141a0a462ce2f24914ab366cc0cdcf27ed87e0845fc6f`.

Run all 80 settings: five captures, RTT 0/0.05/0.25/1 second, full/half displayed
depth and basket off/on. Preserve 10% limits, 90 actions/minute, the $250
observed-loss trigger and zero prior P&L. Primary: 0.25 second RTT/full depth/
basket on. Do not select a latency or path after seeing the result.

Reuse the guarded driver from `5832359`, changing only its descriptive header
and source-manifest plan path. It must first reproduce every baseline result
field and all seven archived journals. Candidate pre-cleanup request/fill hashes
and stop fields must match exactly. Preserve source/input/artifact hashes,
complete 80-row prerequisite gates, sticky audit failures, early-settlement
guards and the ban on network, credentials and downloaded history.

Report all outcomes, including failures, residual positions and interrupted
trials. Retain all eight journals/profiles per run and compare request counts,
elapsed cleanup time, fills and terminal P&L. Reproduce representative results
independently before making a conclusion.

## Decision rule and limits

Reject production promotion for any new guard failure, increased residual
exposure/attention outcomes, worse worst terminal loss, increased losing-setting
count, lower overall mean terminal P&L, or worse mean cleanup duration across the
fixed twelve early stops. Passing these checks is evidence for a candidate,
not automatic proof of live benefit. Explain individual regressions and require
independent review before any production change.

These five paths are reused development diagnostics. The 80 settings are
correlated, not independent seasons. The separately frozen forward evaluators
remain unchanged; no capture-246 or later published future outcome is read for
this experiment. Shared-account ownership remains unresolved, so this work
does not restart live orders or cancel another actor's orders.
