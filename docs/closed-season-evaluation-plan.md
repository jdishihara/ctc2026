# Prospective completed-market evaluation

Declared on 2026-10-24 at approximately 06:06 UTC, during observed season 243.
Keep the entry-corrected strategy and the existing 24-scenario observed-market
grid fixed while the read-only recorder and observer continue through 12:00 UTC.

An offline worker will consume newly written official settlement receipts and
evaluate each completed captured season. Eligibility, receipt validity,
contiguous news, all final reports, and per-round quote coverage are checked by
the existing observed-capture validator before evaluation. Active-season
published history is never read. The worker has no network or account client.

## Boundaries and output

- Record the code/model hashes at startup and refuse further evaluation if any
  relevant file changes. Preserve the full 24 outcomes and coverage limitations.
- Process only receipts at or after the declared start timestamp. Do not select
  favorable seasons or scenarios. Invalid/incomplete captures remain visible as
  failures, with their receipt identity and reason.
- Persist each evaluation and append a compact completion/error ledger. Verify
  previously successful artifact hashes on every pass. A result left without a
  terminal ledger row after a crash must be reproduced before recovery.
  Changed receipts and damaged artifacts fail visibly.
- At 12:00 UTC, perform a final local read to drain qualifying receipts already
  present, including any written during the last sleep. Receipts timestamped at
  or after 12:00 UTC are excluded. This last offline evaluation may finish after
  the cutoff; no orders are involved. Receipts absent at the final read cannot
  be evaluated. A restart must use the same manifest and bounds.
- Summarize every completed result: range, negative-scenario count, and coverage
  warnings. This is counterfactual replay, not actual account profit.

This adds repeated evaluation, without changing parameters or enabling live
orders. Season 243 was already underway at declaration; later seasons begin
after the strategy and grid are fixed. Live controlled practice remains gated
on resolving the shared-account ownership question.

## Operation

Run from the reviewed checkout and leave its code/model files unchanged:

```sh
python scripts/evaluate_closed_seasons.py \
  --observations /absolute/path/to/market-observations.jsonl \
  --feed /absolute/path/to/feed.jsonl \
  --out /absolute/path/to/new-output-directory \
  --start-at 2026-10-24T06:06:00Z \
  --until 2026-10-24T12:00:00Z
```

`manifest.json` freezes source/model hashes, Git revision, inputs, and time
bounds. `ledger.jsonl` preserves starts, stops, failures, and completed summaries.
Each successful season has a UUID-named JSON artifact containing every scenario
and the original receipt/coverage. An exclusive local file lock prevents a
second worker from writing the same output directory. The same command resumes
only if its full manifest matches. A failed evaluation remains visible and is
not automatically retried with different data or settings.

The initial implementation passed 12 regression tests, including six that first
reproduced restart-integrity and deadline defects found in independent review.
The integrated suite passes 390 tests. Independent real-capture validation also
reproduced all 24 season-242 results with network, credential, and historical
season reads blocked. Test counts are not profitability evidence.
