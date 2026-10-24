# Fixed cleanup retry checks on later closed captures

## Capture 248 result

The unchanged bounded-retry runtime produces the same sixteen terminal outcomes
as the original supervisor on closed capture 248. All settings are positive,
complete and settled; mean $897.99, worst $295.45, best $1,224.03. The primary
remains $985.54. There are no loss stops or extra-pass mutations, so this is
confirmation of unchanged behavior on this path, not another demonstrated
cleanup improvement.

All sixteen pre-cleanup request/fill traces and first-five-pass request hashes
match. Maximum actual mutations in any inclusive trailing 60-second window are
25 in both phases. The primary's contemporaneous final mark is $986.42 and it
retains seven officially settled holdings. A settled receipt does not require
zero positions. No owned live account orders were sent.

## Capture 249 result

The next official close also produces identical results in all sixteen settings:
all are positive, completed and settled, with mean $1,485.76, worst $1,014.34,
best $1,795.95 and primary $1,760.14. The primary's final receipt mark is
$1,755.61 and nine nonzero holdings are valued at settlement. No setting hits
the loss trigger or needs extra cleanup passes. Maximum actual rolling
mutations are 27 in both phases. All sixteen pre-cleanup request/fill traces
and first-five-pass request comparisons match; no declared adverse-result rule
is triggered. Independent verification is complete: all 32 rows, 288 produced
files and 244 source/input hashes pass. The primary and slow reproductions
match every field and all 18 files, with zero guard violations.

The original baseline passed first. The initial candidate invocation supplied
a results file to the directory-valued `--baseline` argument. It failed before
creating candidate outputs or running any performance scenario. Its logs and
failure event are retained. A distinct `attempt-02` directory contains a
byte-identical 147-file baseline copy and the corrected candidate invocation;
the baseline was not rerun and the source, specification and settings did not
change. Each successful phase retains 144 journal/profile files.

This capture's selected interval starts at 10:36:43.060 UTC, after the retry
declaration and driver freeze, and closes at 11:23:46.284 UTC. All three weather
tracks nevertheless match fitted rows 744–746 exactly. It confirms unchanged
behavior on this known path, without demonstrating a new cleanup improvement
or unfamiliar-weather profitability. Original evaluator details are in
[capture 249](observed-season-249.md). The separate
[evidence manifest](evidence/cleanup-retry-forward-249/artifact-manifest.json)
retains both invocation attempts and the
[375-file independent audit](evidence/cleanup-retry-forward-249/independent-review.tar.gz).

## Declaration and corrected preflight

The [fixed follow-up plan](cleanup-retry-forward-plan.md) was committed as
`fd35a1e` at 10:28:13 UTC, before capture 248's 10:34:46.327 UTC closing
receipt. It specifies captures 248 and 249, their complete sixteen-setting
grids, the original source/input gates and unchanged risk rules. Unlike the
initial 112-setting promotion experiment, a no-op confirmation does not require
a new residual reduction. Both declared captures have now closed and completed
their fixed comparisons and passed independent audits.

The new evaluator at `4a10763` initially checked receipt type/time and input
hashes too narrowly. Independent synthetic review demonstrated that consistent
hashes could accompany running clocks, the wrong year/source, or an archive
from the wrong phase. No actual capture performance ran with that version.
The rejected 134-file preflight archive and every counterexample are preserved.

The corrected evaluator freezes at `2c441ae`, 10:33:37 UTC. It validates the
complete ready/ready official receipt, full symbol and news coverage, source,
year and competition identity, and the exact declaration-to-cutoff interval.
It reconstructs the sealed observed capture and binds its frames/receipt to
the cache. The original full-supervisor phase must match the frozen `c5c35a3`
driver, `cd3eb23` runtime, `505a5ad` serialized predecessor, source Git blobs,
input hashes, complete grid, configuration and verified completion metadata.

The trading runtime stays byte-identical to reviewed `27ab7c4`, already merged
in [PR 28](https://github.com/jdishihara/ctc2026/pull/28). The changes in this
follow-up are confined to the offline evaluator, tests, plan and evidence.
All existing forward evaluators remain at their original frozen versions.

The final full Python suite passes 713 tests; 61 focused prerequisite tests pass
under independent access guards. Actual-main synthetic baseline/candidate
checks cover both allowed capture IDs. Seventy receipt/provenance corruptions
are rejected before replay; fault-injection phases retain the complete grid.
The approved 359-file preflight archive preserves all prior harness failures.
The separate analyzer passes 27 synthetic checks, including zero loss stops,
unchanged outcomes, adverse pairs and mutation boundaries.

## Capture 248 paired evidence

Original reference, baseline and full-supervisor phases passed before the retry
comparison. Its baseline reproduces all sixteen original result rows and all
112 standard journal files. Candidate evaluation begins only after that gate.
Both phases finish with zero errors, forbidden accesses or source changes and
retain 144 journal/profile files each.

| Metric | Baseline | Retry candidate |
| --- | ---: | ---: |
| Positive / negative settings | 16 / 0 | 16 / 0 |
| Mean terminal P&L | $897.99 | $897.99 |
| Worst / best terminal P&L | $295.45 / $1,224.03 | $295.45 / $1,224.03 |
| Completed / settled | 16 / 16 | 16 / 16 |
| Loss stops / extra-pass mutations | 0 / 0 | 0 / 0 |
| Lowest observed mark | −$138.80 | −$138.80 |
| Maximum observed marked drawdown | $367.48 | $367.48 |
| Maximum rolling mutations | 25 | 25 |

There are zero P&L improvements or regressions. No rejection rule is triggered.
Independent audit verifies all 32 rows, 288 produced files, 112 original journals
and 244 source/input hashes. Both predeclared candidate reproductions (primary
and slow/thin) match every field and all 18 files, with zero guard violations.
The 360-file review archive preserves the failed read-only audit assertion and
its correction; neither caused an additional performance run. No new blocker
was found. This passes the declared no-op confirmation gate for capture 248.

## Timing and limitations

Capture 248's selected interval began at 09:47:38.558 UTC, before the retry
declaration and source freeze. The plan predates closure, but this is not a
fully prospective captured path. Its three weather tracks exactly match
fitted-library rows 741–743. It therefore does not demonstrate performance
on unfamiliar weather. The original audit and quote coverage limitations are
in [observed-season-248.md](observed-season-248.md).

All sixteen execution settings reuse one path. Fixed latency, displayed depth,
assumed fills, missing quote intervals, queue priority and own market impact
limit the interpretation. The $250 observed loss trigger is sampled rather
than a hard loss bound. The actual attributable practice record is unchanged.

The [artifact manifest](evidence/cleanup-retry-forward/artifact-manifest.json)
hashes specifications, phase outputs, journal/profile archives, source and test
logs, both preflight archives, the analyzer and independent reviews. Raw cached
frames remain at the immutable local path in the specification; their canonical
hashes match the independent original capture audit despite different JSON
whitespace. Every failed invocation is retained without rewriting its bytes.
