# Basket continuation 2026-10-23 (Codex)

Frozen at `2ec8d26`: 1% net quoted basket edge, maximum 10 ETF units, capped by
50% of each closing leg's external executable depth. Same fundamental model.
Confirmation means **9925.95 / 6412.88** versus 9452.36 / 5993.53; p10
**512.72 / -2459.40** versus -254.55 / -2712.92. Worst seasons improve in
both regimes; losing counts 7/75 and 13/75. Paired gain intervals
[386.90,566.47] / [283.23,563.94]. Zero normal basket timeouts, rate blocks or
rejections; peak actions 48/56. Three-second delay gains are small and uncertain;
severe+3s mean improves 987.59 -> 1285.44. No live performance claim.

Promoted consistently in launch commands after all PnL gates. All five Important
final-review findings fixed at `73aed77`; 180 tests pass. Nine post-fix comparisons
(675 season replays) exactly reproduce every frozen result row and summary.
There were no Critical or deferred Minor findings. Price timing, direct cone
centering and fixed-lot basket precursors
were rejected under the recorded gates. [Complete evidence and reproduction](docs/research-continuation.md).

---

# Earlier competition continuation 2026-10-23 (Codex)

Frozen tune winner `final_limit` at `2ae7a02`: correct saturated-site report
allocation, exact final valuation, 0.5% entry/full-size final thresholds. The
final phase requires all three reports and complete observed weather; snapshots
and gaps retain conservative settings. Earlier-phase parameters are unchanged.

Verification 526–600 versus `e8d4307`: mean **9452.36 / 5993.53** versus
9345.51 / 5927.40; p10 **-254.55 / -2712.92** versus -147.60 / -2682.24.
Thin p10 deteriorates 1.14%, within the 10% rule. Worst seasons are slightly
worse; losing counts remain 8/75 and 13/75. Paired mean-delta 95% bootstrap
intervals are [49.01,169.82] / [27.37,107.85], conditional on this simulator.
Peak actions 41/48 at the 120 cap, zero rate blocks/rejections.

ACCEPTED as live/backtest/preflight defaults after verification. Faster cadence,
smoother sizing and wind conditioning failed tune gates and remain disabled.
Three important independent-review findings were reproduced with failing tests
and fixed in one pass; the suite has 88 tests and post-review verification
matches every frozen per-season result. The actual exchange accounting gap
remains open pending the requested recordings.

[Experiment table, review rulings, latency stress and reproduction](docs/competition-results.md)
and [paired evidence](docs/competition-verification.json).

---

# Overnight report 2026-10-23 (session 02:05-07:00, Fable; all commits pushed)

## What improved (verify seasons 526-600, deep / thin regime, mean PnL and p10)

| step | deep | thin |
|---|---|---|
| start of night (ladder of 846 snapshots) | 8663 / -2998 | 5301 / -4364 |
| ladder refit from 9,900 snapshots per symbol (new baseline, not a strategy change) | 8718 / -3127 | 5336 / -4302 |
| entropy cut: no adds while the pattern posterior is near-uniform (1.2 nats) | 8747 / -3127 | 5348 / -4297 |
| official advisory cone as a likelihood on the analogs (1.0, spread floor 20) + carry cap 0.5 between storms | 9287 / -271 | 5812 / -2839 |
| min_edge 0.02 -> 0.025 (36-point grid on the tune seasons) | **9344 / -145** | **5925 / -2681** |

Like for like (same simulator): 8718 / 5336 -> 9344 / 5925 (+7% / +11%); losing seasons 17% -> 11% deep, 21% -> 17% thin;
p10 -3127 -> -145 deep, -4302 -> -2681 thin. Tune set 451-525 agrees: 7830 / 4315 -> 8572 / 5154. The single worst season is
2-3k worse (-15.9k / -17.2k vs -12.8k / -14.1k). Every change passed the acceptance rule on the verify set.

## Three findings behind the changes
1. **The season tail is positions carried into the next storm, not bad fills.** In the worst 10 seasons the fills marked to
   their round end sum to about zero while the seasons lose 64-78k. Carry PnL (position at a close x next close - close) has
   a mean of about zero over 150 seasons and an sd of 8k; intra-round PnL has mean +7.8k and p10 -1k. Hence the carry cap.
2. **The forecast office's cone is informative beyond its outlook label.** The label is right 69% of the time, but the cone
   predicts the storm's position 30-40% better than our ensemble did 1-2 minutes ahead and its spread is calibrated. Used as
   a Gaussian likelihood on the analogs: 30 s damage RMSE PORT 17.9 -> 16.7, pattern top-1 70% -> 78% (90 s: 88% -> 92%).
