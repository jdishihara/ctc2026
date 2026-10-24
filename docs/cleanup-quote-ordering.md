# Cleanup quote ordering

This diagnostic evaluates a change to emergency cleanup execution. Trading signals,
parameters, exposure limits and the observed-loss trigger stay fixed.

**Decision: reject production promotion.** The proposed quote ordering reduced
quote age but did not consistently reduce cleanup time or loss. The production
runtime remains unchanged. The experimental implementation and driver remain
available at frozen commit `5832359` on `arjun/cleanup-latency`.

## Why investigate

Two guarded reproductions of the reviewed supervisor found that HTTP requests
accounted for almost all cleanup time at one second RTT:

| Archived setting | Elapsed cleanup | Requests | Time in requests | Closing orders | Book age at execution |
| --- | ---: | ---: | ---: | ---: | ---: |
| 243 / 1 s / half depth / basket on | 238 s | 236 | 236 s | 9 | 9 s each |
| 245 / 1 s / full depth / basket off | 228 s | 223 | 223 s | 6 | 9 s each |

Here, book age means the interval from orderbook-GET execution to closing-POST
execution. The underlying captured market quote can already be older when the
GET samples it. These elapsed times include final account receipt collection. The profilers
reproduced every archived result field and all seven journal files exactly.
They recorded request call sites separately, without changing server request
records, and blocked network, credentials, downloaded history and early
settlement-value access. Times are simulated, not measured live latency.

The old loop chose a book before a four-request account refresh and two
two-request ownership checks. Including the closing POST, the price was nine
RTTs old at execution. Moving the quote closer to submission can reduce this
age, but changing request order also changes the timing of fills and prices.

## Reviewed candidate

The first proposal simply moved the quote read after reconciliation. Independent
review found a counterexample before any alternative performance run: a
conversion during that later quote request could flatten or change the account
without adding an order ID. A closing quantity based on the earlier snapshot
could then reopen exposure. That proposal was rejected.

The revised implementation fetches the quote after reconciliation, then obtains
and strictly validates a new positions response. The entire position vector
must equal the reconciled snapshot. A mismatch or invalid response stops
cleanup with an attention result and sends no new closing order. The existing
ownership, identity, market-open and reduction-only checks remain in place.

This adds one positions request per fetched book. The expected quote age is
four RTTs. It does not promise a shorter total cleanup or a better terminal
P&L. The interface remains non-atomic: another actor can change the account
after a check. Exclusive account control is still required for live practice.

## Protocol and verification before evaluation

- Initial plan committed as `72eca36`; safety amendment as `5d8bfcd`, both
  before candidate capture performance was evaluated.
- Runtime and driver committed as
  `5832359d4705ac70303d80b7c1b9af2d02a6a25a` at 2026-10-24 08:31:27 UTC.
  The operator declared the freeze at 08:31:30 UTC; the artifacts independently
  record the commit time and baseline start at 08:31:31.599 UTC.
- Runtime baseline: `cd3eb239bd7bad97b34f10a8f2bb0b2e1c0f5026`.
- The 28 runtime dependencies differ only in `bot/practice.py`.
- Runtime SHA-256: `e7675afa3e0d5459ba2a61dc39b47108018b15cde745caa93b6405c7986ec907`.
- Driver SHA-256: `475a19fa02be202c51bdf4f69925663215f634f6e041b8fcf023260337fdbae9`.
- Full Python suite: 651 passed. The initial quote-order tests had three
  failures before implementation; four later position-race tests failed on
  the rejected first proposal before the additional check was added.
- Independent runtime review: 96 focused tests passed; original and revised
  implementations passed the three position-race probes, while the rejected
  first proposal failed them. Sixteen corrupted prerequisite cases were
  rejected. No forbidden access was observed.
- Independent driver review: 26 synthetic checks passed, including eight
  settlement access/copy routes, failures caught by production cleanup,
  quote-history guards, complete baseline validation, corrupted prerequisites,
  and rejection of Python optimization mode before reading inputs.

The fixed comparison contains all 80 settings from complete captures 241–245:
four RTTs (0, 0.05, 0.25, 1 second), two depth fractions (full and half), and
basket conversion off/on. Limits remain 10%, the action cap is 90/minute,
the observed-loss trigger is $250, and prior P&L is zero. The primary setting
remains 0.25 second RTT/full depth/basket on.

The baseline must reproduce every archived result field and seven journal
files for every setting. The candidate is gated on that completed baseline
and must preserve exact pre-cleanup request/fill trace hashes and stop fields.
Sources, inputs, archives and produced baseline journals are hashed and checked
again at completion. Guard violations latch even if production catches an
exception. Every failed or adverse setting remains in the report.

The separately frozen forward evaluators are unchanged. This comparison uses
reused closed paths and cannot establish consistent live profitability or a
competition win probability.

## Complete comparison

Baseline finished at 08:33:33 UTC; candidate finished at 08:35:56 UTC.
All 80 baseline settings reproduced every archived field and journal. All 80
candidate settings preserved pre-cleanup request/fill hashes and stop fields.
Both phases ended with zero diagnostic errors, source changes or forbidden
access attempts. The 68 completed-trial supervisor results are unchanged.
The remaining 12 settings stopped on the observed-loss trigger before completing
the season, even when cleanup later produced a positive terminal P&L.

