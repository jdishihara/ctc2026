# Completed season 241: replaying the recorded market

**Later evidence, 08:53 UTC:** all 15 storm tracks in closed captures 241–245
exactly match the fitted analog training library. Source-freeze chronology
does not establish unseen-weather validation. Results below are retained;
see [training-overlap-audit.md](training-overlap-audit.md) for the limitation.

The first bounded live trial settled at **+$141.16**. A second diagnostic now
uses its 865 captured news messages, 92 snapshots, and 16,992 quote frames,
including recorded bid/ask prices and displayed quantities. The model and
strategy parameters remain frozen. This uses a previously observed season;
it is not an untouched evaluation set.

The adapter performs virtual accounting and never sends exchange requests.
Orders activate on their own latency deadlines. A resting order fills only
when a recorded quote crosses its limit, at the resting limit price. Fills
consume displayed top-of-book quantity; each later recorded quote refreshes
that modeled quantity. Quotes older than five seconds cannot fill orders.
Eight focused tests cover timing, size, freshness, close handling, and guards.

## Corrected results

Basket enabled, 10% position limits, and all displayed top-of-book quantity
available to the virtual strategy:

| Order latency | Warm-up reset on every snapshot | Healthy snapshots preserve warm-up |
| --- | ---: | ---: |
| 0.25 seconds | +$181.48 | +$86.32 |
| 1 second | +$135.72 | +$88.19 |
| 3 seconds | +$109.06 | −$21.70 |

The earlier provisional three-second result of −$41.26 was superseded after
review found that overdue orders were activated at the next feed event instead
of their actual deadline. Two regression tests reproduced that timing error;
the corrected adapter schedules them before later market information arrives.

The same-season historical-price replay earned +$1,628.94 with published news,
or +$1,665.73 with captured news. This recorded-market diagnostic is much closer
to the actual live result, but several things change together: the quote path,
spread and displayed size, wall-clock timing, and live session processing.
It does **not** isolate the price path as the sole cause of the difference.

Healthy snapshot handling permits more trading, but does not improve profit in
this particular replay. Correct execution and profitable decisions are separate
requirements. This one season does not justify changing model thresholds or
restoring the accidental recurring warm-up. Keep subsequent evaluations frozen
and retain every result, including losses.

## Limits and next evaluation

These are **simulated fills**, not actual or guaranteed counterfactual profits.
The model omits queue competition, market impact, HTTP serialization, cancellation
races, conversion delay, and fees outside quoted prices. The recorded quotes
already include the market's response to actual trading. Displayed quantity
refreshes are a modeling assumption. Market closures come from news snapshots,
whose arrival can lag the exchange clock.

Evaluate the frozen variants on subsequent fully captured, officially closed
seasons. Use the same 0.25/1/3-second delays and full/half displayed-depth scenarios;
do not choose parameters from the next season's outcomes while it is active.
Live practice still requires resolving the shared-account conflict.

The completed season's 33 order requests had journal attempt-to-response times
of **0.291 seconds median, 1.030 seconds at the nearest-rank 90th percentile,
and 1.472 seconds maximum**. All attempts paired with recorded responses. These
are not exchange fill latencies and exclude earlier decision/queue/reconciliation
time and later basket-hedge delays. New ownership checks may add reconciliation
time. Keep the three-second stress scenario; this small sample does not justify
dropping it. [Timing evidence](evidence/season-241-request-timing.json).

```bash
.venv/bin/python scripts/replay_captured_market.py \
  --batch recordings/consistency-20261024/batch-01 \
  --feed recordings/consistency-20261024/feed.jsonl \
  --competition-id 6650d983-93c3-45d2-96dd-15209dcd8320
```

Full output: [season-241-recorded-market-replay.json](evidence/season-241-recorded-market-replay.json).

## Subsequent observed seasons

The read-only observer writes official closed-market receipts to
`recordings/consistency-20261024/market-observations.jsonl`. It has no order or
position endpoints. Its receipt proves the observed news prefix and official
settlement identity; it does not prove uninterrupted quote coverage.

Once a completed receipt exists, replace `CLOSED_COMPETITION_ID` below with that
receipt's ID:

```bash
.venv/bin/python scripts/evaluate_observed_season.py \
  --observations recordings/consistency-20261024/market-observations.jsonl \
  --feed recordings/consistency-20261024/feed.jsonl \
  --competition-id CLOSED_COMPETITION_ID
```

This adapter validates the receipt before reading the capture, independently
checks contiguous and nonconflicting news, requires all three pre-storm phases
and final reports, and requires quotes for every symbol in every round. It
reports disconnections and receive-time quote gaps, including uncertainty in
when round closes were observed. It does not claim complete quote-path coverage.

The output retains all 24 predeclared combinations: 0.25/1/3-second latency,
full/half displayed liquidity, baskets on/off, and periodic snapshot warm-up
reset on/off. Limits remain 10% and strategy parameters are unchanged. Source
file hashes identify the implementation. No account P&L is read or reported;
all returns are virtual. Do not use these outcomes to choose new parameters or
describe published historical seasons as an untouched model holdout.
