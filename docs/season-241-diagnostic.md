# First completed live season: +$141.16

The first controlled trial settled at 04:51:09 UTC on October 24, 2026, using
the frozen runtime `59603dd` and 10% of normal per-symbol limits. The receipt
verified a closed market, all 12 official settlement prices, and no open orders.
There were 33 acknowledged orders and one ETF conversion. The lowest observed
cumulative P&L was −$17.60; this is not a peak-to-trough drawdown statistic.

## Same-season historical replay

All 865 news messages for historical season 241 were captured. Of these, 841
matched exactly and 24 advisories differed in cone/probability/headline fields.
All 12 published settlement prices exactly matched the official live prices.

The diagnostic uses the accepted model parameters, 10% limits, 90 actions per
minute, historical market prices, the measured static ladder with a ten-second
refill, and 0.25-second simulated order latency.

| News supplied to simulator | Basket overlay | Simulated P&L |
| --- | --- | ---: |
| Published | Enabled | +$1,628.94 |
| Captured live | Enabled | +$1,665.73 |
| Published | Disabled for diagnosis | +$1,330.73 |
| Captured live | Disabled for diagnosis | +$1,327.25 |
| Captured live, complete-history gate enforced | Disabled for diagnosis | +$1,327.25 |

The advisory differences do not explain the large live/replay gap in this
diagnostic. The complete-history gate also has no effect on the core-only replay
in this season, so this result supplies no reason to weaken that guard.

These replay scores are **not live counterfactual profits**. They use a different
market-price path, modeled fills and liquidity, and omit the live HTTP cycle and
periodic snapshot processing. An exploratory alignment of recorded quotes to
nearby news clocks also found material differences from historical market prices.
That comparison does not establish how many orders would have filled.

## Execution findings

The live basket cycle had −$8.73 market-trade cashflow before separate fees and
restored its starting inventory. Its roughly 63-second duration exposed an
avoidable shared retry delay for unsent component legs. Repeated healthy
snapshots also restarted warm-up. Both fixes were reproduced offline and
independently reviewed, with 271 tests passing in their isolated checkout.
They are not part of this live result and need a subsequent live evaluation.

One small-size profitable season is an execution milestone, not evidence of
consistent profitability. The batch was subsequently interrupted when another
trader's orders appeared in its second season. All results and raw receipts
are retained; see [shared-account-incident.md](shared-account-incident.md).

## Reproduce

```bash
.venv/bin/python scripts/audit_completed_season.py \
  --batch recordings/consistency-20261024/batch-01 \
  --feed recordings/consistency-20261024/feed.jsonl \
  --competition-id 6650d983-93c3-45d2-96dd-15209dcd8320 --season 241
```

The script refuses an uncompleted trial before reading its historical outcome.
Recorded output: [evidence/season-241-live-replay.json](evidence/season-241-live-replay.json).
