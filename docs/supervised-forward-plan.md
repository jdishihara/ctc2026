# Corrected practice supervisor on later closing seasons

**Later evidence, 08:53 UTC:** all 15 storm tracks in closed captures 241–245
exactly match the fitted analog training library. Source-freeze chronology
does not establish unseen-weather validation. Results below are retained;
see [training-overlap-audit.md](training-overlap-audit.md) for the limitation.

Declared 2026-10-24 after source freeze at **08:00:15 UTC**, before any capture
245 closing receipt or corrected-supervisor performance results. This protocol
adds an offline evaluation; it does not authorize or start account trading.

## Frozen source and fixed controls

The reviewed runtime is frozen in the clean checkout `.worktrees/practice-history` at
`cd3eb239bd7bad97b34f10a8f2bb0b2e1c0f5026`. Do not edit or merge into that
checkout. Its narrow round-transition correction was independently reviewed;
607 Python tests passed before freezing. Retain the prior supervisor comparison
and the separate 241–244 correction comparison, including all unfavorable rows.

The original comparison driver hard-codes four captures. Use the separately
reviewed `--forward` driver in `.worktrees/supervised-forward`; freeze and record
its exact revision before any forward phase. It verifies all runtime inputs
against Git blobs from `cd3eb23`. Record the driver revision/hash, this protocol's
revision/hash, and the verified runtime manifest separately. The runtime's
08:00:15 freeze is not the later driver's freeze. Do not alter either frozen
checkout after evaluation begins.

For each eligible capture use all 16 predeclared settings: REST RTT
0/0.05/0.25/1 seconds, displayed-depth fraction 1/0.5, baskets off/on. Keep 10%
position limits, 90 actions/minute, the $250 loss trigger, zero prior P&L, and
all strategy parameters unchanged. The primary descriptive setting remains
0.25-second RTT, full displayed depth, baskets enabled. Variants of one market
path are not independent seasons. Do not tune from these results.

## Eligibility and boundary

Read only complete lines from the existing read-only observer's
`recordings/consistency-20261024/market-observations.jsonl`. Include every
official `ready` closing receipt with
`1792828815 <= receipt.at < 1792843200` (08:00:15 through strictly before
12:00:00 UTC), subject to the existing identity and complete-history loaders.
Never read published outcomes for an active season. An eligible receipt that
fails validation or lacks a completed prerequisite remains a visible failure
or pending case; do not silently exclude it.

Capture 245 was already underway at freeze time. Record the first and last
selected frame timestamps for every capture. Only a selected interval starting
after freeze may be called prospective for this corrected source; that label
does not establish full quote coverage or the actual market opening time.

Record each eligibility scan's time and complete-line prefix byte length and
SHA-256, including rejected and malformed receipts. The first scan at or after
12:00 UTC freezes the final prefix boundary. Finish qualifying receipts in that
prefix, then stop. Later appends are outside the evaluation, even if they claim
earlier timestamps. Record unfinished attempts in the final handoff.

Copy the observation file for each scan, require a complete final line, and
verify it equals the same byte prefix of the original append-only file. The
phase loader must consume this immutable copy. Seal a complete-line feed copy
for each attempt as well. Record both byte lengths and SHA-256 values in the
spec; the driver validates them before loading, includes them in its source/input
manifest, and checks for changes after execution. Later live-file appends must
not change the loaded prefix or invalidate its fixed boundary.

## Execution and provenance

Use `recordings/consistency-20261024/supervised-forward/attempts.jsonl` for the
append-only freeze, scan, attempt and completion/failure records. Each capture
gets a distinct directory and immutable input spec. Before executing, record
its competition ID, year, receipt timestamp/hash, spec hash, source revisions,
attempt number and all output/log paths. Preserve every attempt and diagnostic.

The existing frozen sequential forward replay at source `505a5ad` supplies the
16 archived core-client results for that same capture. Require its completed,
successful result/summary/provenance before comparison. The new driver checks
the exact grid, every row's success, summary completion, producer revision and
source hashes, fixed parameters, competition/year, and receipt/frame identity.
Bind the archive results, metadata and summary hashes in the immutable spec.
Then invoke the separately frozen `compare_practice_supervisor.py --forward`
three times with that single-capture spec:

1. `reference`: source `505a5ad`, exact archived-output gate and request/fill
   trace hashes. Reference source must remain unchanged.
2. `baseline`: runtime verified equal to `cd3eb23`, exact archive and reference-trace
   gate. Continue only after all 16 settings pass.
3. `supervised`: runtime verified equal to `cd3eb23`, actual production practice
   supervisor, loss-stop monitoring and cleanup after the verified baseline.

The runner's existing source/spec/receipt/frame hashes and completion gates
remain mandatory; new forward plan, driver and runtime bindings must also match
across phases. A failed prerequisite blocks the dependent phase, while its
failure stays in the ledger. Record each phase exit status and artifact hashes.
Do not replace a failed attempt when retrying; use a distinct attempt directory.

## Reporting

Report every eligible season's primary result and all stress settings, including
losses, incomplete trials, stop reasons, cleanup attention, residual portfolios,
receipt-mark and terminal-settlement differences. Preserve separate counts for
seasons and scenarios. State simulation assumptions and capture gaps. Verify
source/receipt/input hashes and independently rerun representative outcomes
before describing results as checked evidence. No result demonstrates live
profitability or account exclusivity; live practice remains subject to the
unresolved account-ownership issue.
