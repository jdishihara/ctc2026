# CTC 2026: Hurricane Season toolkit

Offline tooling for the Systematic Equities case of the 2026 Cornell Trading Competition. The plan lives in the
shared Google Doc "CTC 2026 Team Plan".

```
data/            copy of hurricane-season-research (case.json, history/, starter_kit/). history/ is gitignored (214 MB).
ctc/history.py   the organisers' loader (unchanged)
ctc/wind.py      wind field + per-site damage/outage model, parameters in damage_params.json
ctc/valuation.py fair-value rules for all 12 symbols + SeasonModel (feed -> state -> fair), valuation_params.json
ctc/sim.py       offline replay simulator: feed + house prices on the real-time axis, synthetic house quotes, fills, limits
ctc/analog.py    analog track ensemble (library of training storms, advisory confusion matrices, cone likelihood), analog_library.npz
ctc/ladder.py    liquidity ladder fill model (ctc/ladder.json, measured on the testnet by scripts/calibrate_book.py)
ctc/strategies.py FairValueTrader (analog ensemble; passive quoting; warm-up; carry cap between storms) and FinalReportOnly
ctc/storm_sample.npz  1350 historical storms (seasons 1-450) for the future-storm prior
bot/live.py      live bot: wraps the exchange API in the Sim interface and runs FairValueTrader (bot/run_live.sh keeps it up)
scripts/backtest.py       runs a strategy over seasons (the protocol's numbers come from here, see EXPERIMENTS.md)
scripts/dissect.py        PnL per symbol x round, fill PnL by storm phase, what the ensemble believed in the worst seasons
scripts/tune.py           unattended parameter search -> out/tune/ledger.csv
scripts/calibrate_book.py order books (scripts/record_books.py) -> ctc/ladder.json
scripts/build_library.py  rebuilds ctc/analog_library.npz from seasons 1-450
scripts/build_storm_sample.py  rebuilds ctc/storm_sample.npz
scripts/fit_prelim.py     preliminary-report + nowcast combination (valuation_params.json["prelim"])
scripts/fit_rebuilders.py exact RECON/MAT/GEN settlement rules (kept behind --exact-rebuild, see the ledger)
scripts/fit_damage.py, fit_valuation.py, eval_valuation.py, eval_forecast.py   model fits and diagnostics
scripts/mock_exchange.py  replays a season over the exchange's HTTP + WebSocket API, for bot tests without the testnet
mario/desk.py, tap.py, engine.py, pricer.py, contracts.py, mock_exchange.py   Mario Markets desk: reads the exchange through the UI's browser session, prices and ranks every contract (mario/README.md)
derivs/bs.py, derivs/build_sheet.py -> derivs/desk.xlsx   Derivatives calculator and the desk workbook
derivs/drill.py                    Timed event rehearsal for the derivatives desk (news t, S moves t+1 min, makers snap t+2 min)
```

EXPERIMENTS.md holds the evaluation protocol and the ledger of every accepted and rejected change; OVERNIGHT.md the
unattended-session manual.

## Run

Install the runtime dependencies with `python3 -m pip install -r requirements.txt`.
For the regression suite, install `requirements-dev.txt` and run `python3 -m pytest -q`.

