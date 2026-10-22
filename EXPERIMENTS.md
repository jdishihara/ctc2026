# Experiment protocol

Goal: raise holdout PnL of the Hurricane Season strategy without fooling ourselves, so that work can run unattended.

## Fixed evaluation
- Fit anything (damage model, valuation, analog library) on seasons 1-450 only.
- Tune parameters on 451-525. Verify on 526-600. Report 526-600 numbers as "the" result.
- Always report two liquidity regimes: deep (half spread 0.15%, unlimited depth) and thin (0.3%, 100 shares/tick).
  Until the testnet is measured, a change must help in both.
- Accept a change if verify-set mean PnL rises in both regimes and the thin-regime p10 does not fall by more than 10%.
- Every accepted change: commit with the numbers in the message, and add a line to the ledger below.
- Never edit data/. Never force-push or rewrite history. Keep runs under out/ (gitignored).

## Commands
```
python3 scripts/backtest.py --strategy analog --seasons 526-600
python3 scripts/backtest.py --strategy analog --seasons 526-600 --half-spread 0.003 --depth 100
python3 scripts/tune.py --hours 8            # unattended parameter search, out/tune/ledger.csv and best.json
python3 scripts/eval_forecast.py 25 50       # forecast skill
```

## Ledger (verify seasons 526-600, mean PnL deep / thin, losing %)
| date | change | deep | thin | notes |
|---|---|---|---|---|
| 2026-10-22 | analog ensemble baseline (min_edge .01, edge_full .05, sd_mult 1) | see tune/best.json | | first unattended run |

## Backlog (ordered by expected value)
1. Passive quoting: rest orders inside the house spread instead of crossing; measure under thin regime.
2. Insurer convexity: HAVEN/REIN fair should use the loss distribution over analogs (already) plus prior-storm uncertainty for rounds 1-2 (currently a point prior). Replace the point prior for future storms with a sample of historical storms.
3. Rebuilders: RECON and MAT residual ~1 point. Try per-storm saturation with closure hours, or repair backlog carried across rounds.
4. Damage model: fit per-site fragility for AQUA (farm vs fleet) and ISLE; try p < 1 and a separate decay k for damage vs closure.
5. Confidence shaping: trade the insurers harder late in the storm when the loss distribution is tight; cut size when posterior entropy is high.
6. Rate-limit aware rebalancing: fewer symbols per cycle when actions are scarce; prioritise by edge x limit.
7. Early-storm prior: the house open price implies an expected damage; compare with our prior to find systematic house bias by pattern.
8. Preliminary report: model the prelim-to-final error (sd 4-7 points) rather than treating prelim as truth.
9. ETF create/redeem arbitrage when the ETF quote diverges from basket quotes.
10. Mario Markets Monte Carlo pricer and Derivatives Black-Scholes sheet (separate deliverables, not PnL-scored here).
