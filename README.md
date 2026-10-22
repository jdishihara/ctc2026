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
ctc/strategies.py FairValueTrader (constant-velocity nowcast or analog ensemble) and FinalReportOnly
bot/live.py      live bot: wraps the exchange API in the Sim interface and runs FairValueTrader
scripts/build_library.py  rebuilds ctc/analog_library.npz from seasons 1-450
scripts/eval_forecast.py  forecast skill at several storm ages, constant velocity vs ensemble
scripts/mock_exchange.py  replays a season over the exchange's HTTP + WebSocket API, for bot tests without the testnet
scripts/fit_damage.py     refits the damage model (writes ctc/damage_params.json)
scripts/fit_valuation.py  refits the settlement rules (writes ctc/valuation_params.json)
scripts/eval_valuation.py residual sd per symbol on holdout (adds resid_sd to valuation_params.json)
scripts/backtest.py       runs a strategy over seasons
```

## Run

```bash
python3 scripts/backtest.py --strategy nowcast --seasons 451-600          # holdout
python3 scripts/backtest.py --strategy final   --seasons 451-600          # round-3 final report only
python3 scripts/backtest.py --strategy analog  --seasons 451-600          # analog ensemble (current best)
python3 scripts/backtest.py --strategy nowcast --seasons 7 --verbose      # every fill of one season
python3 scripts/backtest.py --strategy analog --seasons 451-600 --depth 100 --half-spread 0.003   # liquidity what-if
```

Live bot (testnet or competition), dry run first:

```bash
pip install "websockets>=14"
python3 bot/live.py --url https://hurricane.cornelltradingcompetition.org --key BOT_KEY --dry-run
```

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

House bid/ask = consensus price * (1 -/+ half_spread), default 0.15%; unlimited depth; 0.25 s latency; position limits
include resting orders; 300 order actions per minute; resting orders cleared at each close; ETF create/redeem at marks.
Replace half_spread and depth with numbers measured on the testnet (quotes channel) as soon as we have a recording.

## Results so far (seasons 451-600, default parameters)

| Strategy | mean PnL | median | p10 | losing seasons |
|---|---|---|---|---|
| final (round-3 final report only) | 576 | 85 | 0 | 5% |
| nowcast (constant-velocity projection, no pattern model) | 9,333 | 9,698 | 2,088 | 5% |

Most PnL comes from HAVEN, PORT and ARCH during the storm. Rounds contribute about equally.

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

1. Measure house depth, spread and inventory skew on the testnet (record the quotes channel); set the simulator to match.
2. Passive quoting inside the house spread once depth is known.
3. Rebuilders: RECON/MAT residuals (1 pt) are the loosest part of the valuation.
4. Live announcements: the bot pauses named symbols; a human must read the headline and decide.
