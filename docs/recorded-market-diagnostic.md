# Completed season 241: replaying the recorded market

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

```bash
.venv/bin/python scripts/replay_captured_market.py \
  --batch recordings/consistency-20261024/batch-01 \
  --feed recordings/consistency-20261024/feed.jsonl \
  --competition-id 6650d983-93c3-45d2-96dd-15209dcd8320
```

Full output: [season-241-recorded-market-replay.json](evidence/season-241-recorded-market-replay.json).
