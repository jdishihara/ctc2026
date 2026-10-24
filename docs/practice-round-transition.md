# Practice round-transition correction — 2026-10-24

## Finding and change

The [first full supervisor replay](supervised-client-replay.md) exposed a real
control-flow defect: a valid next storm formation can arrive before its initial
weather observation. Model readiness correctly becomes false during that wait,
but the practice supervisor treated that temporary state as lost history and
permanently stopped an already attempted trial. Independent replay attributed
all 40 history stops in the original comparison to valid round transitions.

The correction records an accepted contiguous transition from a fully reported
round to round 2 or 3. Waiting is bound to the model object, agreeing known
account/news competition and year, and expected round. News and outage history
must remain complete; final reports must exactly match the completed prefix.
Submissions remain blocked until valid initial weather restores readiness.
Resting-order cancellation, ownership, quote freshness, pending-news, warm-up,
position limits and the loss trigger remain in force.

Checks now also run at each news-event boundary. Invalid new-sequence duplicate,
restarted or skipped formation permanently stops the journal even if later
weather in the same callback would otherwise conceal it. Ignored stale or
retransmitted messages preserve a legitimate wait. The narrow exception does
not overhaul general model validation of malformed reports.

## Frozen comparison and verification

- Runtime and comparison source: `cd3eb239bd7bad97b34f10a8f2bb0b2e1c0f5026`,
  frozen **08:00:15 UTC**, clean before and after execution.
- Plan: [practice-round-transition-plan.md](practice-round-transition-plan.md),
  declared before corrected performance was run. Strategy parameters, 10%
  limits, 90 actions/minute, zero prior P&L and the $250 trigger are unchanged.
- Tests reproduced 12 failures in the initial 23 cases before the main fix;
  five further regressions reproduced the review findings before hardening.
  All **607 Python tests passed** before freeze, including 28 new cases.
  Independent review passed 133 focused tests and a full 732-message synthetic
  season, including additional rollover, stale-message and report probes.
- Reused the already verified 64 reference rows from frozen source `505a5ad`.
  All **64 new baseline rows exactly match archived outputs and ordered
  request/fill traces**. Their result file is byte-identical to the prior
  baseline. Only then were all 64 corrected supervised settings run.
- Both phases completed with zero diagnostic errors, mismatches or changed
  source files. The corrected supervised phase finished **08:03:24 UTC**.
  Independent result and artifact audit is complete: all rows and tables,
  65 unique manifest paths against frozen Git blobs, ten copied artifacts,
  448 archived journal files and all 11 artifact hashes were verified.
  Twelve representative reruns matched every result field and all seven files
  per run with network, credential and downloaded-history access blocked;
  settlement access remained fenced to the recorded closed receipt.

These are reused captures 241–244, not four new untouched seasons. The 16
settings per path stress RTT 0/0.05/0.25/1 seconds, full/half displayed depth,
and baskets off/on. Sixty-four settings do not constitute 64 independent trials.

## Results

| Measure | Original supervisor | Corrected supervisor |
| --- | ---: | ---: |
| Completed full-season trials | 16 / 64 | 53 / 64 |
| History stops | 40 | 0 |
| Loss stops | 8 | 11 |
| Positive terminal outcomes | 40 | 52 |
| Negative terminal outcomes | 24 | 12 |
| Mean terminal simulated P&L | +$423.41 | +$515.58 |
| Worst terminal simulated P&L | −$310.74 | −$420.64 |
| Best terminal simulated P&L | +$1,479.88 | +$2,236.76 |
| Cleanup marked attention | 6 | 2 |

Correcting a false early stop allows later gains and losses to occur. Three
new loss stops arise in capture 243 at one-second RTT. The worst outcome is
therefore worse after the correctness fix. One additional losing scenario
completes the full season at −$226.31. Consistent profitability remains unproven.
Across all settings, 28 terminal results improve, 12 decline and 24 complete
result rows are unchanged.

### Fixed primary setting

RTT 0.25 seconds, full displayed depth, baskets enabled; selected before these
outcomes. Values are simulated terminal P&L at official settlement prices.

| Capture | Original supervisor | Corrected supervisor | Final receipt mark | Outcome |
| --- | ---: | ---: | ---: | --- |
| 241 | −$56.64 | +$52.93 | +$57.04 | Completed, settled |
| 242 | +$810.03 | +$1,497.40 | +$1,492.345 | Completed, settled |
| 243 | +$286.36 | +$286.36 | +$279.335 | Completed, settled |
| 244 | −$261.00 | −$261.00 | −$261.00 | Loss stop, flat |

