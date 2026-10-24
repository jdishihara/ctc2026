# Third completed recorded-market diagnostic

**Later evidence, 08:53 UTC:** all 15 storm tracks in closed captures 241–245
exactly match the fitted analog training library. Source-freeze chronology
does not establish unseen-weather validation. Results below are retained;
see [training-overlap-audit.md](training-overlap-audit.md) for the limitation.

The read-only observer obtained matching ready-state clocks and all 12 official
settlement prices for CID `5edc122c-e97d-4d59-ada5-658c02c3c0da`, fictional
year 1784, at **2026-10-24 06:29:19.863 UTC**. The frozen offline worker evaluated
the season after that receipt. No live trader was running for this evaluation;
these results are virtual fills, not our actual account profit.

## Preselected results

The worker retained all 24 combinations: 10% position limits, order delays of
0.25/1/3 seconds, 100%/50% displayed quantity, basket overlay off/on, and periodic
snapshot warm-up reset off/on. Strategy parameters and the grid were fixed before
the closing receipt. All 24 simulated outcomes were positive, from **$156.65 to
$544.84**. No parameter change or automatic promotion follows from this result.

The 12 scenarios using current snapshot behavior, without periodic warm-up
resets, produced:

| Order delay | Displayed quantity | Core strategy | With basket overlay |
| --- | ---: | ---: | ---: |
| 0.25 s | 100% | $329.95 | $389.27 |
| 0.25 s | 50% | $257.84 | $314.03 |
| 1 s | 100% | $221.44 | $246.00 |
| 1 s | 50% | $156.65 | $177.54 |
| 3 s | 100% | $301.50 | $346.76 |
| 3 s | 50% | $232.43 | $275.79 |

The range for current behavior is **$156.65–$389.27**. Modeled profit need not
decrease monotonically with delay: timing changes which trades execute and
which later decisions are made. This grid does not identify an optimal delay.

## Capture quality and limits

- The receipt and capture contain 860 news messages, exactly sequences 0–859,
  and final reports for all three rounds.
- There are 16,429 quote frames, of which 65 are unusable.
- There are zero recorded disconnect frames and zero subscription
  acknowledgements in the season window. The recorder may log disconnects only
  to text; these counts do not prove that no disconnect or missed quote occurred.
  The artifact explicitly marks the disconnect count as unknown and quote-path
  completeness as unproven.
- The initial quote arrival was approximately 121.31 seconds after the first
  observed round-one frame. The largest interval between quote updates was
  53.77 seconds for REBLD in round one. Full per-symbol/per-round gap statistics and observed close
  boundaries are preserved in the artifact. Quiet quotes cannot be reliably
  distinguished from missed updates from these statistics alone.

Virtual fills consume modeled displayed depth and use the recorded quote path.
Queue priority, market impact, serialized HTTP calls, cancellation races, and
conversion delays remain omitted. The optional HTTP transport merged in PR 11
is not represented in this frozen replay. Historical seasons used during model
fitting or prior research are not untouched holdouts. The first captured market
still has losing stress scenarios, and only one earlier live trial has an
attributable completed positive result.

## Provenance

The worker source remains frozen at `49a690efec04f7dcaf6a616de81da2838afbf149`.
It checks code/model hashes, official receipt identity, recording time bounds,
and every saved output. Its start cutoff is 06:06 UTC and its receipt
cutoff is 12:00 UTC. Subsequent repository changes do not alter this running
evaluation.

The first captured frame was at 05:42:15.592 UTC, before the worker's 06:06
declaration. Its cutoff selects receipts arriving after declaration; it does
not make the entire season an untouched prospective test. The closing receipt
and settlement evaluation arrived later, and no active future outcomes were
read to tune this strategy.

- [All 24 results, official receipt, coverage, and receipt/source-model hashes](evidence/season-243-fixed-evaluation.json).
  SHA-256: `cddaa6544ed12b9b2d3912beba02b2a5f1b85e1646ff50bc6ba9c5ae7db9818b`.
- [Frozen worker manifest](evidence/closed-season-worker-manifest.json).
  SHA-256: `4ccf4ee43071b1df86b9b160176e496d25af8376c819d379c7fcfb5881ce6244`.
- Official receipt SHA-256:
  `8f92306b15696ed4046594b3118a749ae86e5ee259657b528350c5554c74b04a`.

The artifact does not contain a hash of the recording-prefix bytes. Temporal
cutoffs constrain which received frames are selected, but do not cryptographically
prove that those bytes remained unchanged. Independent review reran all 24
scenarios from the retained capture with network, credential, and historical-file
reads blocked; every result field matched. It also independently scanned the raw
feed, checked all 23 source/model hashes, receipt identity, scenario completeness,
and the reported arithmetic. Both archived files are byte-identical to the
worker outputs. The review's provenance wording correction is incorporated here.
