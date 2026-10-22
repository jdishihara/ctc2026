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
small), `--warmup 20` (no trading for 20 s after a round opens), `--prior sample|point`, `--future-sd`,
`--loss-limit`, `--exact-rebuild` (the last three are rejected options kept for reference).

Live bot (testnet or competition), dry run first:

```bash
pip install "websockets>=14"
python3 bot/live.py --key BOT_KEY --dry-run          # default url https://cornelltradingcompetition.org
zsh bot/run_live.sh                                  # keeps it running, logs to recordings/bot_live.log (pnl every 10 s, SEASON END lines)
```
The bot runs the same FairValueTrader as the backtest (analog ensemble, passive 0.75, warm-up 20 s). Prices are
rounded to the 0.01 tick (buys down, sells up). On the testnet the fictional year gives the season: season = 2027 - year.

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

Liquidity is the ladder measured on the testnet (ctc/ladder.json, 846 snapshots per symbol): touch spread 0.23-0.32%,
20-80 shares at the touch, a few hundred within 1-3%, and the house's 600-lot backstop about 8% from its (lagging)
centre. Aggressive orders walk the ladder up to their limit price; consumed depth regenerates linearly over `--refill`
seconds (10 s deep, 30 s thin; `--ladder-scale 0.5` halves every size in the thin regime). A resting order fills when
the house re-quotes through it, for the size the house posts at or beyond our price, at our price (measured live: the
house does cross resting orders). 0.25 s latency; limits include resting orders; 300 order actions per minute (bot cap
120); resting orders cleared at each close; ETF create/redeem at marks; 0.01 tick.

Known gaps vs the testnet: no opening phase (the testnet opens a round with a thin book and the bot's first orders hit the
backstop; the 20 s warm-up covers it), no instant round replays (the testnet replayed one round in a second), fill cost
live measured at about 90 bp of notional against 30-60 bp implied by the ladder.

## Results (verify seasons 526-600, default parameters, 2026-10-22 05:40)

| Regime | mean PnL | median | p10 | min | losing seasons | fills/season |
|---|---|---|---|---|---|---|
| deep (ladder, refill 10 s) | 6,353 | 6,082 | -3,078 | -11,264 | 17% | 362 |
| thin (ladder at half size, refill 30 s) | 2,711 | 2,009 | -7,024 | -16,957 | 35% | 786 |

Deep regime by symbol: HAVEN +2364, ARCH +1195, PORT +855, RECON +515, GRID +440, FERRY +276, AQUA +260, REBLD +229,
ISLE +106, MAT +78, REIN +42, GEN -7. By round: R1 +1654, R2 +2618, R3 +2082. Fill PnL by phase (thin regime, 75 seasons):
the storm itself earns everything (+286k, of which +129k in the first 60 s of the storm); pre-storm, aftermath and
post-report fills are flat to negative. The constant-velocity nowcast loses about 20k per season under the ladder.

Testnet (analog bot, after the fixes of 2026-10-22): season 184 +4.9k vs sim +9.5k, 185 -16.3k vs +7.4k (round 1 was
replayed instantly, the open was traded into the backstop), 186 -0.5k vs +6.3k, 187 +17.8k vs +19.6k.

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

1. Live fill cost (90 bp vs 30-60 bp in the sim): cap aggressive size per cycle, or stop walking into the 8% backstop
   unless the edge is larger than the backstop distance plus the floor.
2. ETF create/redeem arbitrage (measured: ARCH quote more than 0.9% from its basket 5% of the time; small, riskless).
3. Round-3 rate limits: the bot sends up to 47 actions per minute in the sim against a 120 cap; prioritise by edge x limit.
4. Live announcements: the bot pauses named symbols; a human must read the headline and decide.
