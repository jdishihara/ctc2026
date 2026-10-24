# Cleanup refresh after an empty cancellation pass

**Decision: reject production promotion.** The candidate shortens average
cleanup, but violates two predeclared requirements: the worst loss grows and
one more setting finishes negative. Production and frozen forward evaluators
remain unchanged. The experiment is retained at `74c81f4` on
`arjun/cleanup-empty-cancel`.

## Change and protocol

The old cleanup loop refreshes and audits the account, attempts cancellation,
then repeats the refresh and audit. This experiment skips that second pair
only when the first snapshot has no open orders, has nonzero exposure, and
the market is running. Cancellation attempts, flat snapshots and closed
markets retain both refreshes. The per-order book → reconciliation → scope →
send-time checks are unchanged. The rejected quote-order change is excluded.

Plan `0643548` was committed before implementation or alternative performance.
The runtime and driver were committed at **08:49:22 UTC** as
`74c81f4d288f72e1248a6956ffcb15fea3970005`; both independent preflight reviews
passed before the baseline phase began. The baseline is frozen `cd3eb2`.

All 80 settings are retained: captures 241–245, RTT 0/0.05/0.25/1 second,
full/half displayed depth, basket off/on. Limits remain 10%, action rate
90/minute, observed-loss trigger $250 and prior P&L zero. The primary setting
is 0.25 second RTT/full depth/basket on. Strategy and model parameters are fixed.

These are correlated settings on five reused paths. All 15 weather tracks
also overlap the fitted model library, as established in
[training-overlap-audit.md](training-overlap-audit.md). This is an execution
diagnostic, not evidence of performance on unfamiliar storms or a win probability.

## Complete result

Baseline finished at **08:54:52 UTC**; candidate at **08:57:04 UTC**. All 80
baseline results and seven journals match their archives. All candidate
pre-cleanup request/fill hashes and stop fields match. Both phases have zero
errors, changed sources or forbidden accesses. All 68 completed-trial
supervisor results are unchanged.

| Measure, all 80 settings | Baseline | Candidate |
| --- | ---: | ---: |
| Positive / negative terminal P&L | 68 / 12 | 67 / 13 |
| Mean terminal P&L | $478.14 | $478.38 |
| Worst terminal P&L | −$420.64 | −$434.39 |
| Best terminal P&L | $2,236.76 | $2,236.76 |
| Completed / early-stopped trials | 68 / 12 | 68 / 12 |
| Cleanup settled / flat / attention | 68 / 10 / 2 | 68 / 10 / 2 |
| Mean cleanup duration, 12 early stops | 96.00 s | 89.67 s |

P&L improves in 2 settings, declines in 2 and is unchanged in 76. Cleanup is
faster in 7, slower in 1 and unchanged in 72. These counts are not independent
season probabilities. The $250 observed-loss trigger remains a trigger,
not a guaranteed maximum terminal loss.

### Every early stop

“Off and on” rows represent two settings with identical displayed outcomes.
All twelve individual rows are retained in `analysis.json` and the phase results.

| Capture | RTT | Depth | Basket | Settings | Terminal P&L before → after | Cleanup seconds before → after | Cleanup |
| --- | ---: | --- | --- | ---: | ---: | ---: | --- |
| 243 | 1 s | Full | On | 1 | −381.08 → −337.55 | 230 → 247 | Flat |
| 243 | 1 s | Half | Off | 1 | −391.47 → −369.76 | 260 → 235 | Flat |
| 243 | 1 s | Half | On | 1 | −420.64 → −434.39 | 238 → 236 | Flat |
| 244 | 0 s | Full | Off and on | 2 | −310.74 → −310.74 | 3 → 3 | Flat |
| 244 | 0 s | Half | Off and on | 2 | −277.86 → −277.86 | 5 → 5 | Attention |
| 244 | 0.25 s | Full | Off and on | 2 | −261.00 → −261.00 | 45 → 43.5 | Flat |
| 244 | 0.25 s | Half | Off and on | 2 | −303.34 → −303.34 | 45 → 43.5 | Flat |
| 245 | 1 s | Full | Off | 1 | +5.42 → −26.71 | 228 → 168 | Flat |

The two attention portfolios remain AQUA −8, GRID −5, REIN −20, with no
open orders. The primary terminal results are unchanged for every capture:
241 +$52.93; 242 +$1,497.40; 243 +$286.36; 244 −$261.00; 245 +$362.85.

Fewer requests do not guarantee a better fill. At one second RTT, book GET
to closing POST remains nine seconds. The candidate can change later passes,
acknowledgement refreshes and cancellation timing. In 243/half/off it adds
one cleanup DELETE even though it removes a redundant refresh on eligible
passes. In 243/full/on cleanup takes 17 seconds longer. In 245/full/off it
finishes 60 seconds faster but costs another $32.13. Empty replay books reflect
the model's recorded-quote freshness rule, not proof of absent live liquidity.

## Verification and retained evidence

- Two request-path tests failed before implementation. All 15 new tests and
  50 existing practice tests pass; full Python suite: **650 passed**.
- Independent preflight: **27 adversarial probes on each runtime** pass,
  covering exposure changes, cancellation uncertainty, final-send scope
  changes and retry exhaustion. The existing non-atomic account race remains.
- The comparison driver differs from audited `5832359` only in its header
  and plan-path manifest entry; all source, prerequisite and access guards
  are retained. Only `bot/practice.py` differs across 28 runtime files.
- Driver SHA-256: `b491e2753298c56013283697df02c0de0aa4422fc4f0ad3e06de32ba9fc052c3`.
- Runtime SHA-256: `6b6fc9c84be47fd6c04ecd912de24215c1a62c1595352c8017f127a04446b221`.

Independent output review verified all 80 pairs, all 1,280 journal/profile
hashes and 560 exact baseline journal matches. Twelve guarded reruns across
six representative settings reproduced every result field and all 96 files
exactly, including all four P&L changes, the new cancellation path, an unchanged
completed trial and residual attention. The complete analysis JSON also
reproduced exactly. No forbidden access occurred.

The evidence directory retains the
complete 80-pair analysis, analyzer, phase results/metadata/logs, all journals
and request profiles, and preflight/output review archives. The frozen experimental
branch retains the runtime and driver for reproduction. The fixed specification
references sealed inputs whose copies also remain in
`out/cleanup-quotes-v1-20261024/inputs/` locally.

The predeclared rule rejects this candidate despite its mean time and mean
P&L improvements. It does not replace the current production cleanup.
