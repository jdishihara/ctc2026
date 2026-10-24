# Closed capture 249 — independently verified execution diagnostics

All sixteen full-supervisor settings complete and settle positive. The fixed
primary returns **+$1,760.14** terminal settlement P&L; the range is
**+$1,014.34 to +$1,795.95**, with mean **+$1,485.76**. Independent
verification is complete. These are offline results on one captured market
path. No owned live trial ran; the negative capture-247 results remain part of
the record, and consistent live profitability has not been established.

All three full weather tracks match fitted-library rows 744–746 (zero-indexed)
exactly. There are now 27 matching storm tracks across captures 241–249.
Chronological source freezes do not make these unfamiliar-weather tests.

## Identity and chronology

Competition ID: `7d19a254-8c3b-4c4a-b4f3-32c84a138b79`; fictional year 1778.
The official ready/ready settlement receipt was recorded at
**11:23:46.284 UTC** on October 24. The selected feed interval is
10:36:43.060–11:23:44.083 UTC, after the original and bounded-retry source
freezes. Closure was verified before the replay inputs were selected.

The fifth sealed observation scan contains 302,691 bytes; the sealed feed
contains 66,111,365 bytes. Both are complete-line exact prefixes of the live
recordings. Selection reconstructs 22,930 frames and 862 contiguous news
messages, sequences 0–861. Final damage reports occur at sequences 283, 569
and 861. All original comparison phases have 16 rows, zero errors, zero
mismatches and no source changes.

| Evaluator | Frozen source | Settings | Mean | Worst | Best | Negative |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Original market worker | `49a690e` | 24 | $1,333.14 | $1,162.77 | $1,556.01 | 0 |
| Serialized production client | `505a5ad` | 16 | $1,345.69 | $1,144.23 | $1,711.86 | 0 |
| Full supervisor | runtime `cd3eb23`, driver `c5c35a3` | 16 | $1,485.76 | $1,014.34 | $1,795.95 | 0 |

The reference and baseline phases reproduce the serialized archive exactly.
The settings remain RTT 0/0.05/0.25/1 seconds, full/half displayed depth and
baskets off/on, at 10% position limits and the unchanged $250 sampled loss
trigger. Different evaluator grids and request timing can change profits in
either direction. These rows are not independent seasons or live account returns.

## Primary result and risk

The predeclared primary is 0.25-second RTT, full displayed depth, baskets on.
It completes all three storms with terminal settlement P&L of $1,760.14.
The contemporaneous final receipt mark is $1,755.61. Nine nonzero holdings are
valued at official settlement: **settled does not mean flat**.

The primary's lowest observed mark is −$50.47 and maximum marked drawdown is
$388.62. Across all sixteen settings, the lowest observed mark is −$105.425
and maximum drawdown is $416.535. No setting hits the loss trigger. The core
client's primary returns $1,244.04; the worker's primary with current snapshot
behavior returns $1,309.52. These timing differences are diagnostic, not a
counterfactual live profit claim.

## Independent verification

The audit checks all 88 worker, serialized, reference, baseline and supervised
rows, all 112 standard supervisor journal files and 91 source paths. Six fixed
reruns match every result field and trace: two serialized settings, three
supervised settings and one original worker setting. All 21 reproduced
supervisor journal files are byte-identical. There are zero forbidden-access
attempts and no additional performance variants.

The [222-file independent archive](evidence/observed-season-249/independent-review.tar.gz)
retains the original outputs, guarded reruns, source/input hashes and checks.
The [audit](evidence/observed-season-249/audit.json) and
[verification](evidence/observed-season-249/verification.json) distinguish the
complete original-output audit from the representative reproductions.

## Coverage and interpretation

The initial round-one snapshot precedes the first valid quotes by about
120.325 seconds. The largest later valid interquote interval is 58.935127
seconds for REIN in round one. Disconnect counts and complete quote-path
coverage remain unknown. Fixed latency, displayed depth and assumed fills omit
queue priority and own market impact. The $250 trigger samples observed losses;
it does not guarantee a maximum loss.

The unchanged merged cleanup retry is evaluated separately under its
[fixed declaration](cleanup-retry-forward-plan.md). This preserves the original
frozen evaluators. Results are reported in
[cleanup-retry-forward.md](cleanup-retry-forward.md).

The [artifact manifest](evidence/observed-season-249/artifact-manifest.json)
retains the independent review, original outputs, sealed scan, specification
and ledger prefixes. The raw feed remains at the
immutable local path recorded in the specification. No active-season published
outcomes were inspected.
