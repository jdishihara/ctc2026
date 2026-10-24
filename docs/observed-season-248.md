# Closed capture 248 — independently verified execution diagnostics

All sixteen full-supervisor settings complete and settle positive. The fixed
primary returns **+$985.54** terminal settlement P&L; the range is **+$295.45
to +$1,224.03**, with mean **+$897.99**. These are offline results on one
captured market path. No owned live trial ran, and they do not replace the
earlier negative capture-247 outcomes or establish consistent profitability.

All three complete weather tracks exactly match fitted-library rows 741–743
(zero-indexed). This brings the verified overlap to 24 storm tracks across
captures 241–248. The result does not establish unfamiliar-weather performance.

## Identity, closure and source chronology

Competition ID: `789097b1-a48b-4e68-95b4-5e15b047e149`; fictional year 1779.
The valid official ready/ready settlement receipt was recorded at
**10:34:46.327 UTC** on October 24. The selected feed interval is
09:47:38.558–10:34:42.529 UTC, after the original runtime and driver freezes.
The official close was verified before selecting outcomes or running replays.

The fourth sealed observation scan is 262,975 bytes. The sealed feed prefix is
58,421,744 bytes, and both are complete-line exact prefixes of the original
recordings. Selection reconstructs 25,213 frames, news sequences 0–864 and
three final damage reports. All reference, baseline and supervised phases have
16 rows, zero errors, zero mismatches and no source changes.

| Evaluator | Frozen source | Settings | Mean | Worst | Best | Negative |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Original market worker | `49a690e` | 24 | $965.54 | $919.12 | $1,050.83 | 0 |
| Serialized production client | `505a5ad` | 16 | $964.05 | $493.54 | $1,224.03 | 0 |
| Full supervisor | runtime `cd3eb23`, driver `c5c35a3` | 16 | $897.99 | $295.45 | $1,224.03 | 0 |

The reference and baseline phases reproduce the serialized archive exactly.
All evaluators retain their predeclared parameters. Their grids and execution
models differ, so their rows are not independent seasons or interchangeable
estimates of live returns. The full-supervisor grid uses RTT 0/0.05/0.25/1 s,
full/half displayed depth and baskets off/on, at 10% limits and the unchanged
$250 sampled loss trigger.

## Primary result and risk

The primary is 0.25-second RTT, full displayed depth, baskets enabled. It
completes all three storms with a settled receipt. Its terminal P&L is $985.54;
the contemporaneous final account mark is $986.42. Seven nonzero holdings are
valued at official settlement, so this is **settled, not flat**.

The primary's lowest observed mark is −$1.30 and its maximum marked drawdown is
$289.32. Across all sixteen settings, the lowest observed mark is −$138.80
and the maximum marked drawdown is $367.48. No setting hits the loss trigger.
The modeled core-client primary earns $997.15; the original market-worker
primary with current snapshot behavior earns $1,039.24. Supervisor requests
and execution timing affect the comparison; none is an actual account receipt.

## Independent verification

The audit checks all 88 original worker/client/comparison rows, all 112 standard
supervised journal files, source hashes, sealed input identities, official
closure and eligibility. Six authorized reruns reproduce every original result
field: two serialized settings, three supervised settings and one original
worker setting. All five client request/fill hashes match; all 21 reproduced
supervisor journal files are byte-identical. No additional policy setting was
tested and no active-season outcome was inspected.

The [203-file independent archive](evidence/observed-season-248/independent-review.tar.gz)
retains the audit, exact source/input hashes, all results and full rerun traces.
The [verification](evidence/observed-season-248/verification.json) records every
rerun and the settlement-access guards. A proofreading change briefly broke
an identifier in the verification script during packaging; it was corrected
before the final archive. The prior package, receipt and packaging note are
retained, and no performance evaluation was repeated for that correction.

## Limits and separate retry comparison

The first valid quotes arrive about 120.318 seconds after the initial snapshot.
The largest later valid-quote interval is 52.438055 seconds for RECON in round
three. One subscription acknowledgement is recorded; the disconnect count and
quote-path completeness remain unknown. Fixed latency, replayed depth and
assumed fills omit queue priority and own market impact.

The merged cleanup retry was evaluated separately under a plan declared before
this capture closed. It leaves all sixteen outcomes unchanged and needs no
extra cleanup passes here. That follow-up preserves the original frozen
evaluators and is documented in [cleanup-retry-forward.md](cleanup-retry-forward.md).

The [artifact manifest](evidence/observed-season-248/artifact-manifest.json)
hashes the retained review packages, verification, scan, specification and both
ledger prefixes through independent review. The complete raw feed remains at
its immutable local path recorded in the specification.
