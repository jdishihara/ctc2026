# Hurricane Season efficiency and execution verification

2026-10-23 — Codex, for Arjun. Reference revision: `f4eb4dd`.

## Result

Complete analog forecasts ran **1.71× faster** on the measured workload, with a
maximum absolute difference of `1.14e-13` in fair values and uncertainty outputs.
The execution changes pass **40 tests**, including a local HTTP integration test.
Verification replay mean PnL increases by only **1.79 deep / 2.58 thin per season**;
this is an efficiency and correctness improvement, not evidence of a material
new trading advantage or an optimal competition strategy.

## Case and evaluation

The downloaded four-page PDF contains the overview. The detailed rules and the
research archive are linked from the [official case packet](https://docs.google.com/document/d/1XnZGvu3qPCc0abJYtkax9IyHVbx-LvUH6s1k8Y9j3Ps/edit).
Systematic Equities permits bots; the other cases use manual trading. The packet
describes 10 stocks, two ETFs, three 13-minute rounds, position limits that include
same-side open orders, and limits of 300 actions/minute per bot key and 180 per
team. The existing bot's conservative 120-action budget is retained.

Downloaded the packet's official 600-season research archive. Its `case.json`
matches the repository exactly; history remains ignored. No fitted parameters,
library, valuation rules, default strategy flags, or published historical records
were modified. All calculations here use the same history in both checkouts.

Evaluation follows `EXPERIMENTS.md`: fit 1–450, tune 451–525, verify 526–600.
Tune results were checked before verification; no parameters were selected on
verification seasons. The default measured ladder uses refill 10 s; thin uses
refill 30 s and half-sized liquidity.

## Computation

- Align historical tracks to actual observation ages, including sparse prefixes,
  instead of assuming that the number of observations equals elapsed time.
- Cache squared track errors only while the entire observed prefix is unchanged.
  Corrected, truncated, or replaced observations reset that evidence.
- Use partition selection for the top analogs while preserving ties.
- Vectorize damage and outage calculations across analogs within each company.

`scripts/benchmark_forecast.py` compares complete `fair_analog` calls with the
reference implementation, including fair values, current uncertainty and future
uncertainty. It alternates measurement order, feeds real messages, and asserts
numerical agreement. Seasons 451/470/500, three repeats, 1,419 calls per version;
Python 3.14.7, NumPy 2.5.4, arm64:

| Metric | Reference | Candidate |
|---|---:|---:|
| Total forecast time | 8,235.53 ms | 4,817.48 ms |
| Median call | 6.798 ms | 3.488 ms |
| p95 call | 7.088 ms | 5.804 ms |
| Maximum absolute output difference | — | 1.1369e-13 |

Total time falls 41.5%. This measures forecast CPU work, not live network latency
or end-to-end trading latency. Initial sequential replay runs took 169/171 s for
the reference's 150 seasons in deep/thin, versus 104/100 s for the candidate's
two 75-season blocks per regime. Replay wall time is approximate and machine
dependent; the dedicated benchmark is the primary speed measurement.

## Execution

- Failed or rate-limited cancellations keep reservations and block replacement.
  Successful cancellations reconcile positions and open orders, including fills
  that beat the cancellation, before replacement quantities are calculated.
- Refresh builds a complete account snapshot before publishing it. Missing
  symbols reset to zero. Reading orders before positions conservatively accounts
  for fills between those two reads; any failed required read blocks new orders.
- Timeouts, truncated responses and malformed or missing order acknowledgements
  block submissions until reconciliation. Acknowledged fills update inventory;
  accepted unfilled quantities reserve capacity immediately.
- Pausing a symbol cancels its orders, including orders absent locally after a
  lost acknowledgement, and retries failed cancellations.
- Filled passive quotes can be replenished immediately. Cached quote metadata
  alone no longer suppresses replacement for 120 seconds.
- Pending simulated orders reserve capacity. ETF conversion marks the account
  uncertain until a complete refresh.

## Replay results

PnL is simulator currency per season. Values below are calculated from the
per-season CSVs, including the simulator's cent rounding. Every row has 75
seasons. Both versions had zero rejected simulated orders.

| Split / regime | Reference mean | Candidate mean | Change |
|---|---:|---:|---:|
| Tune / deep | 8,572.12 | 8,577.71 | +5.59 |
| Tune / thin | 5,154.10 | 5,155.03 | +0.93 |
| Verify / deep | 9,343.72 | 9,345.51 | +1.79 |
| Verify / thin | 5,924.82 | 5,927.40 | +2.58 |

| Verify metric | Reference deep | Candidate deep | Reference thin | Candidate thin |
|---|---:|---:|---:|---:|
| Median | 9,435.54 | 9,435.54 | 6,230.87 | 6,201.42 |
| p10 | -144.98 | -147.60 | -2,680.86 | -2,682.24 |
| Minimum | -15,909.83 | -15,911.48 | -17,236.05 | -17,236.05 |
| Losing seasons | 8/75 | 8/75 | 13/75 | 13/75 |
| Mean fills | 363.19 | 363.89 | 900.45 | 901.39 |

Both verification means rise. Thin p10 deteriorates by 1.384, or 0.052%, within
the existing 10% acceptance bound. Deep p10 deteriorates by 2.622. The tiny mean
changes do not establish statistical significance. Dense forecast parity is
checked separately: replay changes include corrected passive replenishment and
pending-order reservations.

## Verification and review

`python -m pytest -q`: **40 passed**. Coverage includes independent sparse-track
oracles, corrections and resets, top-k ties, terminal ages, scalar versus
vectorized damage, reservation limits, failed refresh and cancellation, unknown
acknowledgements, racing fills, passive replacement, and pause retries. The local
HTTP server exercises real urllib requests, tick rounding, cancellation HTTP 503,
blocking during uncertainty, HTTP 204 cancellation, reconciliation and recovery.

One independent code review identified four important execution defects. Each
was reproduced with failing regression tests and fixed: invalid acknowledgements,
truncated HTTP replies, fills racing with refresh/cancel, and paused orders whose
acknowledgement was lost. Quantity-validation regressions were also added.

After the review fixes, both verification regimes were rerun: 49 s deep / 50 s
thin. Their complete CSVs are byte-for-byte identical to the candidate results
above. Final `python -m pytest -q`: 40 passed in 0.59 s.

Rulings and limitations:

- Preserve the existing fitted strategy and its evaluation split. The patch does
  not eliminate large losing seasons or the documented live/simulator PnL gap.
- Treat a cancel response as provisional until an account refresh confirms that
  target orders are gone. Separate HTTP snapshots are not a transaction; orders
  first is conservative for fills, but concurrent trading from another client
  still requires coordination.
- Defer the review's minor fractional-age integration issue: exposure still
  weights each future sample by two seconds when the latest age lies between
  samples. The supplied dense history uses two-second steps; fractional-position
  matching is tested, but fractional-duration exposure is not claimed exact.
- Sparse-track matching does not reconstruct unobserved past damage. Existing
  feed-log replay remains preferable to an incomplete reconnect snapshot.
- No ETF arbitrage strategy was added. Simulator ETF conversion accounting and
  live multi-asset behavior need separate verification before using one.
- No orders were sent to the competition or testnet. The live adapter uses
  synchronous HTTP, and the real exchange response shapes still need a supervised
  testnet check before deployment. Local tests cannot certify the remote API.

## Reproduce

Install `requirements-dev.txt`, place the official unmodified history under
`data/history`, and create a reference worktree at `f4eb4dd` with the same history.
Use the same Python environment for both checkouts.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/benchmark_forecast.py --baseline ../ctc2026-reference \
  --seasons 451,470,500 --repeats 3 --out out/forecast-benchmark.json
python scripts/backtest.py --strategy analog --seasons 451-525 --out out/tune-deep
python scripts/backtest.py --strategy analog --seasons 451-525 \
  --refill 30 --ladder-scale 0.5 --out out/tune-thin
python scripts/backtest.py --strategy analog --seasons 526-600 --out out/verify-deep
python scripts/backtest.py --strategy analog --seasons 526-600 \
  --refill 30 --ladder-scale 0.5 --out out/verify-thin
```

Run the same replay commands in the reference worktree for comparison. Results
are written to each output directory's `backtest_analog.csv`; output and history
are intentionally ignored by Git.
