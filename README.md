# CTC 2026: Hurricane Season toolkit

Offline tooling for the Systematic Equities case of the 2026 Cornell Trading Competition. The plan lives in the
shared Google Doc "CTC 2026 Team Plan".

```
data/            copy of hurricane-season-research (case.json, history/, starter_kit/). history/ is gitignored (214 MB).
ctc/history.py   the organisers' loader (unchanged)
ctc/wind.py      wind field + per-site damage/outage model, parameters in damage_params.json
ctc/valuation.py fair-value rules for all 12 symbols + SeasonModel (feed -> state -> fair), valuation_params.json
ctc/sim.py       offline replay simulator: feed + house prices on the real-time axis, synthetic house quotes, fills, limits
ctc/analog.py    analog track ensemble (library of training storms, advisory confusion matrices), analog_library.npz
ctc/ladder.py    liquidity ladder fill model (ctc/ladder.json, measured on the testnet by scripts/calibrate_book.py)
ctc/strategies.py FairValueTrader (analog ensemble; passive quoting; warm-up) and FinalReportOnly
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
mario/pricer.py, mario/README.md   Mario Markets Monte Carlo pricer and drill sheet
derivs/bs.py, derivs/build_sheet.py -> derivs/desk.xlsx   Derivatives calculator and the desk workbook
derivs/drill.py                    Timed event rehearsal for the derivatives desk (news t, S moves t+1 min, makers snap t+2 min)
```

EXPERIMENTS.md holds the evaluation protocol and the ledger of every accepted and rejected change; OVERNIGHT.md the
unattended-session manual.

## Run

```bash
python3 scripts/backtest.py --strategy analog --seasons 526-600                                   # verify, deep regime
python3 scripts/backtest.py --strategy analog --seasons 526-600 --refill 30 --ladder-scale 0.5    # verify, thin regime
python3 scripts/backtest.py --strategy analog --seasons 540 --verbose                             # every fill of one season
python3 scripts/dissect.py --seasons 526-600 --refill 30 --ladder-scale 0.5 --worst 8             # where the losses are
python3 scripts/backtest.py --strategy nowcast --seasons 451-600                                  # constant-velocity baseline (bad under the ladder)
```
Strategy flags (defaults are the accepted configuration): `--passive 0.75` (rest inside the spread when the edge is
small), `--warmup 20` (no trading for 20 s after a round opens), `--max-cross 0.02` (an aggressive order never pays
more than 2% through the touch), `--ent-cut 1.2` (do not add while the pattern posterior is near-uniform), `--carry 1.0` (between storms, position limit as a fraction of the exchange limit; 0.5 halves the tail at 3% of the mean, off by the protocol, see the ledger), `--prior sample|point`, `--future-sd`,
`--loss-limit`, `--exact-rebuild` (the last three are rejected options kept for reference).

Live bot (testnet or competition), dry run first:

```bash
pip install "websockets>=14"
python3 bot/live.py --key BOT_KEY --dry-run          # default url https://cornelltradingcompetition.org
zsh bot/run_live.sh                                  # keeps it running, logs to recordings/bot_live.log (pnl every 10 s, SEASON END lines)
```
The bot runs the same FairValueTrader as the backtest (analog ensemble, passive 0.75, warm-up 20 s, max-cross 2%). Prices are
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
nohup zsh bot/run_live.sh > /dev/null 2>&1 &  # reads .botkey, restarts the bot on a crash, logs to recordings/bot_live.log
tail -f recordings/bot_live.log
```

While it runs, one person watches the log. Every 10 s it prints `t= … r<round> pnl <season pnl> SYM:mid/fair/position`.
What to look for:

- `strategy analog min_edge 0.02 edge_full 0.03 …` at start: the accepted configuration. Anything else, stop and check the flags.
- `snapshot processed: warm-up before trading` and `market (re)opened: warm-up`: no orders for 20 s. Fair values in the
  first line after a connect can be far from the mids (the model is still catching up); they should be sane by the second line.
- Round opens: the house re-prices by about 7% from the previous close, stays quiet for 30 s, then moves about 3% over the
  next five minutes. That move is where the season's PnL is made or lost; the bot trades it after the warm-up.
- `HTTP 4xx …` lines: rejections. One or two around a halt are normal; a stream of them means the tick, the limits or the key.
- `ANNOUNCEMENT <symbols>: <headline> -> pausing those symbols`: the bot stops trading them because the model has not seen
  the announcement. A human reads the headline and decides; to resume, restart the bot (`bot/stop.sh` then `run_live.sh`).
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

Seasons 1 to 450 were used for fitting; report results on 451 to 600.

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

## Results (verify seasons 526-600, default parameters, 2026-10-23 03:05)

| Regime | mean PnL | median | p10 | min | losing seasons | fills/season |
|---|---|---|---|---|---|---|
| deep (ladder, refill 10 s) | 8,747 | 8,324 | -3,127 | -12,774 | 17% | 348 |
| thin (ladder at half size, refill 30 s) | 5,348 | 4,763 | -4,297 | -14,113 | 20% | 879 |

Deep regime by symbol: HAVEN +2669, PORT +1300, ARCH +1181, FERRY +720, GRID +590, AQUA +537, RECON +540, REBLD +441,
ISLE +241, MAT +100, GEN +68, REIN +47. By round: R1 +2649, R2 +3144, R3 +2639. Fill PnL by phase (thin regime, 75 seasons):
the storm itself earns everything (+286k, of which +129k in the first 60 s of the storm); pre-storm, aftermath and
post-report fills are flat to negative. The constant-velocity nowcast loses about 20k per season under the ladder.

## Forecast skill (holdout storms, RMSE of end-of-storm company damage in points, PORT/ISLE/AQUA/GRID/FERRY)

| Storm age | Constant velocity | Analog ensemble | Pattern top-1 |
|---|---|---|---|
| 30 s | 24.7 / 11.2 / 14.9 / 11.3 / 10.8 | 18.7 / 9.1 / 10.9 / 7.4 / 7.3 | 71% |
| 90 s | 23.2 / 10.1 / 14.1 / 10.9 / 10.2 | 15.2 / 6.0 / 7.2 / 6.2 / 6.4 | 87% |
| 150 s | 22.1 / 8.3 / 9.1 / 9.7 / 8.1 | 12.0 / 4.7 / 5.9 / 5.4 / 5.4 | 93% |
| 240 s | 13.3 / 4.5 / 5.3 / 5.8 / 5.1 | 9.8 / 3.5 / 4.0 / 4.5 / 4.1 | 95% |

Official advisories name the true pattern 69% of the time; the ensemble passes that by the second advisory.
The ensemble is insensitive to sigma (15 to 40), k (50 to 100) and the position shift.

## Next

1. Freeze the parameters: the tuner is being re-run on the current simulator (out/tune/ledger.csv); re-verify its winner
   against the accepted set before competition day.
2. Live earns about 70% of the sim on the same seasons with the sign right every time since the warm-up fix; the
   remaining gap is concentrated in the big winning seasons (190: +15k live vs +33k sim). Compare the bot's fills in those
   seasons with the sim's (scripts/dissect.py --json) before changing anything.
3. Exact rebuilder settlement rules with a 3% floor for RECON and MAT (needs its own tune run).
4. ETF create/redeem arbitrage (measured: ARCH quote more than 0.9% from its basket 5% of the time; small, riskless).
5. Live announcements: the bot pauses named symbols; a human must read the headline and decide.
