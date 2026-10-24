# Fixed execution replay on later closing seasons

**Later evidence, 08:53 UTC:** all 15 storm tracks in closed captures 241–245
exactly match the fitted analog training library. Source-freeze chronology
does not establish unseen-weather validation. Results below are retained;
see [training-overlap-audit.md](training-overlap-audit.md) for the limitation.

Declared 2026-10-24 07:17 UTC, before evaluating any official outcome for
season 244. Effective freeze time is the commit time of this plan and the
source manifest correction. The original fixed worker continues separately.

## Purpose and source

Carry the independently checked serial REST model into subsequent recorded
markets without changing strategy parameters in response to each result.
The backend is the reviewed version from PR #16, with only a manifest correction:
include imported `bot/control.py` and this forward plan in future source hashes.
No trading or fill behavior changes. Freeze this checkout and its HEAD before
the first evaluation and retain it until 12:00 UTC / 08:00 EDT.

## Eligibility and timing labels

- Include season 244 as the predeclared initial carryover, plus every new
  official `ready` closing receipt with `freeze_at <= receipt.at < cutoff`,
  where `cutoff` is 2026-10-24 12:00:00 UTC, subject to the existing
  complete-history validation. Do not
  read published outcomes for an active season. Use only the observer's closing
  receipt and the recorder's selected frames.
- Season 244 was already underway when this plan was declared. Label its result
  accordingly; it is not a fully prospective season for this execution model.
  It remains included if its closing receipt falls just before the commit.
- For each later capture, record the first captured timestamp relative to the
  freeze time. Only captures whose entire selected interval starts afterward
  may be called prospective recorded intervals. This does not prove full quote
  coverage or establish the actual market opening time.
- Record all eligible captures, including invalid-history failures. Preserve
  partial/error runs and use a distinct directory for any explicit retry.

## Eligibility and attempt record

Maintain `recordings/consistency-20261024/serialized-forward/attempts.jsonl`
outside the frozen checkout. Before invoking the replay CLI, append an
`attempt_started` row with the CID, year, receipt timestamp and SHA-256, source
revision, attempt number, output path, and stdout/stderr log paths. Append a
matching completion/failure row with exit status and artifact hashes afterward.
Capture stdout and stderr even if the CLI fails before creating its output
directory. A started attempt without a terminal row remains visibly incomplete;
do not certify it or erase it when retrying.

For each eligibility scan, record its wall-clock time and the observation file's
complete-line prefix length and SHA-256. An append-only source can then be
rechecked against the exact prefix used. Record rejected/malformed receipts
explicitly; do not silently skip them. The initial ledger row records the exact
freeze timestamp and source revision. Receipt identity/history validation is
still performed by the existing CLI and failures retain their attempt entries.

The final eligibility boundary is the complete-line observation prefix captured
by the first scan at or after 12:00 UTC. Record that scan time, prefix byte count,
and hash; include only qualifying receipts within that prefix whose timestamp
is strictly before the cutoff (including the declared 244 carryover). Finish
those evaluations, then stop. Later appended receipts are outside the declared
observation boundary even if they claim an earlier timestamp. Report the final
boundary and any unfinished attempts in the handoff.

## Fixed grid and reporting

Run exactly the reviewed 16 scenarios on each eligible capture: REST RTT
0/0.05/0.25/1 seconds × displayed-depth fraction 1/0.5 × basket off/on.
Position limits stay at 10%, action cap 90/minute, and all other strategy
parameters remain frozen. Use the existing `observed` replay entry point with
the official receipt gate. Save metadata, every result row, and summary under
`recordings/consistency-20261024/serialized-forward/<competition-id>/`.

The primary descriptive scenario is **0.25-second RTT, full displayed depth,
baskets enabled**, selected before these outcomes. Report its return and risk
for every eligible capture, alongside the complete stress grid. Count seasons
separately; the 16 variants of one market path are not independent trials.
Report missing or invalid cases rather than silently excluding them from the
primary record. No tuning, best-scenario selection, or size increase follows
from a single positive result.

Verify source/input/receipt hashes and independently reproduce representative
results before presenting them as checked evidence. The raw source revision
and all failure artifacts remain available even if later documentation changes.

## Limits and stopping

These are offline virtual fills, not owned account profits. Fixed RTT,
instantaneous CPU/conversion assumptions, unknown quote/disconnect coverage,
and omitted queue priority/own impact remain as documented in
[serialized-client-replay.md](serialized-client-replay.md). The last-frame
terminal fence can help or hurt results. New captures improve the evidence;
they cannot establish an unbeatable strategy.

Finish processing receipts timestamped before 12:00 UTC, then produce the
competition handoff. Do not restart live trading without resolving shared
account ownership, and do not continue practice trading into the competition.