3. **The live bot's model was wrong after every restart.** (a) It carried the previous season's damage across a season
   change (fair values 5-7 points low all of season 214). (b) A snapshot rebuild has no closure history and integrated the
   storm coarsely: fair values off by up to 20 points right after, 2-5 points for the rest of the season. Both fixed: the
   season resets on a change of fictional year, and the bot rebuilds the season from the recorder's feed file on each start
   (exact), with a repaired snapshot fallback (bias 1 point). Also fixed: the fill log repeated every fill ~180 times.

## Rejected (ledger has the numbers)
Cone without the carry cap (+350 more mean but thin p10 -5090, worst season -20k); island probabilities as a likelihood (fattens
the tail in every setting); Student-t cone; wider cone floors; exact rebuilder settlement rules with a 3-4% RECON/MAT floor (+600-700
mean, worse p10); carry 0.35 and 0.25; sd_mult other than 0.7 (sharp optimum); edge_full 0.04; warm-up 10 or 40 s; passive 0.5 or
off; max-cross 1% or 3%; velocity in the analog kernel; cones of all advisories; late-storm no-add; entropy cut at 0.9.

## Testnet vs sim (season = 2026 - the year printed on the SEASON END line; sim = deep regime, current defaults, at settlement)

| season | testnet | sim | note |
|---|---|---|---|
| 214 | +4.2k | n/a | not comparable: traded on the previous season's damage until 02:48, then on a snapshot-rebuilt model |
| 215 | -0.7k (R1 +1.5k, R2 +3.3k, R3 -5.4k) | +2.6k (R1 +2.3k, R2 +4.9k, R3 -4.5k) | first clean season on the new package; shape agrees round by round |
| 216 | +8.3k (R1 +3.8k, R2 +5.0k, R3 -0.5k) | +17.8k (R1 +12.2k, R2 +5.8k, R3 -0.3k) | bot restarted on min_edge 0.025 during round 1 (missed part of the storm) |
| 217 | +7.3k | +7.7k (R1 +2.5k, R2 +4.2k, R3 +1.0k) | clean season, no restart |
| 218 | +2.7k | +13.6k (R1 +3.4k, R2 +9.7k, R3 +0.5k) | clean season |
TESTNET_ROWS_PLACEHOLDER

**Open question (ledger 06:25):** the exchange's realized PnL runs 2-3k per season below an average-cost replay of its own
trade list (positions and unrealized match exactly); that gap is the size of the live-vs-sim shortfall in round 3. Live
rounds 1-2 earn 65% of the sim (29.4k vs 44.9k over seasons 215-218); live round 3 -11.8k vs sim -3.3k.

Live fill cost tonight: +29 bp of notional over 599 fills, 40% of notional at or better than mid (same as yesterday, inside the
simulator's 30-60 bp). Testnet round opens within a season gap only 50-90 bp from the previous close (yesterday's 741 bp
figure mixed in season boundaries), so the simulator's no-gap assumption is close.

## Deliverables
- scripts/grid.py (deterministic grid on the tune seasons, verifies the top configurations); bot/live.py `--feed-log` (run_live.sh
  passes it; FEED_LOG=recordings/competition.jsonl on the day); preflight prints the full parameter set.
- Derivatives: `derivs/bs.py convert` and a Round3 sheet in desk.xlsx (variance, daily/weekly vol, expected move, ATM straddle
  -> IV); a bias-corrected inverse-variance analyst blend in the Analysts sheet (stress test: 2.15 vs 2.30 vol points RMSE
  with biased analysts; following the single best analyst is the worst choice).
- Mario: pricer calibration validated (race-winner Brier 0.65 vs 0.75 uniform after two races), note in mario/README.md.

## Top three decisions for Jayden
1. **How much to carry between storms.** Carry 0.5 is now the default (accepted as a package with the cone). Over 150 seasons
   the carried positions earn about nothing and are all of the tail. Options: keep 0.5; 0.25 cuts the tail further at about
   10% of the mean; 1.0 (no cap, cone alone) adds about 350/season of mean with p10 -5k and a -20k worst season. Pick by how
   much a bad single season would cost the overall rank (Systematic Equities is 45% of it).
2. **Exact rebuilder rules.** `--exact-rebuild --rebuild-min-edge 0.03` adds +700 deep / +475 thin of mean and improves the
   worst season by 4k, but p10 falls (-871 / -3925 vs -145 / -2681). Rejected by the rule; a legitimate alternative if you
   prefer mean over p10.
3. **Competition-day start order.** Start record_feed.py BEFORE the bot (the runbook does), so that any restart rebuilds the
   season from the recording; without the recording the bot falls back to the snapshot (1-point bias). Also decide who
   watches the first minute of each round and the announcement pauses.