```bash
python3 scripts/backtest.py --strategy analog --seasons 526-600                                   # verify, deep regime
python3 scripts/backtest.py --strategy analog --seasons 526-600 --refill 30 --ladder-scale 0.5    # verify, thin regime
python3 scripts/backtest.py --strategy analog --seasons 540 --verbose                             # every fill of one season
python3 scripts/dissect.py --seasons 526-600 --refill 30 --ladder-scale 0.5 --worst 8             # where the losses are
python3 scripts/backtest.py --strategy nowcast --seasons 451-600                                  # constant-velocity baseline (bad under the ladder)
```
Strategy flags (defaults are the accepted configuration): `--passive 0.75` (rest inside the spread when the edge is
small), `--warmup 20` (no trading for 20 s after a round opens), `--max-cross 0.02` (an aggressive order never pays
more than 2% through the touch), `--cone-w 1.0 --cone-s0 20` (the official advisory's cone as a likelihood on the analogs; `--cone-nu` for a Student-t version, `--isl-w` for the island probabilities, rejected), `--carry 0.5` (between storms the position limit is half the exchange limit: the tail of the season PnL is positions carried into the next storm), `--ent-cut 1.2` (do not add while the pattern posterior is near-uniform), `--prior sample|point`, `--future-sd`,
`--loss-limit`, `--exact-rebuild` (the last three are rejected options kept for reference).
Final-phase defaults are `--final-exact --final-edge 0.005 --final-edge-full 0.005`.
They activate only after all three final reports with complete recorded weather;
gaps or snapshot reconstruction keep the conservative settings. Per-symbol
residual-error floors still apply. Use `--no-final-exact` to disable this phase.

The accepted basket overlay uses `--basket-edge 0.01 --basket-participation 0.5`.
It trades ETF/component discrepancies with at most 10 ETF units, sized to half
the displayed external liquidity of each closing leg. It requires fresh books,
reserves action capacity, and restores starting positions after partial fills.
`--basket-edge 0` disables it. Confirmation mean PnL is **9,925.95 deep /
6,412.88 thin**, versus 9,452.36 / 5,993.53 before the overlay. These are
historical simulator results; delay substantially reduces the advantage.
See [full results, stresses and rejected experiments](docs/research-continuation.md).
All five final-review execution findings are fixed; 180 tests pass and 675
post-fix season replays exactly reproduce the frozen results. The live feed
keeps receiving during HTTP work and preserves quote arrival times; timed-out
basket orders are cancelled even when quotes stop arriving.

Live bot (testnet or competition), dry run first:

```bash
pip install -r requirements.txt
python3 bot/live.py --key BOT_KEY --dry-run          # default url https://cornelltradingcompetition.org
zsh bot/run_live.sh                                  # keeps it running, logs to recordings/bot_live.log (pnl every 10 s, SEASON END lines)
```
The bot runs the same FairValueTrader as the backtest (analog ensemble with the cone likelihood, passive 0.75, warm-up 20 s, max-cross 2%, carry 0.5). On each
start it rebuilds the season from the recorder's feed file (`--feed-log`, exact state) and falls back to the exchange snapshot. Prices are
rounded to the 0.01 tick (buys down, sells up). On the testnet the fictional year gives the season: season = 2027 - year (verified by matching storm tracks). The
`SEASON END` log line prints the fictional time of the NEXT season, so the season that just ended is 2026 - that year.
`bot/preflight.py` checks everything that went wrong on the testnet before a start; `bot/stop.sh` is the kill switch.

## Competition day runbook (Hurricane Season bot)

Before the market opens (allow 15 minutes):

```bash
caffeinate -i -t 36000 &                       # keep the Mac awake for 10 h; it slept after the overnight caffeinate expired and the bot missed two seasons
git pull && git status                         # clean tree on main
echo COMPETITION_KEY > .botkey                 # git-ignored; never put the key in a tracked file or a commit
python3 bot/preflight.py                       # must end with 0 failures; WARN on positions or open orders -> bot/stop.sh first
nohup python3 data/starter_kit/record_feed.py --url wss://cornelltradingcompetition.org --key $(cat .botkey) \
      --out recordings/competition.jsonl --symbols PORT,ISLE,AQUA,GRID,FERRY,RECON,MAT,GEN,HAVEN,REIN,ARCH,REBLD > /dev/null 2>&1 &
nohup python3 scripts/record_books.py --key $(cat .botkey) --out recordings/competition_books.jsonl > /dev/null 2>&1 &
FEED_LOG=recordings/competition.jsonl nohup zsh bot/run_live.sh > /dev/null 2>&1 &  # reads .botkey, restarts on a crash, rebuilds the season from the recorder's file on each start, logs to recordings/bot_live.log
tail -f recordings/bot_live.log
```

While it runs, one person watches the log. Every 10 s it prints `t= … r<round> pnl <season pnl> SYM:mid/fair/position`.
What to look for:

- `strategy analog min_edge 0.025 edge_full 0.03 … carry 0.5 … cone_w 1.0 cone_s0 20.0` at start, then `replayed N feed messages of season year Y`: the accepted configuration rebuilt from the recording. Anything else, stop and check the flags and FEED_LOG.
- `final phase exact=True entry=0.005 full=0.005`: accepted final-phase settings;
  these require every weather observation and all three final reports.
- `basket edge=0.01 participation=0.5 max_lot=10`: accepted basket settings;
  missing or invalid order books skip basket entries. The core strategy continues.
- `snapshot processed: warm-up before trading` and `market (re)opened: warm-up`: no orders for 20 s. Fair values in the
  first line after a connect can be far from the mids (the model is still catching up); they should be sane by the second line.
- Round opens: the house re-prices by about 7% from the previous close, stays quiet for 30 s, then moves about 3% over the
  next five minutes. That move is where the season's PnL is made or lost; the bot trades it after the warm-up.
- `HTTP 4xx …` lines: rejections. One or two around a halt are normal; a stream of them means the tick, the limits or the key.
- `ANNOUNCEMENT <symbols>: <headline> -> pausing those symbols; re-anchor to the house mid in 60 s ...`: the model has not
  seen the announcement, so the bot cancels its orders in those symbols and waits. After `--announce-wait` (60 s; the house
  consensus adjusts within about 45 s) it shifts each symbol's fair to the house mid, keeps the model's storm dynamics on top,
  and resumes: `announcement wait over: HAVEN fair anchored to house mid 31.20 (offset -6.35); trading resumes`. No action is
  required. To act sooner, or differently, append a command to `recordings/control.txt` (polled every 3 s, no restart):
  `echo "HAVEN -6%" >> recordings/control.txt` (fair = model x 0.94), `GEN +3` (points), `PORT =61.5` (fair is 61.5 now),
  `resume HAVEN` (announcement judged irrelevant), `clear HAVEN` (drop the adjustment), `pause MAT`, `status`.
  `docs/announcements.md` has the decision sheet; `--announce-wait 0` makes the bot wait for a command instead.
- `disconnected … reconnecting`: fine once; repeated every few seconds means the network or the host.
- Order actions: the bot caps itself at 120 per minute; the team limit is 180, so nobody else trades on the bot's key.

Stop or emergency:

```bash
bot/stop.sh              # kills wrapper and bot, cancels every resting order, prints positions
bot/stop.sh --flatten    # the same, then closes every position three levels into the book
```

Failures seen on the testnet, all fixed, all covered by the preflight or the warm-up: prices not on the 0.01 tick (every order
rejected); the bot running the nowcast instead of the analog ensemble (-14k in one season); full-size orders in all 12 symbols
within a second of a round open or a reconnect (-4k to -16k); a crash on every reconnect once an advisory existed; the Mac
sleeping with positions open.

End-to-end test without the testnet (mock exchange replays season 451 at 25x):

```bash
python3 scripts/mock_exchange.py --season 451 --speed 25 --port 8765 &
python3 bot/live.py --url http://localhost:8765 --ws ws://localhost:8766 --key test
```

The mock's response shapes (positions, open orders, order acks, quote frames) are guesses; fix `bot/live.py`
after the first testnet session if the real API differs.

Seasons 1–450 are for fitting, 451–525 for tuning, and 526–600 for verification.

## Forecast efficiency and execution checks (2026-10-23)

The initial efficiency patch made complete analog forecasts 1.71× faster on the measured three-season workload,
with matching fair values and uncertainty to `1.14e-13` maximum absolute error.
Track matching uses observation ages and caches verified prefixes; damage across
analogs is vectorized. That patch preserved the fitted strategy and parameters;
the continuation below intentionally changes report reconciliation and final trading.

Order replacement now requires confirmed cancellation and refreshed positions.
Failed refreshes, uncertain submissions and malformed acknowledgements block new
orders until reconciliation. Paused symbols cancel existing orders and retry
failures; filled passive quotes can be replenished immediately.

The initial 40-test suite included a local HTTP integration test. Its verification mean PnL
was 9,345.51 deep / 5,927.40 thin, versus 9,343.72 / 5,924.82 at `f4eb4dd`; this
small difference is not evidence of a material new trading advantage. See
[measurements, reproduction commands and remaining limitations](docs/efficiency-results.md).
Remote exchange behavior still needs a supervised testnet check before deploying
this branch.

## Pre-overlay strategy reference (2026-10-23)

The earlier accepted defaults achieved verification means **9,452.36 deep / 5,993.53
thin**, increases of 106.85 / 66.13 over the efficiency patch. Thin p10 worsens
1.14%, within the 10% acceptance limit; deep p10 and the worst season also worsen
slightly. Losing-season counts are unchanged. Peak actions are 41/48 per minute,
below the 120 cap, with zero simulated rejections. That revision had 88 tests.
The current overlay results are [documented separately](docs/research-continuation.md).

Damage reports now redistribute saturated-site damage correctly. Final-round
valuation and sizing use the reduced uncertainty after all reports, gated on
complete weather history. Faster rebalance schedules, smoother sizing and wind
strength conditioning were rejected on tune and remain disabled.

See [full results, rejected experiments and reproduction](docs/competition-results.md)
and [paired season evidence](docs/competition-verification.json). The live PnL
discrepancy still requires actual recordings; use `scripts/audit_account.py` to
reconcile complete own-trade and position exports. No remote orders were placed
while developing this branch.

## What is fitted (holdout numbers)

Wind at a site: `intensity * exp(-1.88 * dist / radius)`. A site closes while wind > 0.146 (from the impact messages).
Damage per storm at a site: `remaining * (1 - exp(-c * sum(wind * 2 s)))`, company damage = weight-sum over sites.
Holdout R² per company: PORT 0.93, ISLE 0.92, AQUA 0.94, GRID 0.86, FERRY 0.87.

Settlement rules (all R² 1.00 unless noted):

| Symbol | Rule |
|---|---|
| PORT | 100 - 0.549 * cum damage - 0.0197 * weighted outage seconds |
| ISLE | 60 - 0.380 * cum damage |
| AQUA | 35 - 0.200 * cum damage |
| GRID | 50 - 0.244 * cum damage - 0.048 * outage seconds |
| FERRY | 25 - 0.050 * cum damage - 0.059 * outage seconds |
| season loss ($M) | 9.0 PORT + 6.0 ISLE + 2.5 AQUA + 7.0 GRID + 1.2 FERRY damage points, per storm |
| HAVEN | 75 at loss <= $400M, linear to 21 at $1,300M |
| REIN | 90 until $1,300M, then -0.035 per $M |
| RECON | 37.3 + 31.5 * (1 - exp(-(PORT+GRID+FERRY damage)/190)), R² 0.94, resid sd 1.05 |
| MAT | 27.2 + 14.4 * (1 - exp(-total damage/204)), R² 0.75, resid sd 0.87 |
| GEN | 30.2 + 4.4 * (1 - exp(-GRID damage/10.6)) + 0.074 * GRID outage seconds, R² 0.99 |
| ARCH, REBLD | basket |

## Simulator assumptions

Liquidity is the ladder measured on the testnet (ctc/ladder.json, 9,900 snapshots per symbol over 22 h): touch spread 0.23-0.32%,
20-80 shares at the touch, a few hundred within 1-3%, and the house's 600-lot backstop about 8% from its (lagging)
centre. Aggressive orders walk the ladder up to their limit price; consumed depth regenerates linearly over `--refill`
seconds (10 s deep, 30 s thin; `--ladder-scale 0.5` halves every size in the thin regime). A resting order fills when
the house re-quotes through it, for the size the house posts at or beyond our price, at our price (measured live: the
house does cross resting orders). 0.25 s latency; limits include resting orders; 300 order actions per minute (bot cap
120); resting orders cleared at each close; ETF create/redeem at marks; 0.01 tick.

Known gaps vs the testnet: no opening phase. Measured on 49 testnet opens (books.jsonl): the book is not thinner after an
open (depth within 1% of mid 330-550 shares in the first minute against 285-410 later), but the opening mid sits 741 bp
(median) from the previous close, is quiet for 30 s, then moves 298 bp (p90 1122 bp) over five minutes. The sim has no
instant round replays either (the testnet replayed one round in a second). Live fill cost after the warm-up fix: 29 bp
of notional (93 bp before it).

## Results (verify seasons 526-600, default parameters, 2026-10-23 03:42)

| Regime | mean PnL | median | p10 | min | losing seasons | fills/season |
|---|---|---|---|---|---|---|
| deep (ladder, refill 10 s) | 9,344 | 9,436 | -145 | -15,910 | 11% | 363 |
| thin (ladder at half size, refill 30 s) | 5,925 | 6,231 | -2,681 | -17,236 | 17% | 900 |

Deep regime by symbol: HAVEN +2708, PORT +1541, ARCH +1384, FERRY +837, GRID +725, AQUA +571, REBLD +543, RECON +453,
ISLE +298, GEN +173, MAT +90, REIN +20. By round: R1 +3160, R2 +2945, R3 +3239. Fill PnL by phase (deep, 75 seasons, marked
at the round end): the storm itself earns everything (+675k, of which +401k in its first 60 s and +174k in the next 60 s;
after 240 s the fills are flat); pre-storm, aftermath and post-report fills are flat to slightly negative (the post-report
rebuilder fills, -8k, are the carry cap paying the spread). The season tail is positions carried into the next storm, not
bad fills (see the ledger, 2026-10-23 02:25). The constant-velocity nowcast loses about 20k per season under the ladder.

## Forecast skill (holdout storms, RMSE of end-of-storm company damage in points, PORT/ISLE/AQUA/GRID/FERRY)

| Storm age | Constant velocity | Analog ensemble (outlook only) | Ensemble + cone (accepted) | Pattern top-1 (outlook only / + cone) |
|---|---|---|---|---|
| 30 s | 24.7 / 11.2 / 14.9 / 11.3 / 10.8 | 17.9 / 8.6 / 10.4 / 7.1 / 7.1 | 16.7 / 7.7 / 9.4 / 6.9 / 6.9 | 70% / 78% |
| 90 s | 23.2 / 10.1 / 14.2 / 10.9 / 10.2 | 14.6 / 5.8 / 7.1 / 6.1 / 6.3 | 13.5 / 5.1 / 6.1 / 5.9 / 5.9 | 88% / 92% |
| 150 s | 22.1 / 8.3 / 9.1 / 9.7 / 8.1 | 11.9 / 4.6 / 5.8 / 5.4 / 5.3 | 11.1 / 4.5 / 5.3 / 5.1 / 4.9 | 92% / 96% |
| 240 s | 13.3 / 4.5 / 5.3 / 5.8 / 5.1 | 9.4 / 3.5 / 3.9 / 4.5 / 4.0 | 9.2 / 3.6 / 3.9 / 4.5 / 3.9 | 95% / 96% |

Official advisories name the true pattern 69% of the time, but their cone is calibrated (error / stated spread median 0.77)
and predicts the storm's position 30-40% better than the ensemble did at 1-2 minutes ahead, so the cone is a likelihood term
on the analogs (`python3 scripts/eval_forecast.py 15 100 shift 1.0 0 20`). The island probabilities are calibrated too but
using them fattens the PnL tail (rejected). With the cone the ensemble prefers sigma 15 and k 100 (sigma 10 or 25 and k 50 lose about 1,100 points of tune score).

## Next

1. Season PnL tail = positions carried into the next storm (carry PnL over 150 seasons: mean about 0, sd 8k; intra-round
   mean +7.8k, p10 -1k). `--carry 0.5` is the accepted compromise; `--carry 0.25` cuts the tail further at about 10% of the mean.
2. Live vs sim on the testnet seasons the bot trades tonight (215 on): compare SEASON END with `scripts/backtest.py --seasons N`
   (deep regime); the bot now logs every fill once (FILL lines) and rebuilds the season from the recording on each start.
3. Exact rebuilder settlement rules with a 3% floor for RECON and MAT (needs its own tune run).
4. ETF create/redeem arbitrage (measured: ARCH quote more than 0.9% from its basket 5% of the time; small, riskless).
5. Live announcements: the bot pauses named symbols, re-anchors to the house mid after 60 s, and takes human adjustments
   from `recordings/control.txt` (bot/control.py, docs/announcements.md). Untested against a real announcement: the
   research seasons have none.
