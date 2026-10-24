# Completed capture 247: losses in the frozen evaluations

Competition ID `fd1ebff9-0f96-4533-b283-bc0a5c60cd4b`, fictional year 1780.
The ready settlement receipt is **2026-10-24 09:45:36.260472 UTC**.
These are virtual executions at 10% limits, not account profits or losses.
The actual clean completed practice receipt remains +$141.16.

## Complete results

| Frozen engine | Settings | Positive / negative | Mean terminal P&L | Worst |
| --- | ---: | ---: | ---: | ---: |
| Original fixed worker | 24 | 0 / 24 | −$690.90 | −$799.84 |
| Serialized core client | 16 | 2 / 14 | −$400.60 | −$738.46 |
| Full practice supervisor | 16 | 1 / 15 | −$332.11 | −$573.91 |

The original worker includes both current warm-up behavior and its reset
counterfactual, with delays 0.25/1/3 seconds. Core and supervisor use the fixed
grid RTT 0/0.05/0.25/1 second × full/half displayed depth × baskets off/on.
These request paths are different; their results are not interchangeable.

The supervisor completes four trials. Twelve stop before completing; nine end
flat and three require attention. The attention settings are zero RTT with
full depth/baskets off, half depth/baskets off and half depth/baskets on. Each
retains **REIN −6**, no open orders and no later fills. Their terminal marks are
−$403.97, −$522.38 and −$490.71. These are residual portfolios, not settled or
flat receipts. Every loss and incomplete outcome is retained.

### Fixed primary

The predeclared primary remains 0.25-second RTT, full depth, baskets on.
Core terminal P&L is **−$501.21**. The full supervisor observes −$269.88, stops
and closes flat at **−$239.99**, with 52 orders, 53 fills and no conversions.
Its lowest server mark is **−$315.83** and maximum marked drawdown **$544.345**.
The $250 observed-loss trigger is not a hard bound on interim or terminal loss.

## Chronology, inputs and training overlap

The original worker is frozen at `49a690efec04f7dcaf6a616de81da2838afbf149`,
serialized core at `505a5ad2d5a6f81e7c711cb550871ce7aa7f3734`, corrected runtime
at `cd3eb239bd7bad97b34f10a8f2bb0b2e1c0f5026` and comparison driver at
`c5c35a30e0c5f521f12324eec854f405b681b8c0`. Their existing protocols remain
unchanged. Capture 247 follows those freezes.

The sealed scan-003 observation prefix is 221,524 bytes, SHA-256
`9e98c0fe5b5a503dc6c6f1566b785572896c5e35ba0be8f8fcfae49dd273b195`.
The sealed feed is 50,016,422 bytes, SHA-256
`0df79451a59a031710d63271c1558f2711a7d28458b064ae4c4c0340877352f7`.
Both end at complete records and were checked against exact prefixes of the
live append-only sources before execution. The feed remains at the immutable
local attempt path in the retained spec; the closed cache is in the audit.

The selected stream contains 21,974 frames and all news sequences 0–871,
including three final reports. The opening quote gap is approximately 121.296
seconds, and a later REIN gap is 41.959 seconds. These are recorded receive-time
gaps, not proof that the exchange itself lacked liquidity. Replay freshness and
truncated-tail assumptions can help or hurt the simulated results.

Independent review after closure finds exact full-track matches to fitted
analog rows **738, 739 and 740** (zero-based): all 241 observations and all four
weather channels, with zero error. This makes 21 matching tracks across
captures 241–247. Chronological freezes do not establish unfamiliar-weather
validation. No future outcome for an active capture was used in this audit.

## Reproduction and retained evidence

All three comparison phases contain 16 rows, with zero errors, mismatches,
forbidden accesses or source changes. Reference and baseline match the frozen
serialized outputs before supervisor execution. Result SHA-256s:

| Phase | SHA-256 |
| --- | --- |
| Reference | `2b2ca30740a62348d7bae2c808351dd5371db51780bf6cec20a7e2cf6db402b6` |
| Core baseline | `a157463650ece2e52f2042600cbb26447f2e5e54f1c73ffa64a6549aa3e40381` |
| Supervised | `9f49c0207913893e2fa1ac1dd836e459f8604bcf42f1016d57507921109ff00a` |

Independent review verifies all **88 original rows**: 24 worker, 16 core and
three 16-run comparison phases. Eleven guarded reruns match every result field;
nine core/baseline/supervisor traces match their hashes. The complete archive
retains 208 files, including 112 original supervised journal files, closed
inputs, result bundles, replay traces and settlement reconciliations. SHA-256:
`8930064de48813f53025be67a6d0db6e00019e86631b36b6e176d38dc9329b93`.

`docs/evidence/observed-season-247/` binds that archive, audit JSON, spec,
observation prefix and both reviewed attempt-ledger prefixes with a six-artifact
manifest. The separate fixed-blend experiment is reported in
[repeat-blend.md](repeat-blend.md), including its failed supplemental check.
The frozen production strategy and forward evaluators remain unchanged.
