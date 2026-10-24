# Practice loss review — October 23–24, 2026

## What happened

I started the full-size strategy midway through storm 3 to test integration, then forced it flat after a short timer.
That was a poor test design. It exposed real code defects and paid extra execution costs to close the positions.

- Strategy P&L before cleanup: **−1,970.18 simulated dollars**.
- Strategy P&L after cleanup: **−2,589.19**; cleanup added **−619.01**.
- Including two preceding one-contract round trips: **−2,589.80**.
- The first five positions (PORT, GRID, RECON, MAT, HAVEN) accounted for **−1,857.26**, or **94.3%**, of the loss before cleanup.
- Final reconciliation was flat with zero open orders. Trading and the owned recorders were stopped. No remote orders were placed during this investigation.

These figures come from actual exchange receipts and fill replay, not a forecast of what a longer holding period would have earned.

## Causes reproduced offline

### Incomplete history was allowed to authorize full-size positions

The recorder began at news sequence 630, storm age 92. The bot replayed only sequences 630–632 at startup.
The first recorded snapshot had a trajectory from age 0 through 120 and prior-round final reports. Recovery preferred
the few received observations over the snapshot trajectory, leaving the beginning of the current storm absent.
The model knew its weather/outage history was incomplete, but that flag only restricted final-phase valuation;
it did not prevent ordinary trading.

The live log shows HAVEN fair **33.47** against a mid of **58.30** after the snapshot. The bot subsequently sold its
maximum **250** units. A later official advisory changed the forecast sharply. A large displayed edge from this
incomplete state was not reliable evidence for a maximum position.

An offline comparison at the first captured snapshot, using the exact live ensemble parameters
(`sigma=15`, `k=100`, `cone_w=1`, `cone_s0=20`, `cone_nu=0`, `isl_w=0`), gives:

| Startup evidence | PORT fair | HAVEN fair |
| --- | ---: | ---: |
| Three recorded messages + old snapshot recovery | 76.35 | 33.74 |
| Same evidence + corrected snapshot recovery | 79.58 | 37.46 |
| Complete preceding history + recorded messages through snapshot | 96.96 | 55.51 |

This is a fixed-snapshot diagnostic, not an exact recreation of every live thread interleaving. The complete-history
comparison reads published messages **only before sequence 630**, then the actual captured messages through 647;
it uses no later observations or outcomes. Snapshot interpolation still lacks exact earlier weather and advisory
history. **Correcting interpolation alone is insufficient. The new live history gate blocks this startup.**

### Blocking HTTP let execution continue on older inputs

The market-data receiver remained active, but the trading worker processed a whole symbol batch before applying queued
news. During the losing opening batch, a newer official advisory reached the recorder before the final MAT/HAVEN orders.
Quote freshness was checked at batch entry, so several slow REST calls could make later submissions stale.
Canceling the asynchronous driver also did not stop its already-running worker from continuing the batch.

The review additionally reproduced stale-checkpoint and season-rollover cases that could reopen trading too early,
and a restart path that omitted announcement pauses. Those now have dedicated regressions.

## Changes

1. Snapshot recovery merges supported trajectory gaps with received observations, preserves actual and newer points,
   and rejects older-round snapshots. Reconstructed history remains explicitly incomplete.
2. Live orders/conversions require a complete news sequence from season start, complete observed weather, earlier final
   reports, and a current live checkpoint. Missing history cancels resting orders and leaves holdings for operator management.
3. Every order/conversion checks fresh relevant quotes, queued news, announcement pauses, and season synchronization.
4. Driver cancellation latches a stop before waiting for the worker. An HTTP request already submitted can still finish;
   subsequent submissions are blocked.
5. News-led rollover fences the old account until the new competition ID/year is confirmed, preserving the new history already received. Account-led rollover rejects buffered prior-year news without dropping the new season's opening observations.
6. Feed-log replay restores announcement pauses and reports the actual model round even if the recording lacks a storm-formed message.

Strategy parameters, sizing thresholds, fitted models, and research data were not tuned to this loss.

## Verification and remaining limits

- The snapshot regressions failed on the old recovery code; the new live regressions reproduced prohibited submissions before their fixes.
- Full Python suite before upstream integration: **227 passed** (`.venv/bin/python -m pytest -q --tb=short`).
- Full suite after integrating upstream `f3da303`: **238 passed** on `a49544a` (1.86 s); only this verification note was added afterward.
- Offline replay of **all 4,375 captured frames**, seeded with the same three startup messages: **zero order or conversion requests**, no positions.
- Independent review also replayed all **861** published messages of the recorded season through `LiveSession`; the complete-history path remained eligible across all three storms.
- Independent review: **82 targeted tests passed**, all reported findings resolved, ready to merge subject to the full-suite check.
- Portable tests cover complete three-storm histories, missing news, missing weather, late snapshots, stale quotes,
   queued news during HTTP, disconnect checkpoints, news/account rollover, announcement replay, and shutdown during a blocked worker.

These checks establish the repaired behavior. Full-season live profitability and performance against
competition-day opponents remain unverified.

## Advisory differences: measured with complete history

The original recording contains 132 unique news messages, sequences 630–761 of season 239.
Only advisories 664, 698, and 733 differ from the published feed. Their captured payloads are preserved in
[`evidence/practice-advisories.json`](evidence/practice-advisories.json).

Two models with identical complete prior history and the accepted forecast parameters were evaluated after
each of those 132 messages. One used the published advisories; the other substituted the three captured advisories.
The largest absolute fair-value change across all symbols and checkpoints was **0.264848 per ARCH unit** at
sequence 698. The largest HAVEN change was **0.162024 per unit** at sequence 699. An independent reviewer
checked the raw capture and reproduced every per-symbol maximum using `SeasonModel` and `AnalogEnsemble` directly.

Reproduce with:

```bash
.venv/bin/python scripts/audit_practice_advisories.py
```

The diagnostic reads only the news prefix through sequence 761. It uses no prices, settlement values,
API credentials, network requests, or current-season data. This measures sensitivity to the changed advisories;
it does not calculate counterfactual trading P&L. The reason the exchange generated different advisories remains
unknown. No strategy parameters were changed based on this check.

## Operating rule

Start recording and start the bot before the first storm. Require `history complete: trading eligible` and the configured
warm-up before orders. A partial midseason recording stays blocked. Restart only with a complete current-season recording,
or wait to observe a new season from its beginning. API preflight success and a snapshot are not proof of valid model history.

Use offline replay/dry run for strategy diagnostics. A connection smoke test should be one-contract and bounded; it should
not launch the normal maximum-position strategy and force-close it minutes later.

Raw evidence remains in the ignored `recordings/practice-20261024/` directory. A small captured snapshot fixture is
tracked in `tests/fixtures/live_midstorm_snapshot.json`; it contains no account credentials.
