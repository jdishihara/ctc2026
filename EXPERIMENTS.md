# Experiment protocol

Goal: raise holdout PnL of the Hurricane Season strategy without fooling ourselves, so that work can run unattended.

## Fixed evaluation
- Fit anything (damage model, valuation, analog library) on seasons 1-450 only.
- Tune parameters on 451-525. Verify on 526-600. Report 526-600 numbers as "the" result.
- Liquidity: the simulator uses the ladder measured on the testnet (ctc/ladder.json, from recordings/books.jsonl via
  scripts/calibrate_book.py). Report two regimes: deep (ladder, refill 10 s) and thin (ladder at half size, refill 30 s).
  Re-run scripts/calibrate_book.py when more book snapshots exist; the ladder also contains other teams' orders.
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
| 2026-10-22 | analog ensemble, flat-spread model (obsolete) | 10168 | | before the ladder was measured |
| 2026-10-22 | ladder fill model + liquidity-aware limits, hold through convergence | 5047 (27% losing, min -17k) | | tail is the problem now |
| 2026-10-22 | exchange tick: limit prices rounded to 0.01 in bot and sim (testnet rejected 119/121 orders) | 5012 (p10 -4628) | 2515 (p10 -6878) | new baseline; verify numbers barely move |
| 2026-10-22 | prelim report combined with the nowcast (final = a + b*prelim + c*nowcast, scripts/fit_prelim.py) instead of taken as truth; loss-estimate sd added to model_sd | 5159 (p10 -4339, min -13.5k) | 3108 (p10 -6582, min -15.3k) | ACCEPTED. dissect.py: aftermath insurer fills lost 43k/75 seasons because fair_sd was 0 after the prelim; prelim rmse (PORT 9.3 pts, loss 97 $M) is worse than our nowcast (5.7, 64); combined 4.8 / 52 |
| 2026-10-22 | per-symbol-per-round loss limit (stop adding after losing L in a cell; `--loss-limit`) | tune 451-525: L=1000 5878/3823 vs 6067/4044 off; L=2000 6086/4021 (thin p10 -6347 vs -6016); L=4000 never triggers | | REJECTED on the tune set, not run on verify. Losses come from fair being wrong, not from churn; a stop locks them in |
| 2026-10-22 01:45 | ladder refit from 611 book snapshots per symbol (00:31-01:36, 5 testnet seasons) instead of 22; recorder now logs our own open orders so later refits subtract them | 4716 (p10 -4590, min -14.1k, 33% losing) | 2654 (p10 -7128, min -15.7k, 37% losing) | NEW BASELINE (not a strategy change). Top of book is thinner than the first sample (first band 20-80 shares, was 20-160), spreads 0.23-0.32%; the house keeps a 600-lot backstop about 8% away. Tuner rows after 01:45 use this ladder |
| 2026-10-22 02:05 | testnet vs backtest, season 182 (fictional year 1845; year 2027-N): testnet realized -14.2k after rounds 1-2, PORT flipped side 31 times in 16 min. Cause: bot/live.py constructed FairValueTrader without analog=True, i.e. it ran the constant-velocity NOWCAST. Backtest of 182 under the ladder: nowcast -23.1k (853 fills), analog +9.3k (130 fills). Sign and size agree with the sim, so the simulator is faithful and the bot was wrong. Bot now runs the analog ensemble (flags --sigma --k --sd-mult, --nowcast for debugging); restarted 02:02 | | | FIXED (bot). Season 181 was traded by the tick-broken bot, no comparison possible. Still to compare: seasons 183+ with the analog bot |
| 2026-10-22 02:08 | ladder refit with finer far bands (0.06-0.10) so the house's 600-lot backstop lands in the right bin (live it sits 7-8.5% from mid); 846 snapshots | 4917 (p10 -4519, min -14.1k, 29% losing) | 3004 (p10 -6780, min -15.4k, 37% losing) | NEW BASELINE for the rest of the night |
| 2026-10-22 02:40 | future-storm prior = average of the valuation over a sample of historical storms (400 one-, two- and three-storm combinations from seasons 1-450, ctc/storm_sample.npz) instead of the valuation at the mean storm; vectorised values(); `--prior point` keeps the old behaviour | 5957 (p10 -2517, min -10.2k, 23% losing) | 3943 (p10 -5044, min -13.8k, 27% losing) | ACCEPTED (+1040 / +939; p10 up 44% / 26%). Convexity: with two storms to come HAVEN fair moves 40.6 -> 44.9 and REIN 90.0 -> 88.5 at a typical state; HAVEN pnl +900/season. Live bot restarted on it 02:41 |

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
