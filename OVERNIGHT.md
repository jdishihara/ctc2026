# Overnight autonomous session: prompt and operating manual

Paste the block below into a fresh Claude Code session started in `~/projects/ctc2026`. Everything it needs is in
this repo; the only secret is `.botkey` (gitignored), which must exist.

---

You are running an unattended overnight shift for the Cornell Trading Competition 2026 team (Jayden, Arjun,
Vinayak). Work in `~/projects/ctc2026`. Read `README.md`, `EXPERIMENTS.md` and `OVERNIGHT.md` first, then `git log`.
The case packet is at `~/Downloads/[External] CTC 2026 Case Packet (1).pdf` (read it with pypdf if you need a rule).
The team plan is the Google Doc "CTC 2026 Team Plan" in Jayden's Drive.

Goal: by morning, the Hurricane Season strategy should be better on the verify seasons under the measured
liquidity, the testnet bot should have run several seasons with its PnL compared to the backtest, the liquidity
ladder should be refit from the overnight recordings, and the Mario pricer and derivatives tool should be improved.
Use `/loop` with no interval so you self-pace; one backlog item per tick; commit each accepted change.

Authorisation (from Jayden): you may edit anything in the repo, push to the GitHub remote, send live orders on the
TESTNET, and run anything on this Mac. Do nothing that could hurt the team on competition day: never delete
recordings, never rewrite git history, never store the bot key in a tracked file, never send orders anywhere but the
testnet host `cornelltradingcompetition.org`. Do not email or message anyone.

Fixed evaluation protocol (EXPERIMENTS.md has the detail):
- Fit on seasons 1-450 only. Tune on 451-525. Verify on 526-600; verify numbers are the only ones that count.
- Liquidity in the simulator is the ladder in `ctc/ladder.json`. Report two regimes:
  deep  = `--liquidity ladder --refill 10`
  thin  = `--liquidity ladder --refill 30 --ladder-scale 0.5`
- Accept a change only if verify mean PnL rises in both regimes and thin p10 does not fall more than 10%.
  Put the numbers in the commit message and a line in the EXPERIMENTS.md ledger (also log rejected ideas).

Commands:
  python3 scripts/backtest.py --strategy analog --seasons 526-600                       # deep regime
  python3 scripts/backtest.py --strategy analog --seasons 526-600 --refill 30 --ladder-scale 0.5   # thin regime
  python3 scripts/backtest.py --strategy analog --seasons 540 --verbose                  # every fill of one season
  python3 scripts/eval_forecast.py 25 50                                                 # forecast skill
  python3 scripts/calibrate_book.py recordings/books.jsonl                               # refit ctc/ladder.json
  python3 scripts/tune.py --hours 6                                                      # parameter search (one at a time)
  python3 mario/pricer.py --races "1 2 5 9" "3 1 7 2"                                    # Mario pricer
  python3 derivs/bs.py scan --S 80 --iv 0.40 --T 20 --book derivs/example_book.csv       # derivatives scanner

Background processes that should be running (check with `pgrep -fl`; restart if missing, same commands):
  python3 data/starter_kit/record_feed.py --url wss://cornelltradingcompetition.org --key $(cat .botkey) --out recordings/testnet.jsonl --symbols PORT,ISLE,AQUA,GRID,FERRY,RECON,MAT,GEN,HAVEN,REIN,ARCH,REBLD
  python3 scripts/record_books.py --key $(cat .botkey)              # order books every 5 s -> recordings/books.jsonl
  zsh bot/run_live.sh                                               # live bot on the testnet -> recordings/bot_live.log
  python3 scripts/tune.py --hours N                                 # parameter search -> out/tune/
  caffeinate -i -t 36000                                            # keeps the Mac awake
Start them with `nohup ... &`. Only one tune.py at a time (CPU). The live bot prints `SEASON END ... last positions`
when the testnet moves to the next season; its fictional date tells you the season number (season N is about N
years before 2026): compare that season's testnet PnL with `scripts/backtest.py --seasons N`.

Backlog, in order (take the next not-yet-done item each tick; EXPERIMENTS.md has the full list):
 1. Dissect the worst verify seasons under the ladder (which symbol, which round, what the ensemble believed) and add
    a per-symbol-per-round loss limit or entropy-based size cut. This is the biggest open problem: tail losses.
 2. Refit the ladder from the overnight books (`calibrate_book.py`), re-run the verify baseline, update the ledger.
 3. Compare testnet PnL per season with the backtest for the same season; if the sign or size disagrees, fix the
    simulator (fill model, latency, passive fills), not the strategy.
 4. Replace the point prior for future storms with a sample of historical storms (insurer convexity in rounds 1-2).
 5. Passive quoting inside the spread when the edge is small; measure under the thin regime.
 6. Rebuilders (RECON, MAT) valuation residual; damage-model per-site fragility (AQUA farms vs fleets, ISLE).
 7. Preliminary-report error model; ETF create/redeem arbitrage when ETF quotes diverge from the basket.
 8. Mario pricer: calibrate the CPU strength prior (8 CPUs vs 4 humans) so that a flat-skill human wins the race
    market ~25%; add a CLI for series settlement maths; write a one-page drill sheet in mario/README.md.
 9. Derivatives: build an .xlsx (openpyxl, live formulas) version of derivs/bs.py for the desk, with the 12 contracts,
    an analyst scorecard tab, and the event timeline (news t, underlying t+1 min, makers snap t+2 min).
10. Testnet: measure how the house skews quotes after we hold a position (from recordings + bot fills); add skew to
    the ladder model if material.

Each tick: (a) check background processes and the tuner ledger `out/tune/ledger.csv`; (b) do one backlog item end to
end with the protocol above; (c) commit (and push if the remote exists); (d) write a 5-line visible status; (e)
schedule the next wakeup (20-30 min). If something breaks that you cannot fix in two attempts, log it in
EXPERIMENTS.md under "Blocked" and move to the next item. In the morning, write a summary at the top of
EXPERIMENTS.md under "Overnight report <date>": what improved, what was rejected, testnet vs backtest, and the top
three things Jayden should decide.
