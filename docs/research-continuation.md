# Competitive strategy research — 2026-10-23

This continuation tests independent sources of PnL beyond the accepted
`aa51985` strategy. Selection uses seasons 451–525; models use only 1–450.
Seasons 526–600 have been inspected in earlier work and are **reused
confirmation data**, not an untouched holdout. No remote orders were placed.

## Basket overlay: frozen tune candidate

The overlay trades a discrepancy between an ETF and its component basket.
It cancels participating orders, captures reconciled starting positions,
creates/redeems at most 10 ETF units, and submits closing legs. Partial fills
trigger cancellation and restoration after 10s with a 2% crossing cap. It
suspends new fundamental orders until inventory is restored and no
participating orders remain. Fresh quotes, known round timing, temporary
inventory capacity and action headroom are required.

The [official packet](https://docs.google.com/document/d/1XnZGvu3qPCc0abJYtkax9IyHVbx-LvUH6s1k8Y9j3Ps/edit)
specifies immediate, fee-free ETF creation/redemption subject to position
limits. Individual closing trades are separate orders; their execution is the
main uncertainty in this strategy.

| Tune configuration | Deep mean | Thin mean | Thin p10 | Score | Decision |
|---|---:|---:|---:|---:|---|
| Accepted baseline | 8643.98 | 5176.69 | -3729.45 | 5045.61 | Reference |
| 0.5% basket edge | 9270.13 | 5709.93 | -4291.16 | 5344.45 | Reject: tail |
| 1.0% basket edge | 9215.25 | 5736.06 | -3054.46 | 5948.43 | Frozen |

The 1% candidate increases tune means 6.6% / 10.8% and improves thin p10 by
674.99. Peak actions are 62/69 per minute at a 120 cap; no blocks/rejections.
Average cycles are 8.17/8.47 per season, with 17/192 timeout restorations across
75 seasons. Selection was committed at `ae41076` before confirmation.

Confirmation and stress results are recorded below when the frozen runs finish.
Launch defaults remain unchanged until those gates and code review are complete.

## Rejected price timing

The packet describes slow house-price adjustment. A per-symbol/per-phase ridge
model predicts 120s public-price returns from lagged returns at 2/10/30/60/120s.
Horizon selection used 1–300 fitting and 301–450 validation, then refit on all
1–450. Features use only prices available at or before each lag. The artifact
records input and fitting-script hashes. Internal validation correlation is
0.271; directional accuracy for signals above 0.5% is 65.4%. Samples overlap,
and these metrics exclude trading costs.

| Tune configuration | Deep mean | Thin mean | Thin p10 | Score |
|---|---:|---:|---:|---:|
| Accepted baseline | 8643.98 | 5176.69 | -3729.45 | 5045.61 |
| Gate adverse drift at 0.5% | 8750.20 | 5378.12 | -3595.89 | 5266.22 |
| Gate adverse drift at 1.0% | 8811.26 | 5358.49 | -3694.88 | 5237.44 |
| Add predicted drift to fair | 8838.25 | 5306.73 | -5661.16 | 4241.91 |

The 0.5% gate was frozen at `1e246c2`. Confirmation means fell from
9452.36/5993.53 to 9277.55/5968.32, so it was rejected. Thin p10 improved
from -2712.92 to -1969.59; that does not override the predeclared mean gates.
Paired mean changes were -174.82/-25.20, with bootstrap 95% intervals
[-474.58,68.66]/[-262.01,188.68]. The data do not establish that the filter
is worse in all settings; they fail the required evidence for promotion.

At 2s latency on tune, means were 8750.25/5378.12 versus 8644.06/5177.41.
At severe tune liquidity (60s refill, quarter depth), mean was 1978.33 versus
1671.82 and p10 -5713.94 versus -7692.26. These stress improvements do not
rescue the failed confirmation means. No other price candidate was inspected
on confirmation. `price_gate` and `price_drift` remain zero by default.

Optional price timing was also hardened against reconnects without a valid
round clock and stale individual symbols hidden by other quote traffic.

## Rejected forecast changes

All internal forecast screens use an analog library built only from 1–300
and validation seasons 301–450, at ages 30/90/150/240/360. The primary gate is
at least 5% lower 120s position RMSE with no higher damage RMSE. Damage-model
parameters were previously fitted on 1–450, so damage error is a shared
secondary screen, not independent validation of those parameters.

| Internal forecast | 120s position RMSE | Damage RMSE | Decision |
|---|---:|---:|---|
| Equal weighting | 96.809 | 7.3025 | Reference |
| Position-error half-life 60s | 92.007 | 7.3207 | Reject |
| Half-life 120s | 95.087 | 7.3133 | Reject |
| Half-life 240s | 98.029 | 7.3081 | Reject |
| Center paths 50% toward cone | 86.951 | 7.2202 | Evaluate PnL |
| Center paths 100% toward cone | 82.307 | 7.2140 | Evaluate PnL |

Cone centering translates all selected future paths equally at official cone
points, preserving dispersion and strength paths. It fades back to the
unmodified paths over 60s after the final future cone point. The production
and independent research implementations agree exactly across all 20,250
internal squared-error comparisons.

Both fractions failed tune PnL gates: 50% centering gives means
8648.26/5153.31 and thin p10 -4400.78; 100% gives 8607.39/5110.89 and
-4579.51. Neither was inspected on confirmation. `cone_center` stays zero.

A separate training-only radial damage-kernel probe lowered PORT internal
RMSE from 5.81 to about 5.42 points. That single-company improvement did not
justify replacing the five-company physical model; no runtime change was made.

## Why the basket probe needed a coordinated test

An initial price screen on 1–300 found absolute ETF/basket-mid differences
above 0.5% in 14.8% of ARCH observations and 6.8% of REBLD observations.
Midpoint gaps are not executable profits.

A fixed basket-only probe on 301–450 earned mean 1144.89, p10 751.98 and
minimum 448.02 under deep liquidity, with no losing seasons. At quarter depth,
60s refill and 3s latency, mean fell to 127.73, p10 -23.41 and minimum -178.22;
22/150 seasons lost and there were 3689 timeout retries. The probe uses
unbounded market orders for timeout exits and is **offline research only**.
The coordinated implementation uses bounded exits and competes with the
fundamental strategy for capacity; standalone profits are not added to it.

## Reproduction

Use a fresh output directory for every run. Full strategy parameters, source
revision and dirty-tree status are recorded by each experiment invocation.

```bash
python scripts/fit_price_signal.py --train-end 300 --eval-end 450 --out out/price-internal-new.json
python scripts/fit_price_signal.py --out out/price-fit-new.json
python scripts/experiment_price_timing.py --out out/price-tune-new
python scripts/experiment_price_timing.py --split verify --configs baseline,timing05 --out out/price-verify-new
python scripts/research_recency.py --out out/recency-new
python scripts/research_recency.py --method cone-center --out out/cone-internal-new
python scripts/research_recency.py --method cone-center --production --out out/cone-production-new
python scripts/experiment_cone_center.py --out out/cone-tune-new
python scripts/research_basket.py --out out/basket-internal-new
python scripts/experiment_basket.py --out out/basket-tune-new
python scripts/experiment_basket.py --split verify --configs baseline,basket10 --out out/basket-verify-new
python scripts/experiment_basket.py --configs baseline,basket10 --latency 3 --out out/basket-latency-new
python scripts/experiment_basket.py --configs baseline,basket10 --regimes severe --latency 3 --out out/basket-severe-new
python -m pytest -q
```

The existing account audit still needs actual testnet fill and position exports
to resolve the documented 2–3k PnL discrepancy. A localhost conversion test
cannot establish live exchange accounting or execution quality. No historical
simulation can prove that a strategy is unbeatable by other teams.
