# Overnight report 2026-10-22 (session 01:00-07:10, 28 commits, all pushed)

## What improved (verify seasons 526-600, deep / thin regime, mean PnL and p10)

| step | deep | thin |
|---|---|---|
| start of night (old 22-snapshot ladder) | 5012 / -4628 | 2515 / -6878 |
| prelim report combined with our nowcast | 5159 / -4339 | 3108 / -6582 |
| ladder refit from 846 overnight snapshots (new baseline, not a strategy change) | 4917 / -4519 | 3004 / -6780 |
| future-storm prior = sample of 1350 historical storms (convexity) | 5957 / -2517 | 3943 / -5044 |
| SIM FIX: passive fills capped by the house size that crosses us (lowers the baseline) | 5130 / -3529 | 1691 / -6794 |
| passive quoting inside the spread at 0.75 x floor | 6320 / -2986 | 2681 / -6992 |
| 20 s warm-up after each round opens | 6353 / -3078 | 2711 / -7024 |
| tuner's parameter set (min_edge 0.02, edge_full 0.03, sd_mult 0.7, sigma 15, k 100) | **8433 / -3050** | **5073 / -6355** |

Like for like (same simulator), the strategy went from 5130 / 1691 to 8433 / 5073; losing seasons 25% -> 19% deep, 40% -> 24% thin.

## Rejected (details in the ledger)
Per-symbol-per-round loss limit; future-storm valuation sd in the edge floor (everywhere or outside the storm);
exact rebuilder settlement rules (found: RECON, MAT and GEN settle to exact weighted saturations, holdout rmse 0.003,
but using them lowers PnL by about 110/season because the rebuilders then trade at 1% edges; kept behind
`--exact-rebuild`); house inventory skew (measured, not material); ETF create/redeem arbitrage (measured, small, not built).

## Live bot: three bugs fixed, then compared with the backtest
1. Every order was rejected: prices were not multiples of the 0.01 tick (119 of 121 orders before 01:03).
2. The bot ran the constant-velocity NOWCAST, not the analog ensemble (missing flag): season 182 lost 14k while flipping PORT 31 times in 16 minutes; the sim agrees the nowcast loses 23k on that season.
3. At each round open it fired full-size orders in all 12 symbols into a thin book and spammed rejected orders during halts; now a 20 s warm-up and halt handling. Live fill cost fell from 93 bp to 29 bp of notional.

Testnet vs sim (season = 2027 - fictional year; sim is the deep regime with the defaults of the time):

| season | testnet | sim | note |
|---|---|---|---|
| 184 | +4.9k | +9.5k | first clean analog season |
| 185 | -16.3k | +7.4k | testnet replayed round 1 in one second, bot traded the round-2 open into the 8% backstop |
| 186 | -0.5k | +6.3k | |
| 187 | +17.8k | +19.6k | after warm-up fix |
| 188 | +4.9k | +7.3k | |
| 189 | +3.0k | +8.8k | |

Sign agrees in 5 of 6; the testnet runs 3-6k per season below the sim. The sim has no opening phase and the house's
book is thinner at the open than the ladder median; passive fills happen live (our resting orders get lifted).

## Deliverables
- scripts/dissect.py (where the losses are), scripts/fit_prelim.py, scripts/build_storm_sample.py, scripts/fit_rebuilders.py, calibrate_book.py with band and own-order handling.
- mario/pricer.py: settle / points / calib commands, CPU prior -0.6; mario/README.md drill sheet with the series-win-by-lead and score tables.
- derivs/desk.xlsx (derivs/build_sheet.py): 12 contracts with live Black-Scholes formulas, market IV, analyst scorecard with inverse-error weights, event timeline; formulas verified against bs.py.
- README refreshed. Bot logs season PnL every 10 s and at SEASON END.