Still running at 07:00: feed recorder, book recorder, live bot (defaults as above), caffeinate (until 12:07). Nothing deleted,
no history rewritten, key not in the repo.

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
| 2026-10-23 | live announcements: pause, re-anchor fair to the house mid after 60 s (`--announce-wait`), human commands via `recordings/control.txt` (bot/control.py) | unchanged | unchanged | not a strategy change: research seasons have no announcements; season 451 replay identical (12008); 186 tests; decision sheet in docs/announcements.md |
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
| 2026-10-22 14:15 | LIVE FIX (reconnect): (1) the snapshot's advisory record has no "type" field, so the model raised KeyError on every reconnect once an advisory existed (crashes 13:03 and 13:24; the Mac has been sleeping between wake-ups since caffeinate ended at 10:30, so reconnects are frequent); now tagged as an advisory. (2) Right after a snapshot the fair values can be far off until live messages arrive (14:10 reconnect: PORT fair 99.9 vs mid 81, AQUA 35.0 vs 20.0); the bot sent full-size orders in 10 symbols within one second and gave back about 4k in 30 s. The 20 s warm-up now also runs after each snapshot. Verified 14:12: two reconnects, no orders during warm-up, fair values sane. Also: the SEASON END log line prints the NEXT season's fictional year, so season = 2026 - printed year there, while a running season is 2027 - year (storm tracks matched 15:20; the report's rule was right). Comparison 190-194: testnet +15.3k/-5.2k/+6.4k/-7.0k/+14.3k vs sim +32.7k/-5.5k/+4.6k/-8.0k/+15.6k (sim column fixed 15:10; an earlier version of this row had it shifted by one season). Seasons 195-196 (-7.0k, -17.2k) were traded while the Mac slept and are not comparable | | | FIXED (bot). Simulator untouched (verify unchanged) |
| 2026-10-22 14:30 | MEASURED round opens from recordings/books.jsonl (49 opens x 12 symbols, 5 s snapshots): the house's book is NOT thin after an open (depth within 1% of mid 330-550 shares in the first minute vs 285-410 later; spread 22 bp vs 27-38 bp later; halts last 120 s). What changes is the price: the opening mid sits 741 bp (median; p90 2403 bp) from the previous close, is quiet for 30 s (8-9 bp per 30 s), then moves 40-45 bp per 30 s for the next 5 minutes (298 bp median, p90 1122 bp, max 4500 bp by +300 s) | | | FINDING. The opening losses are about the direction of that 300 bp move, i.e. whether our fair is right at the open, not about book depth; the 20 s warm-up protects against our own model being stale (as after a snapshot), not against the house. No change to the warm-up length |
| 2026-10-22 14:45 | fair-jump guard: skip a symbol for one cycle when its fair moved more than X since the previous cycle (`--fair-jump X`, default 0 = off; strategies.py, backtest.py). Motivation: after the 14:10 reconnect the first fair values were 20% off for one cycle | X=0.02: 6531 (p10 -4608); 0.05: 7108 (p10 -4343); 0.10: 7799 (p10 -3050) vs 8433 (p10 -3050) off | 0.02: 3803 (p10 -7882); 0.05: 4119 (p10 -7314); 0.10: 4516 (p10 -6139) vs 5073 (p10 -6355) off | REJECTED (-630 / -560 even at 10%): large fair moves in the sim are real news (damage reports, track updates) and the trade is worth most on the first cycle after them. Flag kept off; the snapshot warm-up (dbfaab8) covers the reconnect case |
| 2026-10-22 14:50 | bot/preflight.py (17 checks: key git-ignored and absent from tracked files, host whitelist, tick rounding, clean tree, modules, ladder age, strategy defaults, caffeinate, no second bot, disk, case file, exchange time, positions flat, no resting orders, market data flowing, sim smoke run) and bot/stop.sh (kill wrapper and bot, cancel all orders, print positions, `--flatten` closes positions three levels into the book) | | | DELIVERABLE. Preflight against the testnet at 14:39: 16 pass, 1 warn (uncommitted changes), 0 fail. Would have caught last night's tick bug and the nowcast-by-default bug |
| 2026-10-22 14:55 | derivs/drill.py: timed rehearsal of a derivatives event with the packet's clock (news at t, underlying moves at t+1:00 with makers repricing delta only, makers snap to the true IV at t+2:00), midpoint fills, rounds 1-3 (announced IV / three analysts with persistent bias and sd / 1-day expected move), per-event PnL, edge captured vs perfect foresight, seconds to first trade, best three trades shown afterwards; `--fast` 15 s phases, `--auto` self-test, logs to out/drill/ | | | DELIVERABLE for the humans (no bots in that case). Self-test passes |
| 2026-10-22 15:10 | testnet vs sim, seasons 187-194 (season = 2027 - fictional year; SEASON END lines print the next season's year; bot after the warm-up fix): sign agrees 8 of 8; testnet +51.7k vs sim +75.1k (69%); per season 187 +17.8k/+19.6k, 188 +4.9k/+7.3k, 189 +3.0k/+8.8k, 190 +15.3k/+32.7k, 191 -5.2k/-5.5k, 192 +6.4k/+4.6k, 193 -7.0k/-8.0k, 194 +16.5k/+15.6k (194 re-marked at settlement). Live round-3 increments looked bad (191 -10.6k, 193 -9.3k) but the sim loses those rounds too (R3 -8.6k, -11.0k): no round-3 anomaly. Re-marking live end-of-season positions at settlement.json instead of the last mid moves the numbers by under 100 except 194 (+2.3k, HAVEN mid 26.10 vs settlement 21.00, ARCH 259 vs 240: the house had not converged) | | | FINDING. The simulator is faithful in sign and roughly in size; the shortfall sits in the biggest winners (190). Next: compare fills in 190 live vs sim |
| 2026-10-22 15:55 | Why live made +15k in season 190 where the sim makes +33k (all in round 2: live +4.0k vs sim +20.5k; rounds 1 and 3 agree). Checked three suspects. (1) Model state after the 07:01 mid-season restart: replaying the recorded feed through the model from the season start and from the 07:01 snapshot gives identical fair values from 2 minutes after the snapshot on, and the live log's fair values match the full-feed replay to the cent, so the snapshot rebuild is sound. (2) House reaction to the final report: the testnet house re-priced HAVEN 29.1 -> 34.2 within 4-8 s of the report and the history price file does the same (28.86 -> 34.23 at +4 s), so the sim is not trading against a slower house than the real one. (3) Our fills: the public trade tape shows our 500-lot HAVEN buy at 07:25:57.5-57.7 filled 165 at 29.10-29.34 and the rest at 31.43 (the 600-lot backstop, +7.7%), exactly the ladder model's fill; we then sold 348 at 34.24-34.34, a profitable round trip. Yet the exchange's running pnl fell 11.4k in those 10 s while mark-to-mid on held positions moved 0.8k | | | FINDING. Model and fill model are faithful; the unexplained item is the exchange's own realized/unrealized accounting during flips, which the bot cannot audit because it never logged fills. The bot now polls /trades every sync and logs FILL lines with price, size, mid and slippage in bp (dry-run tested). Tonight's run will show whether the SEASON END numbers (which are the exchange's) are consistent with the fills |
| 2026-10-22 16:05 | max-cross cap: an aggressive order never pays more than X through the touch (buy limit <= ask*(1+X), sell limit >= bid*(1-X); `--max-cross X`, strategies.py, backtest.py, live.py). Motivation: the season-190 tape showed our 500-lot HAVEN sweep taking 335 lots at the 600-lot backstop 7.7% above the touch; the limit fair/(1+keep) lets a big-edge order walk the whole book | X=0.02: 8663 (p10 -2998, 17% losing); 0.03: 8614 (p10 -3025); 0.05: 8519 (p10 -3050) vs 8433 (p10 -3050) off | 0.02: 5301 (p10 -4364, 21%); 0.03: 5266 (p10 -4464); 0.05: 5089 (p10 -4805) vs 5073 (p10 -6355) off | ACCEPTED at 0.02 (+230 / +228, thin p10 up 31%). Tune set 451-525 agrees: 0.02 7823 / 4258 vs 7659 / 3885 off and 7786 / 4161 at 0.03. Default is now 0.02 everywhere (backtest, live bot, dissect, preflight). The running tuner picks the backtest default up through its subprocess, so its ledger rows after 16:03 (row 40 on) are scored with the cap; the 39 earlier rows without it, none of which beat the accepted set |
| 2026-10-23 02:20 | ladder refit from 9,900 book snapshots per symbol (22 h of testnet, 14:17-02:07 with no bot of ours running, so other participants' liquidity only) instead of 846; spreads and top-of-book sizes identical to 0.01% / a few shares, only the 600-lot backstop bin moves between 8% and 9% for some symbols | 8718 (p10 -3127, min -12.8k, 17% losing) vs 8663 | 5336 (p10 -4302, min -14.1k, 21% losing) vs 5301 | NEW BASELINE (not a strategy change; +55 / +35, inside noise). The liquidity measured yesterday was already representative |
| 2026-10-23 02:25 | WHERE THE TAIL IS (dissect.py + carry decomposition, verify 526-600 deep): in the worst 10 seasons the fills marked to their round end sum to -73 (thin: +2338) while those seasons lose -64k (-78k): the losses are positions carried across a round boundary into the next storm. Decomposition per season: carry PnL (position at close r x close r+1 - close r) mean +903, sd 8151, p10 -8029, min -21.8k; intra-round PnL mean +7815, sd 8323, p10 -1049. On the tune set 451-525 the carry is NEGATIVE: mean -772, sd 8456, p10 -11.0k, intra-round +8602 (p10 +1166). Over 150 seasons the carry has about zero expected value and all of the tail. The overnight gap (close r -> open r+1) is zero in the research prices and 50-90 bp on the testnet within a season (yesterday's 741 bp figure mixed in season boundaries, which jump 5-20%) | | | FINDING |
| 2026-10-23 02:25 | carry cap: between storms (after a final report, before the next storm forms) the position limit is carry x the exchange limit; positions above it are reduced paying the spread (`--carry`, strategies.py, backtest.py, bot/live.py, default 1.0 = off). Verify: 0.75 -> 8590 (p10 -2877, min -10.7k, 15% losing); 0.5 -> 8193 (p10 -2531, min -9.3k, 13%); 0.25 -> 7560 (p10 -2298); 0 -> 6246 (p10 -1541, min -6.3k) | vs 8718 (p10 -3127, min -12.8k, 17%) | 0.75 -> 5365 (p10 -3358, min -12.9k); 0.5 -> 4995 (p10 -2721, min -10.7k, 20%); 0.25 -> 4306 (p10 -2926); 0 -> 3232 (p10 -1891) vs 5336 (p10 -4302, min -14.1k, 21%) | REJECTED BY THE RULE (verify mean -525 / -341 at 0.5) but tune set 451-525 at 0.5: deep 7767 vs 7830 (p10 -1916 vs -3993, losing 13% vs 20%), thin 4512 vs 4315 (p10 -3663 vs -6758, losing 27% vs 32%). Over 150 seasons carry 0.5 costs about 3% of the mean and halves the tail. DECISION FOR JAYDEN: the competition is one season, scored by rank; flag kept off by the protocol, recommended on (0.5) |
| 2026-10-23 02:25 | entropy cut: do not add to a position while the pattern posterior's entropy exceeds 1.2 nats (near-uniform over the 6 outlooks; storm-phase fills at entropy > 1.2 earned +20 bp deep and -122 bp thin) (`--ent-cut 1.2`, now the default; 0.9 tested: +13 / +5) | 8747 (p10 -3127) vs 8718 | 5348 (p10 -4297) vs 5336 | ACCEPTED (+29 / +12, inside noise, passes the rule; no change to the tail) |
| 2026-10-23 02:48 | LIVE FIXES (bot/live.py): (1) the bot started at 02:07 inside a season transition; its first snapshot still described the previous season (1814) and that season's round-1 damage was carried into season 1813 (no storm_formed with a smaller round had been seen, and the competition id did not change after the first poll), so fair values ran 5-7 points low all season (GRID fair 30.7 vs 36.1 after a restart). Now a change of fictional year on any message, or a round-1 storm_formed with state present, resets the model. (2) /trades ignores its cursor and returns the latest 100: the same 238 fills were logged 43,576 times; FILL lines are now deduped by trade id and carry the exchange's executed_at time. (3) Snapshot rebuild measured against a full-feed model on tonight's recorded season: fair values differed by up to 20 points (PORT) / 50 (ARCH) right after the rebuild and by 2-5 points (PORT, GRID, FERRY, GEN) for the rest of the season, because the damage report gives no closure seconds, earlier damage is spread evenly over sites, and the 40-point track was integrated coarsely at intensity 1.0. Now: `--feed-log` replays the recorder's file for the current season on start (exact state; run_live.sh passes recordings/testnet.jsonl, FEED_LOG=recordings/competition.jsonl on the day), and the snapshot fallback interpolates the track to 2 s, uses the storm's intensity and books 1.7-2.3 closure seconds per damage point (storm_sample fit): residual bias before the final report 1 point (GRID 1.1, FERRY 1.1, GEN 1.1, ARCH 4.4; was 4.8 / 4.6 / 5.4 / 16.2) | | | FIXED. Season 1813 (= 214) is not comparable with the sim (traded on stale damage until 02:57, then on a snapshot-rebuilt model until 02:48) |
| 2026-10-23 02:40 | FINDING: the official advisory's cone and island probabilities are informative beyond its outlook label (holdout storms 451-530). Cone position error vs the ensemble's mean position vs constant velocity, RMSE in map units: 0-45 s ahead 16 / 30 / 23; 45-75 s 34 / 56 / 51; 75-135 s 68 / 102 / 115; 200-300 s 147 / 177 / 274. Cone error / stated spread: median 0.77, p90 1.52 (calibrated). Island probabilities are calibrated (stated 0.5-0.6 -> observed 0.67, 0.8-0.9 -> 0.84, 0.9-1.0 -> 0.99). The ensemble had used only the outlook label (right 69% of the time) | | | FINDING |
| 2026-10-23 02:55 | cone likelihood in the analog weights: each future cone point (age, x, y, spread) of the latest official advisory multiplies the weight of analog i by exp(-d_i^2 / (2 (spread^2 + s0^2))) with d_i the distance of the shifted analog track at that age (`--cone-w`, `--cone-s0`; `--cone-nu` for a Student-t version). Forecast skill at 30 s: PORT damage RMSE 17.9 -> 16.7 points, ISLE 8.6 -> 7.8, AQUA 10.4 -> 9.4, pattern top-1 70% -> 77%; at 90 s 88% -> 93%; the ensemble becomes over-confident (|err|/sd 0.9-1.0 -> 1.2-1.4). Tune set 451-525 (score = half the mean of the two regimes + half the thin p10; baseline deep 7830 / thin 4315, p10 -3993 / -6758, score 2693): cone 1.0 s0 10: 8480 / 4880 (p10 -2869 / -4749) score 4305; s0 20: 8591 / 4953 (-2996 / -4784) 4380; s0 30: 8453 / 4861, 4231; cone 0.5: 8138 / 4752 (p10 -5704 / -6424) 3233; cone 2.0: 8755 / 5072 (-4953 / -6740) 3543; cone 1.0 + sd_mult 1.0: 6568 / 3643; + min_edge 0.025: 8337 / 4911, 4056; Student-t nu 3/5/10: 8589-8660 / 4931-4980, 4100-4300; island probabilities as a Bernoulli likelihood (`--isl-w 1.0`, hit = analog gives hurricane conditions on the island): 8735 / 4990 but p10 -6094 / -8398 | cone 1.0 s0 20 alone: 9631 (p10 -1563, min -18.2k, 17%) vs 8747 (p10 -3127, min -12.8k) | 6285 (p10 -5090, min -20.4k, 23%) vs 5348 (p10 -4297, min -14.1k) | Cone alone: +884 / +937 (+10% / +18%) but thin verify p10 -18% -> fails the rule on its own. Pooled 150 seasons (cone 1.0 s0 10): deep +790 (se 314), thin +746 (se 306), p10 better in both, p5 worse (-9.3k vs -7.5k), 64% of seasons improve. The island term fattens the tail in every setting: REJECTED |
| 2026-10-23 03:03 | ACCEPTED PACKAGE: cone 1.0, s0 20 AND carry 0.5 (the carry cap limits what rides on the next storm; the cone adds mean inside the storm). Tune 451-525: deep 8573 (p10 -1238, 16% losing) / thin 5101 (p10 -3909, 27%) vs 7830 / 4315, score 4882 (best of everything tried) | 9287 (p10 -271, min -15.0k, 11% losing) vs 8747 (p10 -3127, min -12.8k, 17%) | 5812 (p10 -2839, min -17.8k, 17% losing) vs 5348 (p10 -4297, min -14.1k, 20%) | ACCEPTED (+540 / +464, thin p10 up 34%, losing seasons 17 -> 11% / 20 -> 17%; the single worst season is 2-4k worse). Defaults everywhere (backtest, bot/live.py, preflight, dissect); the live bot restarted on them 03:03 in season 215 round 1. ALTERNATIVE for Jayden: cone without the carry cap = +350 more mean per season but p10 -5090 and worst season -20k |
| 2026-10-23 03:08 | exact rebuilder settlement rules (`--exact-rebuild`) with a RECON/MAT/GEN edge floor (`--rebuild-min-edge`), on top of the accepted cone + carry package. Tune 451-525: floor 0 -> 8730 / 5170 (p10 -2802 / -5052); 0.03 -> 9273 / 5461 (p10 -2850 / -4964); 0.04 -> 9207 / 5465 (p10 -2752 / -4759) vs 8573 / 5101 (p10 -1238 / -3909) | 0: 9427 (p10 -1147, min -11.4k); 0.03: 10013 (p10 -871, min -10.8k, 13%); 0.04: 9894 (p10 -648, min -10.4k, 12%) vs 9287 (p10 -271, min -15.0k, 11%) | 0: 5847 (p10 -3990); 0.03: 6287 (p10 -3925, min -13.2k, 19%); 0.04: 6249 (p10 -3410, min -13.1k, 19%) vs 5812 (p10 -2839, min -17.8k, 17%) | REJECTED by the rule (thin p10 -20% at the 0.04 floor, -38% at 0.03) although the mean rises +600-700 / +440-475 and the worst season improves by 4k: the exact rules make RECON/MAT trade at 3-4% edges at full size, and those positions widen the tail. Option kept; third candidate for Jayden |
| 2026-10-23 03:08 | Mario pricer calibration (300 simulated series from its own generative model, CPU prior -0.6): race-winner Brier after 1 / 2 / 3 races 0.69 / 0.65 / 0.64 (uniform 0.75); series-winner Brier 0.50 / 0.34 / 0.21; reliability after two races: predicted 0.15-0.25 -> 0.22 observed, 0.25-0.35 -> 0.30, 0.35-0.50 -> 0.40, 0.50+ -> 0.60 (n=87). Likelihood temperature 4 / 8 / 16 / 32 changes the Brier by under 0.01 | | | VALIDATED, no change (temperature stays 8) |
| 2026-10-23 03:42 | focused grid (scripts/grid.py, 36 combinations on 451-525: min_edge 0.015/0.02/0.025 x edge_full 0.03/0.04 x sd_mult 0.5/0.7/0.85 x carry 0.35/0.5, 25 min with 6 workers). sd_mult 0.7 is a sharp optimum (0.5 and 0.85 lose 1-4k of score), carry 0.5 beats 0.35 everywhere, edge_full and min_edge matter little. Top: min_edge 0.025 score 5014 (deep 8572 p10 -1581, thin 5154 p10 -3699) vs the accepted 0.02 at 4882 | 9344 (p10 -145, min -15.9k, 11%) vs 9287 (p10 -271) | 5925 (p10 -2681, min -17.2k, 17%) vs 5812 (p10 -2839) | ACCEPTED min_edge 0.025 (+57 / +113, inside noise but passes the rule on both sets); edge_full 0.04 with min_edge 0.02 verifies at 8891 / 5610 (rejected). Default in backtest, bot, preflight, dissect, tune baseline |
| 2026-10-23 03:44 | derivatives analyst weighting, stress test (4000 simulated games, analysts publish from event 4, truth after each event; biases ~ N(0, 2 vol pts), noise sd 1.5-5 pts, redrawn per game). RMSE of the blended IV over events 5-10: equal 2.28, median 2.56, inverse-MAE (the sheet) 2.30, inverse-MAE over the last 3 events 2.33, follow-the-best-analyst 3.41, bias-corrected inverse-variance (subtract each analyst's mean error shrunk by k/(k+1), weight by 1 / (residual variance + 0.03^2/(k+1))) 2.15. With biases of 4 pts: 3.06 / 3.50 / 2.84 / 2.88 / 4.05 / 2.26. With no bias: 1.97 / 2.13 / 1.99 / 2.02 / 2.95 / 2.11 | | | DELIVERED: bias-corrected blend added to the Analysts sheet next to the inverse-MAE one; never follow a single analyst; equal weights are fine until two truths are known |
| 2026-10-23 04:05 | grid 2 (27 combinations on 451-525 at the accepted set): passive 0.5 / 0.75 / 1.0 (off) x warm-up 10 / 20 / 40 s x max-cross 1 / 2 / 3%. Top score 5014 = the accepted set (passive 0.75, warm-up 20, max-cross 0.02); warm-up 40 s 4989 (verify 9264 / 5853 vs 9344 / 5925); warm-up 10 s 4862; max-cross 0.03 4808; 0.01 4732; every passive 0.5 or 1.0 row scores below 4660 | | | NO CHANGE: the accepted execution parameters are a local optimum under the new model |
| 2026-10-23 04:08 | velocity in the analog kernel (`--vel-w`, `--vel-sd`: current vx, vy vs the analog's velocity at the same age; library speeds 1.8-1.9 units/s, sd of vx across analogs 0.6-0.9): forecast skill with the cone at age 30 s PORT / ISLE / AQUA RMSE 16.7 / 7.8 / 9.5 (w 0.5), 16.6 / 7.9 / 9.6 (w 1.0) vs 16.7 / 7.7 / 9.4 without; at 90 s 13.8 / 13.6 / 14.1 vs 13.5, pattern top-1 unchanged (77%) | | | REJECTED at the skill stage (no PnL run): the position kernel already carries the velocity. Option kept, default 0 |
| 2026-10-23 04:30 | cones of ALL official advisories so far instead of the latest only (`--cone-all`): forecast skill at 90 s PORT 14.2 vs 13.5, pattern top-1 91% vs 92%; at 30 s unchanged | | | REJECTED at the skill stage: older cones are stale. Option kept, off |
| 2026-10-23 04:40 | late-storm no-add (`--late-cut` s: do not add to a position once the storm is older than this; fills after 240 s earn about nothing): 300 s -> verify 9336 / 5887, tune 8572 / 5151; 360 s -> 9336 / 5914, tune 8579 / 5154 vs 9344 / 5925 and 8572 / 5154 | | | NO CHANGE (within +-40 everywhere): the late fills are cheap passive ones. Option kept, off |
| 2026-10-23 05:05 | grid 3 (sigma 10 / 15 / 25 x k 50 / 100 / 200 at the accepted set, tune 451-525): sigma 15 / k 100 keeps the top score 5014; k 200 4894 (verify 9139 / 5871, p10 +32 / -2045); sigma 25 with k 200 4690, with k 100 3863 (thin p10 -6206); sigma 10 about 3840; k 50 3420. Under the cone the ensemble is no longer insensitive to sigma: 10 and 25 both lose about 1,100 points of score | | | NO CHANGE |
| 2026-10-23 06:05 | grid 4 (cone_w 0.75 / 1.0 / 1.25 / 1.5 x cone_s0 15 / 20 / 30 at the accepted set, tune 451-525): (1.0, 20) keeps the top score 5014; (1.5, 30) 4873 verifies at 9487 / 6013 (p10 +489 / -2037, min -16.7k / -18.1k) vs 9344 / 5925; (0.75, 15) 4840; (1.0, 15) 4815; (1.5, 20) 4798 | | | NO CHANGE by the protocol (selection on the tune set); (1.5, 30) is a near-equivalent alternative |
| 2026-10-23 06:25 | EXCHANGE PnL vs FILLS (seasons 217, 218): the bot's deduped FILL lines reproduce the exchange's positions exactly and the unrealized leg within 70, but the exchange's REALIZED PnL is below an average-cost replay of the same trades: 217 +6053 vs +9364 (-3.3k, -81 bp of notional), 218 +3775 vs +5731 (-2.0k, -34 bp). Fills marked at settlement: 217 +10.6k, 218 +4.7k vs exchange totals +7.3k, +2.7k. Live rounds 1-2 sum to 65% of the sim (29.4k vs 44.9k over 215-218) and live round 3 loses 11.8k vs the sim's -3.3k; the exchange-side gap is of the same size as the round-3 shortfall | | | OPEN. Not fees (not proportional), not missing fills, not the mark. The bot now logs per-symbol realized and average price at SEASON END; scratch script realized_check.py compares per symbol mid-season. Suspect: how the exchange books position flips |
| 2026-10-23 16:00 | MARIO DESK (packet update: bots allowed for Mario, no API key). Checked in Chrome: the trading UI calls the same /api/v1 endpoints as the bot API with the login cookie (orderbook/positions/orders/trades/symbols), 401 without it. Built mario/desk.py: Playwright drives its own Chrome window (log in once), polls the books inside the page, prices all 46 contracts (pricer.fairs), engine ranks riskless arbs (sets of 4 binaries vs 100, top-2 = #1 + #2, hard bounds from banked points) and fair +- margin edges sized to the book and limits, dashboard on localhost:8787, results typed in. mario/mock_exchange.py drill: taking the top 3 actions every 3 s over 6 races +6.5k in the mock's marks (+2.5k realized). Browser tap verified against the mock page; --prefill (types the order into the UI form, human clicks) exists but is off pending a rules check | | | DELIVERED (not PnL-scored) |

## 2026-10-23 — Codex / Arjun: forecast efficiency and execution reconciliation

Reference `f4eb4dd`. Complete forecasts: 1,419 calls per version, tune seasons
451/470/500, three repeats, 8,235.53 -> 4,817.48 ms (**1.71x**), maximum fair/SD
difference 1.14e-13. Age-aligned matching, verified-prefix caching, tie-preserving
partition and vectorized damage; no fitted parameters or strategy defaults changed.

Cancellation success is explicit and reconciles racing fills before replacement;
uncertain accounts block orders; paused symbols cancel/retry; pending simulated
orders reserve capacity; fully filled passive quotes can be replenished. Tune
451–525 mean deep/thin: 8,572.12 / 5,154.10 -> 8,577.71 / 5,155.03. Verify 526–600:
**9,343.72 / 5,924.82 -> 9,345.51 / 5,927.40**. Verify p10 deep/thin:
-144.98 / -2,680.86 -> -147.60 / -2,682.24; thin p10 worsens **0.052%**, within
the 10% bound. Both means rise, satisfying the repository's acceptance rule;
the changes are too small to claim a material new trading advantage.

40 regression/integration tests pass. Independent review's four important findings
were reproduced and fixed. Minor fractional-age exposure-duration issue deferred
(the supplied dense history has two-second steps). No remote orders or deployment.
Full measurements, tails, review rulings and commands: [efficiency results](docs/efficiency-results.md).

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
10. Mario desk: symbol mapping on the day (map command), rate limit of the book polling, prefill rules check; Derivatives Black-Scholes sheet.
