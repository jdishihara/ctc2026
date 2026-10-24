# Completed capture 246: fixed offline evaluations

Competition ID `83fc18b9-e9fd-4634-bc8e-c7a1a77768a7`, fictional year 1781.
The official ready receipt is **2026-10-24 08:56:43.484856 UTC**. All results
below are virtual executions at 10% limits. This evaluation sent no account
orders and does not add to the actual +$141.16 completed practice receipt.

## Results

The full frozen supervisor completes all three storms in all 16 execution
settings and every setting finishes positive. None hits the loss trigger,
history stop or cleanup attention state. Independent output review passed.

| Frozen engine / settings | Positive | Mean terminal P&L | Worst | Best |
| --- | ---: | ---: | ---: | ---: |
| Original fixed worker, all 24 | 24 / 24 | $1,599.47 | $1,172.78 | $1,848.21 |
| Original worker, current warm-up behavior only | 12 / 12 | $1,731.66 | $1,471.29 | $1,848.21 |
| Serialized core client, 16 | 16 / 16 | $1,568.38 | $1,155.06 | $1,937.04 |
| Full practice supervisor, 16 | 16 / 16 | $1,678.09 | $1,439.61 | $1,937.04 |

These engines model different request paths; their results are not interchangeable.
The original worker includes a warm-up-reset counterfactual and delays
0.25/1/3 seconds. Serialized core and full supervisor use RTT
0/0.05/0.25/1 second, full/half displayed depth and basket off/on.

### Fixed primary setting

Primary remains **0.25 second RTT/full depth/basket on** (0.25 second order
delay in the original worker), with current warm-up behavior.

| Measure | Original worker | Serialized core | Full supervisor |
| --- | ---: | ---: | ---: |
| Terminal settlement P&L | $1,848.21 | $1,393.60 | $1,539.17 |
| Orders / fills / conversions | 113 / 89 / 4 | 86 / 63 / 1 | 71 / 55 / 0 |
| Lowest marked P&L | −$40.00 | −$115.36 | −$30.27 |

The full-supervisor primary reports all final rounds `[1, 2, 3]`, zero open
orders, verified account identity/history, and settled holdings. Its final
account mark is **$1,524.28**; marking the virtual cash/positions to the official
settlement prices gives **$1,539.17**. Settled positions are not reported as flat.
Maximum marked drawdown is **$263.99**, distinct from the minimum P&L of −$30.27.

### Core and supervisor by RTT

Each row contains all four depth/basket settings. Variation is descriptive;
this does not select a preferred delay after observing the outcome.

| RTT | Core mean | Core range | Supervisor mean | Supervisor range |
| --- | ---: | ---: | ---: | ---: |
| 0 s | $1,901.57 | $1,873.38–$1,937.04 | $1,901.57 | $1,873.38–$1,937.04 |
| 0.05 s | $1,625.31 | $1,548.60–$1,714.43 | $1,602.97 | $1,512.02–$1,707.96 |
| 0.25 s | $1,458.75 | $1,363.80–$1,546.30 | $1,523.90 | $1,490.04–$1,545.73 |
| 1 s | $1,287.89 | $1,155.06–$1,381.96 | $1,683.92 | $1,439.61–$1,834.52 |

## Timing, training overlap and coverage

The selected recorded interval is **08:09:30.028088–08:56:33.677256 UTC**.
It starts after the serialized source freeze at 07:18:38, corrected runtime
freeze at 08:00:15, and supervisor driver freeze at 08:07:32 UTC.
This establishes chronological ordering only. Independent review confirms all
three capture-246 weather tracks exactly match unique fitted-library rows
735–737 (zero-based), at every one of 241 ages and all four weather channels:
2,892 scalar values, zero error. Captures 241–245 also overlap training.
Do not describe these results as unseen-weather validation.
See [training-overlap-audit.md](training-overlap-audit.md).

The selected stream contains **22,748 frames**, including **21,790 quotes**
and **863 contiguous news messages**, sequences 0–862, with all three final
reports. Coverage validation identifies **44 unusable quotes**. There are
zero recorded disconnect frames, but actual disconnect count and quote-path
completeness remain unknown.

The opening quote gap reaches **121.498 seconds**. The largest later within-round
gap is **64.736 seconds** for GEN in round 2. These observed receive-time gaps
are not proof of a server outage or absent exchange liquidity. The selected
stream ends **9.807600 seconds** before the official receipt; replay tail
truncation can help or hurt results and is not a conservative lower bound.

Before execution, observation scan 002 and the feed were copied into immutable
attempt inputs, required to end with complete newline-delimited records, and
verified as exact prefixes of the live append-only sources. Their receipt,
byte counts and SHA-256 hashes are recorded in the attempt ledger and spec.

## Frozen source and complete execution

- Original worker: `49a690efec04f7dcaf6a616de81da2838afbf149`.
- Serialized core: `505a5ad2d5a6f81e7c711cb550871ce7aa7f3734`.
- Full runtime: `cd3eb239bd7bad97b34f10a8f2bb0b2e1c0f5026`.
- Separate comparison driver: `c5c35a30e0c5f521f12324eec854f405b681b8c0`.

The three comparison phases each contain all 16 settings, with zero errors,
mismatches or source changes. Reference and core baseline reproduce the frozen
serialized outputs before the full supervisor runs. Phase result SHA-256s:

| Phase | SHA-256 |
| --- | --- |
| Reference | `26b267e0183a447251400d7a28537959d81fcdea235cfd29d8e24561073a9dc6` |
| Core baseline | `5018086013f145ceec1813ab69d954d1d7fde926c9f2d33abe3a7954c8273af7` |
| Supervised | `60960b091422ac4cbfcc4e9c88f60d561e6ecf095a215405de11818436e591cb` |

Full supervised comparison finished at **09:01:22 UTC**. Completion and the
subsequent independent review are recorded in the append-only attempt ledger.

## Evidence and limitations

The evidence directory retains all engine results, metadata and logs, the
sealed observation prefix, input spec, ledger prefixes and all 112 supervised
journal files. The sealed 42,629,330-byte feed remains at the local attempt path
recorded in the spec. Its SHA-256 is
`f5215abcb9756823c4916c060127d2bf7e520a4dad5fe88662a89647120f9ae6`.

Independent review verified all 24 original outputs, 16 core outputs and all
three 16-run comparison-phase gates, including source/input/receipt hashes and
chronology. Six guarded reruns reproduced every archived result field: original
primary and 3-second/half-depth/basket-on/current-warm-up settings; core and
supervisor primary and 1-second/half-depth/basket-on settings. Core/supervisor
trace hashes match, and both supervised reruns reproduce all seven journal
files byte-for-byte. All sixteen supervised settlement scores independently
reconcile from the recorded cash and holdings. No forbidden access, guard
violation or source change occurred.

The retained independent-review archive contains 57 verified files, SHA-256
`ec707deeccad278ef0411cb4e2ba0694fbc2fc6e629a85f7fef94fa3447bfe23`.
The artifact manifest binds all packaged evidence. Positive
results across settings on one path do not establish independent season
success probabilities, real account profitability, or competition readiness.
The frozen evaluators and production strategy remain unchanged.
