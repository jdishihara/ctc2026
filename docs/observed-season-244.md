# Completed capture 244: fixed offline evaluations

**Later evidence, 08:53 UTC:** all 15 storm tracks in closed captures 241–245
exactly match the fitted analog training library. Source-freeze chronology
does not establish unseen-weather validation. Results below are retained;
see [training-overlap-audit.md](training-overlap-audit.md) for the limitation.

Competition ID: `2cf67e88-9081-4258-aa6a-3648c41925de`, fictional year 1783.
The official closing receipt is `ready` at **2026-10-24 07:18:25.620 UTC**.
Neither evaluation below placed orders or establishes owned account profit.
Both use 10% position limits and fixed parameters.

## Results

| Evaluation | Scenarios | Simulated settlement P&L range | Negative scenarios |
| --- | ---: | ---: | ---: |
| Earlier frozen activation-delay worker, all variants | 24 | +$1,031.57 to +$1,215.88 | 0 |
| Same worker, current snapshot behavior | 12 | +$1,031.57 to +$1,189.38 | 0 |
| Sequential REST client, full fixed grid | 16 | +$533.32 to +$1,238.28 | 0 |

The sequential client's predeclared primary scenario (0.25-second REST RTT,
full displayed depth, baskets enabled) earns **+$628.14** in the virtual replay.
It sends 71 orders, receives 59 fills, and completes zero conversions. Its
lowest marked P&L is **−$263.29** and maximum peak-to-trough marked drawdown is
**$350.33**. A positive final result does not remove intraseason loss risk.

The core-client replay does not apply the practice supervisor's cumulative
loss stop or cleanup. The lowest virtual mark is below the earlier $250 loss
trigger. Whether and when the supervisor would stop depends on prior cumulative
P&L and the marks observed at its polls; subsequent cleanup fills would affect
the final outcome. The +$628.14 therefore cannot be treated
as the predicted result of a bounded supervised practice run.

The REST grid holds depth and basket choice fixed when comparing with zero RTT:

| REST RTT | Mean P&L | Worst | Best | Mean paired change vs zero RTT |
| --- | ---: | ---: | ---: | ---: |
| 0 s | $1,182.28 | $1,129.05 | $1,238.28 | $0.00 |
| 0.05 s | $1,039.73 | $888.13 | $1,230.41 | −$142.55 |
| 0.25 s | $578.79 | $533.32 | $628.14 | −$603.49 |
| 1 s | $595.17 | $565.81 | $621.61 | −$587.11 |

These are variants of one captured market, not independent trials. The two
engines differ in reconciliation, event timing, and execution assumptions;
their difference is not an isolated empirical measurement of network latency.
No settings are selected from the highest-return row.

## Timing and prospective status

| Event | UTC time on October 24 |
| --- | --- |
| Earlier worker's configured receipt-window start | 06:06:00 |
| Earlier worker's frozen source commit `49a690e` | 06:11:29 |
| Earlier worker's actual recorded start | 06:11:57.592 |
| First selected capture 244 frame | 06:31:19.566 |
| Last selected frame | 07:18:24.268 |
| Official ready receipt | 07:18:25.620 |
| Sequential forward plan/source effective freeze `505a5ad` | 07:18:38 |

The entire selected interval begins after the earlier worker's actual source
freeze and startup. This makes it a later recorded interval for that fixed
evaluation; it does not establish complete coverage of the true market path.

For the sequential-client plan, 244 is explicitly **predeclared carryover**.
Its receipt precedes the effective freeze by **12.380 seconds**. It is not
prospective evidence for that execution model. The plan was declared before
the outcome was inspected and retains this case regardless of the result.
Later eligibility and the final cutoff are specified in
[serialized-forward-plan.md](serialized-forward-plan.md).

## Input and recording limits

The selected input has 23,135 frames, 871 contiguous news sequence numbers
0–870, and all three final damage reports. It contains 22,169 quote frames,
including 43 unusable quotes. There are no recorded disconnect frames or
subscription acknowledgements; the recorder does not establish the number or
duration of actual disconnects.

The largest actual interquote gap is **44.783 seconds** (round 2, ISLE).
The **121.570-second** opening-boundary gap is a different statistic. Receive
gaps do not prove that server events were missing, but quote-path completeness
remains unproven. Serial matching ends **1.352 seconds** before the official
receipt; that truncation can help or hurt returns. Virtual fills still omit
queue priority, own market impact, and additional fees, and assume instantaneous
strategy CPU and midpoint cash-neutral conversion execution.

## Provenance and verification

All evidence is archived under [evidence/season-244](evidence/season-244).
The earlier artifact includes source and receipt hashes but did not record a
selected-frame hash when it ran. Any reconstructed input fingerprint is a
supplemental audit result, not an original worker guarantee.

The serial attempt ledger was written before CLI validation. It records the
exact 100,304-byte complete-line observation prefix, the receipt identity/hash,
start and completion, logs, and five output hashes. The original receipt was
validated as closed before replay. All 28 source/model/plan hashes match the
frozen checkout, including the formerly omitted control module.

Independent serial review verified all 16 rows, aggregates, paired comparisons,
position caps, source and artifact hashes, and the observation prefix. Four
representative reruns matched every output field, including the primary case.
Networking, credentials, and downloaded-history reads were denied; none were
attempted. Independent verification of the earlier 24-scenario artifact is
also complete: all rows, 23 source/model hashes, artifact/receipt/manifest
hashes, and coverage matched. Four representative replays matched every stored
field, including the current worst/best and the older-behavior maximum. Invalid
receipts, identity, prices, and incomplete history were rejected; guarded runs
attempted no external access or frozen-checkout writes.

Supplemental input fingerprints reconstructed during that review:

- Selected frames:
  `ff76815be619b2b62310dcf77dce868ea31d80fbbe7e41137c64083c73401b20`.
  This matches the serial run's recorded selected-frame hash.
- Receipt-bounded raw feed window:
  `9d8ec864273d7186c7a861a87f466b45afc07a424659ad8cd56685f3444e7c21`.

No strategy, size, or live-control change follows from this report.
