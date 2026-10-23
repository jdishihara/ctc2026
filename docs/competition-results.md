# Competition strategy continuation — 2026-10-23

## Accepted configuration

Candidate `final_limit` was selected on seasons 451–525 and frozen at `2ae7a02`
before examining verification seasons 526–600. It combines corrected allocation
of reported damage with exact final rebuilder valuations and 0.5% entry/full-size
thresholds. The existing per-symbol residual-error floor remains in force.

Final-phase settings require all three final reports and complete observed
weather from all rounds. A gap or snapshot reconstruction retains the previous
conservative settings. Earlier phases keep the accepted 15-second cadence,
2.5% entry floor, 3% full-size edge and all previous fitted parameters.

Live, backtest, preflight and the diagnostic script agree on these defaults. `--no-final-exact`
disables the final-phase valuation and threshold changes. It retains the damage
report correctness fix. The experimental sizing ramp and wind conditioning are
disabled.

## Verification

Each regime contains the same 75 seasons. Reference is `e8d4307`, the previous
efficiency/execution patch. Its saved PnL is rounded to cents. No model was fitted
or candidate selected on these verification results.

| Metric | Deep reference | Deep candidate | Thin reference | Thin candidate |
|---|---:|---:|---:|---:|
| Mean PnL | 9,345.51 | **9,452.36** | 5,927.40 | **5,993.53** |
| Median | 9,435.54 | 9,381.40 | 6,201.42 | 6,205.64 |
| 10th percentile | -147.60 | -254.55 | -2,682.24 | -2,712.92 |
| Worst season | -15,911.48 | -15,984.81 | -17,236.05 | -17,314.91 |
| Losing seasons | 8/75 | 8/75 | 13/75 | 13/75 |
| Fills/season | 363.89 | 376.80 | 901.39 | 918.83 |

Mean improvement is **106.85 deep / 66.13 thin**, about 1.14% / 1.12%. In each
regime, 41 seasons improved, 32 worsened and 2 were unchanged within one cent.
The paired bootstrap 95% intervals for mean improvement are **[49.01, 169.82]**
and **[27.37, 107.85]** (10,000 resamples, seed 20261023). These intervals are
conditional on the historical seasons and simulator; they do not include live
execution error, changing competitors or candidate-selection uncertainty.

Both means increased. Thin p10 deteriorated 1.14%, below the repository's 10%
limit, so the predeclared acceptance rule passed. Deep p10 deteriorated by 106.95
currency units, and both worst seasons were slightly worse. This package improves
mean PnL; it does not improve every tail metric.

The candidate peaked at 41/48 actions per minute versus the enforced 120 cap,
with zero rate blocks and zero rejected orders. A report-correction-only
ablation produced means 9,342.01 / 5,925.58; final-phase changes account for the
improvement over that ablation.

[Machine-readable evidence](competition-verification.json) preserves parameters,
summaries, paired season PnL and action counts. Raw experimental outputs are
ignored under `out/`.

## Tune experiments

Score is half the sum of deep mean, thin mean and negative thin p10. Alternatives
below were evaluated only on seasons 451–525. A candidate must also increase
both means and keep thin p10 deterioration below 10%.

| Configuration | Deep mean | Thin mean | Thin p10 | Score | Decision |
|---|---:|---:|---:|---:|---|
| Original continuation baseline | 8,577.71 | 5,155.03 | -3,699.22 | 5,016.76 | Reference |
| Rebalance 8s | 8,750.12 | 5,248.63 | -5,054.77 | 4,471.99 | Reject: tail |
| Rebalance 4s | 8,697.50 | 5,165.18 | -6,184.07 | 3,839.30 | Reject: tail, 3 rate blocks |
| Rebalance 30s | 8,361.70 | 4,907.59 | -3,578.50 | 4,845.40 | Reject: means |
| Excess-edge ramp 1% | 6,642.45 | 4,070.32 | -3,962.63 | 3,375.07 | Reject: means |
| Excess-edge ramp 3% | 5,098.10 | 3,109.00 | -3,850.03 | 2,178.54 | Reject: means |
| Condition future wind strength | 8,514.08 | 5,380.58 | -6,813.63 | 3,540.52 | Reject: tail |
| Final exact, before report fix | 8,601.09 | 5,166.86 | -3,699.22 | 5,034.37 | Correct report defect first |
| Report fix alone | 8,591.87 | 5,145.04 | -3,712.89 | 5,012.01 | Correctness ablation |
| Report fix + final exact | 8,615.26 | 5,156.88 | -3,712.89 | 5,029.62 | Eligible |
| Plus 0.5% final entry only | 8,541.68 | 5,117.30 | -3,729.45 | 4,964.77 | Reject: means |
| Plus 1% final entry only | 8,606.25 | 5,153.69 | -3,715.47 | 5,022.23 | Reject: thin mean |
| Plus 0.5% entry / 1% full edge | 8,627.18 | 5,168.43 | -3,729.45 | 5,033.08 | Eligible |
| Plus 0.5% entry / 0.5% full edge | **8,643.98** | **5,176.69** | -3,729.45 | **5,045.61** | Selected and frozen |