Receipt marks use the replay's last captured midpoints; they can differ from
official settlement valuations. The capture-244 primary stop and cleanup are
unchanged. No additional owned live trial was run; the verified actual record
remains one completed small-size season at +$141.16 and a later mixed-account
trial that cannot be attributed to this strategy.

### All stress groups

Each row contains all four depth/basket settings. All P&L is simulated terminal
P&L at official settlement prices, in dollars.

| Capture | RTT seconds | Mean | Worst | Best | Negative | Completed | Loss stops |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 241 | 0 | 96.24 | 70.13 | 131.61 | 0 | 4 | 0 |
| 241 | 0.05 | 43.47 | 26.22 | 62.68 | 0 | 4 | 0 |
| 241 | 0.25 | 47.44 | 39.25 | 55.73 | 0 | 4 | 0 |
| 241 | 1 | 147.12 | 127.30 | 157.85 | 0 | 4 | 0 |
| 242 | 0 | 2191.01 | 2152.92 | 2236.76 | 0 | 4 | 0 |
| 242 | 0.05 | 1541.33 | 1513.47 | 1577.09 | 0 | 4 | 0 |
| 242 | 0.25 | 1475.33 | 1450.06 | 1497.40 | 0 | 4 | 0 |
| 242 | 1 | 1350.86 | 1249.28 | 1479.88 | 0 | 4 | 0 |
| 243 | 0 | 501.99 | 409.39 | 597.15 | 0 | 4 | 0 |
| 243 | 0.05 | 188.21 | 116.82 | 260.35 | 0 | 4 | 0 |
| 243 | 0.25 | 250.75 | 215.14 | 286.36 | 0 | 4 | 0 |
| 243 | 1 | −354.88 | −420.64 | −226.31 | 4 | 1 | 3 |
| 244 | 0 | −294.30 | −310.74 | −277.86 | 4 | 0 | 4 |
| 244 | 0.05 | 839.81 | 688.56 | 964.13 | 0 | 4 | 0 |
| 244 | 0.25 | −282.17 | −303.34 | −261.00 | 4 | 0 | 4 |
| 244 | 1 | 507.10 | 477.91 | 559.01 | 0 | 4 | 0 |

### Loss and cleanup details

The three new capture-243 loss stops all have one-second RTT. Times below are
seconds on the replay clock; completion includes the final receipt requests.

| Depth | Baskets | Trigger snapshot P&L | Stop time | Cleanup start | Cleanup complete | Terminal P&L |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Full | On | −272.39 | 2297.994 | 2298 | 2528 | −381.08 |
| Half | Off | −255.10 | 2431.948 | 2432 | 2692 | −391.47 |
| Half | On | −276.92 | 2277.703 | 2278 | 2516 | −420.64 |

The trigger is an instruction to stop and reconcile, not a guaranteed maximum
loss. Observations and requests take time, and closing positions incurs costs.
The eight capture-244 loss stops remain in the complete result files.
The completed capture-243/full-depth/baskets-off run at one-second RTT has a
server marked low of −$306.685 but finishes at −$226.31 without a loss stop.
The supervisor acts on sampled account observations; an unsampled server low
does not itself demonstrate that a stop condition was observed. Its minimum
sampled P&L was −$234.785.

Cleanup totals are **53 settled, nine flat, two attention**. Both attention
cases are capture 244, zero RTT, half depth, with baskets off/on. Each retains
AQUA −8, GRID −5 and REIN −20; all other quantities are zero. Each final receipt
mark is −$256.095, while terminal settlement P&L is −$277.86. Preserve this
residual exposure explicitly; these cases did not finish flat.

## Artifacts and limits

[Evidence directory](evidence/practice-round-transition/) contains both phases'
metadata, results and completion summaries, all four stdout/stderr logs, and
`supervised-journals.tar.gz` with all 448 files from the 64 supervised runs.
`artifact-manifest.json` binds their SHA-256 values. The copied files and journal
members were byte-checked against original outputs. The original reference and
first supervisor artifacts remain in [supervised-client](evidence/supervised-client/).

Baseline result SHA-256:
`8c05ff9ab2f42c6a7f8aa144f043ccbb6b99f80038e8a8d4a6136fbb00b741af`.
Corrected supervised result SHA-256:
`985fdb64e556a0c2caad2f947149e09c5c5b0adceb911f5420b034735035e0bf`.

The existing replay assumptions still apply: fixed request RTT and midpoint
execution, instantaneous CPU computation, captured displayed liquidity,
cash-neutral ETF conversion accounting, last captured marks after close, and
omitted queue priority, own impact and extra fees. Capture gaps remain. This
comparison isolates the code correction within that simulator; it does not
establish the exact counterfactual live batch P&L or competition readiness.