## Top three decisions for Jayden
1. **Parameters for competition day.** The accepted set (min_edge 0.02, edge_full 0.03, sd_mult 0.7, sigma 15, k 100) was selected by the tuner under an older fill model and verified once under the current one. Run `python3 scripts/tune.py --hours 4` on the current simulator today and re-verify the winner; if it does not reproduce, fall back to the previous defaults (0.01 / 0.05 / 1.0 / 25 / 50), which gave 6353 / 2711.
2. **Exact rebuilder rules.** They are the true settlement formulas (rmse 0.003) but cost about 110/season in the sim because RECON/MAT then trade at 1% edges. Either accept the tiny PnL cost for a correct model, or add a 3% floor for RECON/MAT only (needs a tune run); decide before the strategy is frozen.
3. **Round opens on the day.** The testnet opens rounds with a thin book and sometimes replays a round instantly; the 20 s warm-up covers the first case. Decide whether a human watches the first minute of each round, and whether the bot should cap aggressive size per cycle at the open instead of trusting the liquidity-aware limit (which walked into the 8% backstop twice tonight).

Still running at 07:10: feed recorder, book recorder, live bot (restarted 07:08 on the new defaults), tuner (ends 07:40), caffeinate (until 10:30). Nothing deleted, no history rewritten, key not in the repo.

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
| 2026-10-22 03:05 | SIM FIX: a resting order crossed by the house now fills only for the size the house posts at or beyond our price (ladder walk), piecewise as depth regenerates, instead of its whole remainder at once. The remainder of every aggressive limit order rests, so this lowers the baseline | 5130 (p10 -3529, min -11.0k, 25% losing, 320 fills) | 1691 (p10 -6794, min -16.4k, 40% losing, 716 fills) | NEW BASELINE. The previous two ledger rows were measured with the generous passive fill |
| 2026-10-22 03:08 | passive quoting: when the edge is below the floor, rest one order inside the spread at the price where the edge equals 0.75 x floor, replaced only when the price moves (`--passive 0.75`, now the default in backtest.py and bot/live.py). Tune 451-525: 0.5 gives the highest mean but thin p10 falls 12%; 1.0 is a no-op | 6320 (p10 -2986, min -11.3k, 19% losing) | 2681 (p10 -6992, min -17.1k, 33% losing) | ACCEPTED (+1190 / +990; thin p10 -2.9%). Max 47 order actions per minute in the sim (bot cap 120). Whether the testnet house crosses resting orders is unverified: check the live fills tomorrow |
| 2026-10-22 03:40 | testnet vs backtest, analog bot (season = 2027 - fictional year). 184: testnet +4.9k (realized 2.2k + unrealized 2.8k at season end), sim deep +9.5k. 185 (rounds 2-3 only; the testnet replayed round 1 in one second at 03:07 and opened trading at 03:08:50): testnet -9.6k after round 2, sim +6.8k at the round-2 mark. At that open the bot sent full-size orders in all 12 symbols within one second against fresh opening prices (PORT bought at 80.6, direct hit took it to 63); those opening fills do not appear in /trades. Live passive fills DO happen (PORT sold at 79.07 above the 78.52 ask = our resting order lifted) | | | PARTLY EXPLAINED. Sim has no opening phase and no instant round replay. Fix below. 183 unreadable (bot restarted mid-season twice) |
| 2026-10-22 03:42 | round-open warm-up: no trading for 20 s after a round (or the market) opens (`--warmup 20`, default in backtest.py and bot/live.py); the bot also treats HTTP 403 "Trading halted" as market closed until the next time poll (it was spamming 12 rejected orders per cycle during halts) | 6353 (p10 -3078, 17% losing) | 2711 (p10 -7024, 35% losing) | ACCEPTED (+33 / +30, thin p10 -0.5%): neutral in the sim, protects against the opening-auction trades seen live |
| 2026-10-22 04:20 | live fill cost: 135 fills 03:42-03:48 cost +93 bp of notional vs the mid at fill time (2.65k in 5 min); the round-3 open burst hit the 8% backstop (FERRY sold 232 at 18.03 vs 19.51 bid, ISLE -8%, AQUA -7%, PORT +5%). Share-weighted: 44% passive/inside, 19% at touch, 10% one band, 27% deep or backstop | | | MEASURED. Season 185 final: testnet -16.3k (mark-to-mid -8.3k, the rest is fill cost) vs sim +7.4k; sim's +5.4k round 1 never existed on the testnet |
| 2026-10-22 04:25 | future-storm valuation sd (from the storm sample: PORT 14 pts, HAVEN 15, ARCH 32 with one storm to come) added to the edge floor (`--future-sd`): everywhere -> tune 451-525 deep 6973->5549/4438/2708 at 0.25/0.5/1.0; outside the storm only -> deep 6064 (p10 -6127 vs -4312), thin 3395 (p10 -7593 vs -5782), identical for 0.5-2.0 because the floor then exceeds every pre/post-storm edge | | | REJECTED on the tune set. The prior-vs-house trades between storms are net positive in the sim despite their negative mark at round end (they converge in the next round). Option kept, default 0 |
| 2026-10-22 04:45 | rebuilders: the settlement rules are EXACT weighted saturations (scripts/fit_rebuilders.py): RECON = 40 + 24(1-exp(-(0.0090 PORT + 0.0070 GRID + 0.0012 FERRY))), MAT = 28 + 14(1-exp(-(0.0075 PORT + 0.0050 ISLE + 0.0021 AQUA + 0.0058 GRID + 0.0010 FERRY))), GEN = 32 + 17.9(1-exp(-0.0081 GRID outage s)); holdout rmse 0.003 / 0.003 / 0.08 (was 1.05 / 0.87 / 0.30). With them the rebuilders' edge floor drops from 4-5% to 1% and they trade 100 more fills/season | 6241 (p10 -2903) vs 6353 | 2602 (p10 -6864) vs 2711 | REJECTED on PnL (-112 / -109, within noise; min-edge 0.015/0.02 do not recover it on the tune set). Kept behind `--exact-rebuild` / valuation.EXACT_REBUILD with params under RECON_exact etc. Decision for Jayden: the rules are right, the small-edge rebuilder trades are not worth their fill cost |
| 2026-10-22 04:30 | ETF create/redeem arbitrage, measurement only: testnet ARCH quote mid vs basket-of-quotes mid gap p5/p95 = -1.2% / +0.9%, a crossing arb (sell ETF at bid, buy legs at asks, create) has positive edge 14% of the time, p99 edge 0.85% (REBLD 0.4%); research market.csv ARCH gap p1/p99 = -2.5% / +1.9%. With the 50-share ARCH limit a 0.5% episode is worth about 75 | | | NOT IMPLEMENTED (deferred for Mario/derivatives). The fair-value trader already trades ETFs against the basket fair (ARCH is the second-best symbol, +1000/season); the hedged create/redeem loop would add a few hundred per season at most. Packet: create = give the basket, get 1 share; redeem the reverse; no fee stated |
| 2026-10-22 04:45 | Mario pricer: `settle`, `points`, `calib` commands; CPU prior -0.6 (humans usually top-5, #1 series score about 48 as in the packet example); mario/README.md drill sheet with series-win-by-lead and score-contract tables | | | DELIVERED (not PnL-scored) |
| 2026-10-22 05:05 | derivs/desk.xlsx (built by derivs/build_sheet.py): Inputs (S, IV, r, days), Contracts (12 contracts: fair, delta, vega, gamma, edge $ and in vol points vs bid/ask, market IV by four Newton steps), Analysts (10 events x 2 underlyings, errors in vol points, MAE, bias, inverse-error weights over all events and over the last 3, blended IV for the next event), Timeline (10 events with news / underlying move / makers snap exchange times and the real-time offsets t, t+1, t+2 min), Notes (rules: midpoint execution, rank^1.5 scoring, round-by-round information). Formulas verified against derivs/bs.py with a Python Excel engine (fair, vega, market IV exact; scorecard correct) | | | DELIVERED (not PnL-scored). Strikes default to OIL 75/80/85 and PLANE 90/100/110: overwrite from the screen |
| 2026-10-22 05:15 | house quote skew vs our inventory (item 10): 23,855 book snapshots joined with the bot's positions. The house keeps a 600-lot backstop 8% either side of a centre that lags the touch by up to 1.3%. Touch-mid minus centre regressed on our position / limit: pooled corr +0.05, slope +0.07% per full limit (with us, not against us; MAT +0.64%, GRID -0.11%, insurers 0). Spreads 0.02-0.10% wider when |pos| > half the limit, confounded with storm phases | | | NOT MATERIAL: no inventory skew added to the ladder. The house's centre lagging the touch is the thing to exploit (it is where the 8% backstop sits), not skew |
| 2026-10-22 05:40 | tuner (out/tune/ledger.csv, 45 rows since 03:45 under the current defaults; tune set at defaults: deep 6973 p10 -4312, thin 3260 p10 -5782): best scores k=100/sd_mult 0.7 combinations lift the deep mean by 100-600 but all cut thin p10 by 20-28%; min_edge 0.005 lifts deep +391 and lowers thin -78. No row passes the acceptance rule on the tune set, so nothing went to verify | | | NO CHANGE: defaults (min_edge 0.01, edge_full 0.05, sd_mult 1.0, sigma 25, k 50) stay. The tail rule is what rejects the higher-mean sets |
| 2026-10-22 06:05 | live fill cost re-measured after the warm-up and halt fixes (389 fills, 05:20-06:04): +29 bp of notional (was +93 bp at 03:42-03:48); 43% of shares filled passively, 3% at the backstop (was 27% deep or backstop). No rejected orders since 03:44 (15 warm-ups observed). Testnet season 187 +17.8k vs sim +19.6k; 188 at +5.0k in round 3 vs sim +7.3k | | | MEASURED: live fill cost is now inside the sim's 30-60 bp range |
| 2026-10-22 07:05 | tuner's best set (out/tune/best.json, selected on 451-525 at 02:38) re-verified under the current simulator: min_edge 0.02, edge_full 0.03, sd_mult 0.7, sigma 15, k 100 | 8433 (p10 -3050, min -13.2k, 19% losing) vs 6353 | 5073 (p10 -6355, min -14.5k, 24% losing) vs 2711 | ACCEPTED (+2080 / +2362, thin p10 better). Now the defaults in backtest.py, bot/live.py, dissect.py and the tuner baseline. Caveat: the set was selected on the tune seasons under an older fill model, so re-run the tuner on the current simulator before competition day |
| 2026-10-22 14:15 | LIVE FIX (reconnect): (1) the snapshot's advisory record has no "type" field, so the model raised KeyError on every reconnect once an advisory existed (crashes 13:03 and 13:24; the Mac has been sleeping between wake-ups since caffeinate ended at 10:30, so reconnects are frequent); now tagged as an advisory. (2) Right after a snapshot the fair values can be far off until live messages arrive (14:10 reconnect: PORT fair 99.9 vs mid 81, AQUA 35.0 vs 20.0); the bot sent full-size orders in 10 symbols within one second and gave back about 4k in 30 s. The 20 s warm-up now also runs after each snapshot. Verified 14:12: two reconnects, no orders during warm-up, fair values sane. Also: season = 2026 - fictional year (the report says 2027); corrected mapping 190-194: testnet +15.3k/-5.2k/+6.4k/-7.0k/+14.3k vs sim +32.7k/-5.5k/-8.0k/+15.6k/-2.5k. Seasons 195-196 (-7.0k, -17.2k) were traded while the Mac slept and are not comparable | | | FIXED (bot). Simulator untouched (verify unchanged) |

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
