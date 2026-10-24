# Completed capture 245: fixed offline evaluations

**Later evidence, 08:53 UTC:** all 15 storm tracks in closed captures 241–245
exactly match the fitted analog training library. Source-freeze chronology
does not establish unseen-weather validation. Results below are retained;
see [training-overlap-audit.md](training-overlap-audit.md) for the limitation.

Competition ID `a7e77935-0ddd-4c77-8ce9-5494a9941962`, fictional year 1782.
The official ready receipt is **2026-10-24 08:07:30.818968 UTC**. All results
below are virtual executions on recorded data at 10% limits. No account orders
were placed by these evaluations.

## Results

| Evaluation | Settings | Terminal simulated P&L range | Negative settings |
| --- | ---: | ---: | ---: |
| Earlier activation-delay worker, all variants | 24 | −$44.04 to +$503.01 | 4 |
| Same worker, current snapshot behavior | 12 | +$138.89 to +$503.01 | 0 |
| Serialized core client | 16 | +$187.75 to +$692.51 | 0 |
| Corrected production practice supervisor | 16 | +$5.42 to +$692.51 | 0 |

The full supervisor completes **15 trials**. One trial hits the $250 loss
trigger and finishes flat after cleanup. No history stop or cleanup-attention
case occurs. These are 16 settings on one market path, not 16 independent
seasons. All original variants, including the four older-snapshot-behavior
losses, remain archived.

### Fixed primary setting

REST RTT 0.25 seconds, full displayed depth, baskets enabled; fixed in advance.

| Measure | Core client | Full supervisor |
| --- | ---: | ---: |
| Terminal simulated P&L | +$344.43 | +$362.85 |
| Orders | 35 | 41 |
| Fills | 28 | 34 |
| Conversions | 0 | 1 |
| Lowest server marked P&L | −$76.52 | −$77.60 |
| Maximum marked drawdown | $576.38 | $576.355 |

The supervised primary completes all three rounds and settles. Its final
account receipt mark is +$359.95; terminal valuation at the official settlement
prices is +$362.85. Receipt marks retain last captured midpoints and may differ
from settlement. The earlier activation-delay worker's comparable current-
behavior primary is +$370.39. Different engines have different scheduling and
execution assumptions; their differences do not isolate empirical latency.

### All core and supervised settings

Each group contains both depth fractions and both basket settings.

| Engine | RTT | Mean | Worst | Best | Supervised completed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Core | 0 | $585.455 | $505.65 | $692.51 | — |
| Core | 0.05 | $349.448 | $274.80 | $452.29 | — |
| Core | 0.25 | $260.995 | $204.11 | $344.43 | — |
| Core | 1 | $206.88 | $187.75 | $225.72 | — |
| Supervisor | 0 | $585.455 | $505.65 | $692.51 | 4 |
| Supervisor | 0.05 | $312.988 | $270.34 | $365.70 | 4 |
| Supervisor | 0.25 | $310.978 | $263.43 | $362.85 | 4 |
| Supervisor | 1 | $104.065 | $5.42 | $203.38 | 3 |

Across all 16 supervised settings, mean terminal P&L is +$328.37125. No
parameter or size change is selected from the highest-return setting.

### Early loss stop ending positive

At one-second RTT, full depth, baskets off, the sampled account snapshot at
replay time 2425.107219 seconds is −$260.585. It permanently triggers the stop
at 2429.607219, when the server mark has already recovered to −$226.135. Monitoring detects
the stop and cleanup starts at 2430; cleanup and final receipt finish at 2658.
The server's lowest mark is −$264.485. The final portfolio is flat, and both
receipt and terminal P&L are +$5.42. Only rounds 1 and 2 were final-reported to
the stopped client, so this is an incomplete trial despite its positive end.

A loss trigger does not fix the eventual cleanup P&L. Prices can move in either
direction while requests and liquidation execute. This case must not be
presented as a completed full-season success or as a guaranteed recovery.
The difference between the earlier sampled valuation and the six later closing
fills totals +$266.005. This includes the interval before cleanup started; it
is not a settlement uplift or solely a gain earned after cleanup began.