| Measure, all 80 settings | Baseline | Candidate |
| --- | ---: | ---: |
| Positive / negative terminal P&L | 68 / 12 | 67 / 13 |
| Mean terminal P&L | $478.14 | $478.02 |
| Worst terminal P&L | −$420.64 | −$441.76 |
| Best terminal P&L | $2,236.76 | $2,236.76 |
| Completed / early-stopped trials | 68 / 12 | 68 / 12 |
| Cleanup settled / flat / attention | 68 / 10 / 2 | 68 / 10 / 2 |
| Mean cleanup time across the 12 early stops | 96.00 s | 98.25 s |

Terminal P&L improved in 3 settings, worsened in 5 and was unchanged in 72.
These are correlated execution settings on five recorded paths, not 80
independent seasons or a win-rate estimate.

### Every early-stop setting

Rows marked “off and on” represent two settings with identical displayed
outcomes. All twelve individual rows remain in the machine-readable evidence.

| Capture | RTT | Depth | Basket | Settings | P&L before → after | Cleanup seconds before → after | Final cleanup |
| --- | ---: | --- | --- | ---: | ---: | ---: | --- |
| 243 | 1 s | Full | On | 1 | −381.08 → −344.52 | 230 → 253 | Flat |
| 243 | 1 s | Half | Off | 1 | −391.47 → −398.66 | 260 → 283 | Flat |
| 243 | 1 s | Half | On | 1 | −420.64 → −441.76 | 238 → 290 | Flat |
| 244 | 0 s | Full | Off and on | 2 | −310.74 → −310.74 | 3 → 3 | Flat |
| 244 | 0 s | Half | Off and on | 2 | −277.86 → −277.86 | 5 → 5 | Attention |
| 244 | 0.25 s | Full | Off and on | 2 | −261.00 → −262.75 | 45 → 40.75 | Flat |
| 244 | 0.25 s | Half | Off and on | 2 | −303.34 → −301.70 | 45 → 40.75 | Flat |
| 245 | 1 s | Full | Off | 1 | +5.42 → −12.33 | 228 → 174 | Flat |

The two attention cases retain the same positions in both versions:
AQUA −8, GRID −5 and REIN −20, with no open orders. The new position check
did not produce additional attention outcomes on these recorded paths.

At one second RTT, all closing POSTs occurred nine seconds after their book
GET in the baseline and four seconds after it in the candidate. Nevertheless the three
capture-243 cleanup request counts rose from 228/255/236 to 251/278/285.
Capture 245 fell from 223 to 172 requests. The changed read/fill/retry timing
therefore matters as well as the age of an individual quote.

The mechanics audit found that all 28 empty-book responses in these four
paired scenarios came from captured quotes more than five seconds old, with
positive recorded sizes. These are the replay's stale-data responses; they
do not establish empty liquidity at the live exchange. In the worst setting,
PORT's closing submission moved 245 seconds later, following four such skips.
Its worse fill cost $22.20, partly offset by $1.08 from other symbols.

### Fixed primary setting

| Capture | Baseline terminal P&L | Candidate terminal P&L |
| --- | ---: | ---: |
| 241 | $52.93 | $52.93 |
| 242 | $1,497.40 | $1,497.40 |
| 243 | $286.36 | $286.36 |
| 244 | −$261.00 | −$262.75 |
| 245 | $362.85 | $362.85 |

The candidate's fresher quote did not justify promoting it: the worst loss
and the longest slow-cleanup cases worsened, while residual exposure was
unchanged. Keep the current runtime and investigate request costs under a
separate declared hypothesis.

## Evidence and reproduction

Independent output review checked all 80 pairs and reproduced five
representative settings on both versions: ten reruns with every result field,
pre-cleanup hash, seven journals and cleanup profile matching exactly (80
files). It confirmed 3 P&L improvements, 5 declines and 72 unchanged; cleanup
was faster in 5 settings, slower in 3 and unchanged in 72. Both residual
attention portfolios were unchanged. No forbidden access was observed.

The evidence directory contains the fixed input specification, full results,
metadata, process logs, all baseline/candidate journals and request profiles,
and the preflight review package. `analyze.py` produces all 80 paired rows;
`analysis.json` retains its aggregates and the 16-row union of all early stops
and primary settings, with `unchanged_completed_pairs` added separately.
The separate mechanics audit retains its script, all input hashes, request
decomposition and fill attribution. Raw selected inputs are also preserved locally under
`out/cleanup-quotes-v1-20261024/inputs/`; each copy matches the sealed input
hash in the specification. The original absolute cache paths are recorded
in the immutable specification.

Preflight evidence distinguishes the original retained race harness from fresh
synthetic replications and the reconstructed rejected first proposal. Those
replications did not run alternative captured-market performance.

Use the frozen experimental checkout for the driver; it is intentionally not
installed into the production branch. Independent output audit and archive
verification are recorded with the final evidence manifest.