At 2-second latency on tune, the frozen candidate still improves over the
report-corrected baseline: means 8,644.06 / 5,177.41 versus 8,591.95 / 5,145.76.
Thin p10 is -3,727.13 versus -3,709.41. Peak actions remain 42/47, with zero
blocks or rejections. This checks simulated order delay; it does not reproduce
HTTP timeouts, queue position or exchange load.

## Correctness and review

- Damage report reconciliation previously discarded excess damage at saturated
  sites and mishandled allocation when weather was missing. Four failing tests
  reproduced the errors. A training audit over 1,500 company/final reports went
  from 75 errors above 0.01 damage points to zero; maximum residual is 3.4e-11.
- An independent reviewer found three important issues. Regression tests first
  reproduced snapshot overconfidence, same-side equal-timestamp accounting
  ambiguity and experiment-output overwriting. One fix pass corrected them.
- Complete-weather and missing-weather tests cover the confidence gate. All
  450 historical weather grids across tune/verify are complete. A repeated
  verification after the fixes matches the frozen run's per-season results.
- The full suite has **88 passing tests**, including the real local HTTP
  integration checks from the efficiency patch. The actual backtest CLI default
  reproduces frozen season 451 PnL 11,408.14 and all 336 fills. The local preflight
  strategy check prints the same accepted configuration.
- A complete local mock replay at 25× reached all three rounds and submitted
  24 fills, each logged exactly once, with no HTTP/reconciliation errors. The
  first run exposed a missing mock trade-history route, now covered by a failing
  regression and fixed. The mock uses a flat spread and compressed wall time;
  its PnL is not a strategy-performance benchmark.
- Fill logging now uses our side, including passive sellers, and excludes
  unknown-side fills from slippage totals. Two failing regressions demonstrated
  the previous sign error from using the aggressor's side. This fixes the audit;
  it does not establish the cause of the exchange's realized-PnL discrepancy.
- The diagnostic recorder had overridden the round-open handler without
  preserving warm-up, so it profiled a different strategy. A failing behavioral
  test reproduced early orders. Restoring the parent handler makes season 451
  match the backtest's 11,408.14 instead of the erroneous 11,177 diagnostic result.
- Minor review item deferred: the experimental runner's verify argument guard
  still accepts a baseline plus an arbitrary named candidate. The actual frozen
  run used only `baseline,final_limit`; future work must follow the plan and avoid
  inspecting rejected candidates on verification data.

## Account reconciliation and next evidence

`scripts/audit_account.py` compares an independent average-cost replay with an
exchange position/PnL export. It accepts an optional opening snapshot, rejects
conflicting duplicate IDs and requires reliable order for equal-timestamp fills
when sides or prices differ. It never infers our side from an aggressor flag.

```bash
python3 scripts/audit_account.py --trades trades.json --positions positions.json \
  --opening opening.json --out account-audit.json
```

Supply every fill since the opening snapshot, with stable IDs, our buy/sell side,
quantity, price, timestamp with timezone, fees if present, and sequence numbers
where needed. Matching inventory alone cannot prove history is complete.
The previous simulated 323-fill accounting check matched positions and PnL
exactly. The documented 2–3k live discrepancy remains unresolved until the
requested actual recordings arrive.

A screening probe of seasons 451–462 in both regimes found zero rebalance
cycles with an ETF position opposed by a complete offsetting component basket.
Inventory-neutral creation/redemption therefore has no demonstrated opportunity
in that sample; no conversion strategy was enabled from this lead.

The branch has not been deployed and no remote orders were placed. Remaining
competition preparation is a supervised exchange-schema/execution check with
the actual recordings and testnet access. The earlier 1.71× forecast benchmark
is documented separately in [efficiency results](efficiency-results.md); its
numerical-parity claim applies to that patch, before this intentional valuation
and strategy change.

## Reproduction

Install `requirements-dev.txt` and unpack official history into `data/history`.
Use a fresh output directory for each experiment invocation; existing paths
are refused atomically and each run records its parameters in `invocation.json`.

```bash
python3 -m pytest -q
python3 scripts/experiment_execution.py --split verify --configs baseline,final_limit \
  --workers 4 --out out/verification-fresh
python3 scripts/experiment_execution.py --configs baseline,final_limit --latency 2 \
  --workers 2 --out out/latency-fresh
python3 scripts/backtest.py --strategy analog --seasons 451 --out out/cli-fresh
```

Runner `baseline` includes the report correctness fix. To reproduce the original
continuation reference, use `e8d4307` in a separate checkout. Re-running the
frozen candidate is a reproducibility check, not a new selection opportunity.
