# Uncertainty guard experiment — declared 2026-10-24 06:38 UTC

## Observed behavior

The accepted `ent_cut=1.2` rule is documented as preventing additions when the
storm-pattern posterior is near uniform. In `FairValueTrader.on_quotes`, that
check is applied to some aggressive targets. `quote_passive` has no equivalent
check, and aggressive reversals can cross flat while the posterior is uncertain.
Existing orders can remain executable when they still meet the price floor.

Order prioritization has no measured performance result yet. This experiment
first tests the more concrete mismatch between the documented uncertainty rule
and the fundamental order paths. Basket hedges use separate pricing and are
outside the model-uncertainty rule.

## Fixed candidate

- Keep all model parameters, threshold 1.2, sizing, costs, and position limits.
- In an offline subclass, apply the uncertainty rule to every fundamental target:
  permit reductions, cap reversals at flat, and prevent new exposure.
- Cancel fundamental working orders that could add exposure beyond flat while
  the rule is active, including opposite orders whose net quantity is zero.
- Recompute reduction capacity after cancellation and preserve failure latches.
- Do not change the basket execution path, live configuration, or frozen worker.

## Verification and fixed evaluation

1. Reproduce the passive/reversal bypass with failing regression tests. Cover
   both sides, existing pending/partial orders, cancellation races/failure,
   allowed reductions, disabled threshold, and low-uncertainty behavior.
2. Record actual accepted passive additions under the rule in the baseline,
   without changing decisions. Require baseline P&L/fills/rejections/round P&L
   to reproduce the existing artifacts.
3. Evaluate all 75 development seasons, 451–525, at 0.25/1/3-second delays using
   the unchanged observed-touch profile and 10% limits: 225 paired scenarios.
4. Evaluate every current-snapshot scenario on closed captures 241, 242, and
   243: all three delays, full/half displayed depth, baskets off/on. Preserve
   all results and frame/source/model hashes.
5. Consider the next completed capture only after its official receipt. Never
   inspect future published outcomes from active season 244. These historical
   and previously viewed captures are reused evaluation data, not holdouts.

No automatic promotion: before considering a live change, require passing
regressions and independent review, no lower development mean at any delay,
no additional losing development seasons or worse worst case at any delay,
and no lower mean or additional negative scenario on any closed captured market.
If a gate fails, retain the complete evidence and do not change the live defaults.
These gates are conservative experiment decisions, not a guarantee of profit.

## Revision 2 — review findings, declared before rerun

The first frozen candidate is commit `dbe499e`. All 450 development runs and
72 capture runs completed. Their original outputs remain in
`out/uncertainty-guard-20261024-{dev,241,242,243}`. They failed the declared
profit gates. Review also found the cancellation pass was bypassed during an
active basket cycle; a zero accepted-passive-order audit did not establish
that old working orders had been removed.

Revision 2 checks working fundamental orders before basket, throttle, warm-up,
confidence, and quote-availability returns. Active basket target symbols retain
their hedge orders. It uses the latest computed posterior and does not change
the model update schedule. Failed cancellations stop the pass and are retried
at most once per second; competition identity and account readiness are checked
after cancellation. The existing later check covers a posterior refreshed by
the usual fundamental calculation.

Completed/development input must have a `ready` receipt, and the manifest now
includes the observed-receipt validator source. The four original runs did have
independently inspected matching `ready` receipts; their weakness was missing
enforcement in the driver, not a known use of an active settlement.

Rerun exactly the same 225 development pairs and 12 pairs per closed capture,
with all parameters and gates above unchanged. Save fresh outputs under
`out/uncertainty-guard-v2-20261024-*`. Do not overwrite the first run or call
the reused captures prospective validation.