## Timing and evaluation status

| Event | UTC time on October 24 |
| --- | --- |
| Earlier worker actual startup, source `49a690e` | 06:11:57.592 |
| Serialized forward effective freeze, source `505a5ad` | 07:18:38 |
| First selected capture frame | 07:20:24.950635 |
| Corrected runtime freeze, source `cd3eb23` | 08:00:15 |
| Initial corrected-forward protocol declaration `f757d00` | 08:00:59 |
| Last selected frame | 08:07:30.233800 |
| Official ready receipt | 08:07:30.818968 |
| Separate forward driver freeze, source `c5c35a3` | 08:07:32 |

The selected interval starts 106.951 seconds after the serialized freeze. It is
a later recorded interval for that fixed client, with the coverage limits
below. It begins before the corrected-runtime freeze, and its receipt precedes
the separate driver freeze by **1.181032 seconds**. The initial protocol was
declared before the receipt. Do not label this capture prospective evidence
for the corrected supervisor or an untouched historical holdout.

The driver extends only the offline comparison workflow. Before execution it
checks runtime files against `cd3eb23` Git blobs and pins the core reference to
`505a5ad`. The original four-capture driver remains frozen separately. The new
driver and protocol were independently reviewed using a synthetic producer's
16 runs followed by all 48 phase runs, with external access blocked. All
**635 Python tests passed** before driver freeze and after integration with
the team's then-current main. Live strategy parameters and controls are unchanged.

## Recording and provenance

The selected input has **19,891 frames**, **18,933 quotes**, contiguous news
sequences **0–862**, and final reports at sequences **291, 578 and 862**. All
241 weather ages per round are present. There are 37 unusable quotes. The
observed opening-boundary quote gap is 121.441 seconds. Zero disconnect frames
were recorded; actual disconnect count and duration remain unknown. Full quote-
path coverage remains unproven. The final captured frame precedes the receipt by 0.585168
seconds; truncation can help or hurt P&L.

For the serialized core and three-phase comparison, both the observation prefix
and feed were copied and sealed before replay. The earlier activation-delay
worker consumed its original live recording paths.
Their exact byte counts and SHA-256 values are in the immutable input spec and
attempt ledger. Each copy was checked against the same prefix of its original
append-only file. The loader consumes the copies, so later appends cannot change
the recorded boundary. The selected feed copy remains local under the attempt
directory; its hash is preserved in the archived spec.

The new forward driver requires the upstream core results, summary, source and
input provenance to match before loading comparisons. All 16 reference runs
match the upstream outputs; all 16 baseline runs then match outputs and ordered
request/fill traces. Only after those gates pass are the 16 supervised settings
run. All phases completed without errors, mismatches or changed inputs/sources.
The ledger records starts before execution, completions, output hashes and all
phase logs. Future eligibility and the final cutoff are specified in
[supervised-forward-plan.md](supervised-forward-plan.md).

The original worker and core-client evidence passed independent audit: all
rows, source and artifact hashes, receipt and coverage checks, and four guarded
representative reruns matched. The original worker did not record a selected-
frame hash when it ran; reconstruction matching the core hash is supplemental
verification. Independent supervised-result and archive audit is complete:
all three phases and journals reconcile, five guarded representative reruns
match every result field and all seven files per run, and all 27 copied
artifacts, 112 journal files and 28 artifact hashes match. Runtime blobs, sealed
inputs, ledger timing and receipt/frame hashes were also checked.

[Evidence directory](evidence/season-245/) preserves the original worker,
serialized client, all three supervised comparison phases, input spec,
observation prefix, attempt-ledger prefixes, stdout/stderr logs, and all 112
files from the 16 supervised journals. The artifact manifest binds their bytes.

Fixed RTT, instantaneous CPU, displayed-liquidity fills, cash-neutral ETF
conversion accounting, last captured marks and omitted queue priority, own
market impact and extra fees remain simulation assumptions. A positive replay
does not establish live profitability or a probability of winning. The actual
owned practice record remains one verified completed season at +$141.16; the
shared-account conflict remains unresolved.
