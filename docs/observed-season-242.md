# Second completed recorded-market diagnostic

**Later evidence, 08:53 UTC:** all 15 storm tracks in closed captures 241–245
exactly match the fitted analog training library. Source-freeze chronology
does not establish unseen-weather validation. Results below are retained;
see [training-overlap-audit.md](training-overlap-audit.md) for the limitation.

The read-only observer obtained matching ready-state clocks and all 12 official
settlement prices for CID `0d7afac2-6acd-4223-aa8a-8c1a067091f0`, fictional
year 1785, at 2026-10-24 05:40:24 UTC. Evaluation began after that receipt.
This account had competing activity, so its actual account P&L is not attributed
to our strategy. The results below are virtual fills against captured quotes.

## Preselected scenarios

All 24 combinations were retained: 10% position limits, 0.25/1/3-second order
latency, 100%/50% displayed quantity, basket overlay off/on, and the old periodic
snapshot warm-up reset off/on. No parameter selection used these outcomes.
All were positive, from $1,448.10 to $2,176.58.

The current snapshot behavior, without periodic warm-up resets, produced:

| Latency | Displayed quantity | Core strategy | With basket overlay |
| --- | ---: | ---: | ---: |
| 0.25 s | 100% | $2,159.30 | $2,176.58 |
| 0.25 s | 50% | $2,087.58 | $2,091.56 |
| 1 s | 100% | $1,886.73 | $1,836.00 |
| 1 s | 50% | $1,818.58 | $1,823.66 |
| 3 s | 100% | $1,640.84 | $1,496.91 |
| 3 s | 50% | $1,532.05 | $1,448.10 |

Independent review reran all 24 scenarios with network connections and
`data/history/` reads blocked. Every result field matched, including positions,
fills, conversions, and marked P&L. The historical simulator's clock fix does
not affect this adapter's separate event loop.

## Capture limits

The receipt and capture independently agree on 866 unique news sequences,
exactly 0–865, and final reports for all three rounds. There are 14,570 quote
frames, 65 unusable. This establishes the checked news sequence, not complete
quote capture.

The recorder logs disconnects to text rather than emitting a disconnect JSON
frame. A new subscription acknowledgement at 05:05:39.963 UTC, 3.520 seconds
after the preceding captured frame, discloses a reconnection. Its actual start
time and missed events are unknown. The report therefore labels zero as the
number of **recorded disconnect frames**, and the disconnect count as unknown.
The replay only applies explicit disconnect frames; it does not reconstruct
that connection's missing interval.

The initial 121.5-second gap spans repeated pre-trading snapshots. The largest
later quote gap is 57.296 seconds for MAT in round three. Quiet quotes and
missed updates cannot be reliably distinguished from this recording.

Displayed depth, replenishment, passive fills, and order latency remain modeled.
Queue competition, market impact, request serialization, cancellation races,
and conversion delays are omitted. This is encouraging diagnostic evidence,
not actual profit, guaranteed executable profit, or proof of unseen-season
generalization. The first captured season still includes a losing stress case.

[All 24 results, receipt, coverage, and listed source hashes](evidence/season-242-observed-market-replay.json).
Those hashes are not a complete recording-prefix and model-artifact manifest.
