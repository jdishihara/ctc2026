# Mario Markets desk (CTC 2026, 20% of the overall score)

Four humans (Birdo, Daisy, Peach, Yoshi: identical characters and karts) and eight CPUs race; two series of four
races. Only humans have contracts. Points by overall place among all 12: 15 12 10 9 8 7 6 5 4 3 2 1.

The updated packet (2026-10-23) allows bots for this case but gives no API key: "Trading will be done manually through
the UI", "a bot would have to find another way ... (maybe monitor a chrome window or something similar)". The desk below
does exactly that: it reads the exchange through the trading UI's own browser session, prices every contract, ranks the
trades, and a human clicks them in the UI.

## Contracts and settlement

| market | type | limit | settles |
|---|---|---|---|
| Race winner (4 per race) | binary | 100 | 100 for the best-placed human of that race (a CPU may finish ahead), 0 others |
| Series winner (4 per series) | binary | 200 | 100 for the highest series score; 50 each if tied for first; 0 others |
| #1 score, #2 score, top-2 total (3 per series) | numeric | 1000 | the top two human series scores and their sum |

Examples from the packet: scores 49/42/34/28 settle the winner at 100, #1 = 49, #2 = 42, top-2 = 91.
Scores 45/45/34/28: both leaders settle at 50, #1 = #2 = 45, top-2 = 90.

Race-winner contracts settle after each race; series contracts after race 4 and race 8. Anything unsettled trades,
including race 5-8 winners and the series 2 contracts during series 1.

## The desk (bot)

```
mario/desk.py          the program: tap thread + pricer + engine + dashboard on http://localhost:8787 + a command prompt
mario/tap.py           BrowserTap: starts a plain Chrome with remote debugging and attaches over CDP (a Playwright-launched Chrome
                       is refused by Google sign-in), you log in once; polls /api/v1/symbols, orderbook/{sym},
                       positions, orders/open, trades inside that page, so the session cookie authenticates (no API key).
                       HttpTap: plain HTTP for the mock (or an API key if one appears). prefill() types an order into the UI's form.
mario/engine.py        fairs + books + positions -> ranked actions: model-free arbs (set of 4 binaries vs 100, top-2 = #1 + #2,
                       hard bounds from banked points) and model edges (fair +- margin, sized to the book and the limits)
mario/pricer.py        Monte Carlo fair values; particle filter over racer skill; `fairs()` values all 46 contracts
mario/contracts.py     symbol -> role (race/series/score, racer) parser; mario/contracts.json overrides it
mario/mock_exchange.py a fake exchange with 46 contracts, a biased house, races every N seconds, settlements: the drill
```

How the UI talks to the exchange (checked 2026-10-23 in Chrome on the testnet): the Next.js app calls the same
`/api/v1/...` endpoints the bot API uses (orderbook, positions, orders, trades, symbols, competitions/current) and the
`/ws/v1/market-data` stream, authenticated by the login cookie. `fetch('/api/v1/orderbook/PORT', {credentials:'include'})`
from the page returns the full book; the same call without a session returns 401. The order form is `#order-qty`,
`#order-price`, buttons BUY / SELL / Limit / Market, and a submit button "Buy 20 PORT"; symbols are tab buttons.

### Competition day

```bash
pip install playwright                                # once; it drives the installed Google Chrome, no download
python3 mario/desk.py                                 # starts its own Chrome (remote debugging, profile ~/.ctc_mario_chrome): LOG IN THERE once with Google
open http://localhost:8787                            # the dashboard, on a second screen next to the exchange tab
                                                      # --host 0.0.0.0 shares it with teammates' laptops at http://<this laptop's IP>:8787 (ipconfig getifaddr en0)
> map                                                 # check every symbol's role; fix mario/contracts.json and restart if any is wrong or UNMAPPED
> race 1 2 5 9                                        # after each race: overall places of BIRDO DAISY PEACH YOSHI (alphabetical), from the stream
> undo | cpu -0.3                                     # typo, or re-centre the CPU strength prior (see the calibration table below)
> type PORT sell 1 99                                 # checks the form pre-fill on the live UI (nothing is sent until you click); verified on the testnet 2026-10-23
```
The dashboard refreshes every 0.7 s: actions best first (profit in contract points = PnL at settlement if the fair is
right; riskless arbs on an orange background), then every contract with bid/ask, fair, sd, edge, hard bounds, position,
and the log. One person watches the race and types the result; one person clicks orders in the UI from the action list
(limit orders at the listed price and size; the size already respects the position limit and what is in the book).

Each action has a "prepare" button (or `prepare N` at the prompt) that selects the symbol tab, the side and Limit in the
exchange window and types the quantity and price into its form; the human clicks the submit button. The organisers
confirmed on 2026-10-23 that this is allowed. `--no-prefill` turns it off. The mock's page carries a copy of the real
form (same element ids and button names), so `--mock --tap browser` drills the exact prepare-then-click loop.

Flags: `--interval 1.0` (poll period; 46 book requests per poll, well inside the packet's 600 requests per second per team; the packet also caps the browser at 40 orders per minute, so the clicker has about one order every 1.5 s), `--clip 50` (max
size per action), `--risk 1500` (score contracts: size x sd <= risk), `--min-profit 5`, `--cpu-skill -0.6`.

### Drill (no exchange needed)

```bash
python3 mario/mock_exchange.py --race-every 60 --seed 3     # a tournament: a race every minute, a biased house, settlements
python3 mario/desk.py --mock                                # type the results the mock prints ("RACE 1 finished: places ...")
python3 mario/desk.py --mock --auto-results                 # or let the desk read them
> fill S1_WIN_PEACH buy 30 36.7                             # in mock mode the desk sends the order (stands in for the click)
```
Measured 2026-10-23: taking the top three actions every 3 s against the mock (house bias sd 4 points) over six races
made +6.5k in the mock's own marks (+2.5k realized at settlements); the browser tap works against the mock page too
(`--tap browser --headless`). The mock's house is a guess; the real counterparties are the other teams and whatever
market maker the organisers run.

### What the engine does with the book

1. Model-free, riskless at settlement, checked every poll: the four race-winner (or series-winner) contracts of one race
   (series) settle to exactly 100 in total, so sum of asks < 100 is a buy of all four, sum of bids > 100 a sale;
   top-2 total settles to #1 + #2 exactly; #1 >= the leader's banked points and <= banked + 15 x races left, #2 and
   the total likewise. A binary whose racer can no longer win is a free sale.
2. Model edges: buy when ask <= fair - margin, sell when bid >= fair + margin. Binaries: margin 6 / 4 / 3 / 2.5 points
   by races completed in that series (the skill posterior is weak early); score contracts: max(2 points, 0.35 sd).
   Size = what the book offers at acceptable prices, capped by the position limit, `--clip`, and the risk budget.
3. PnL marked to fair (position x (fair - average price) + exchange realized) next to the exchange's own number.

## Pricer (stand-alone)

```
python3 mario/pricer.py                       # interactive: "race 1 2 5 9" (overall places of A B C D), "fair", "undo"
python3 mario/pricer.py --races "1 2 5 9" "3 1 7 2"
python3 mario/pricer.py settle 49 42 34 28    # series settlement from cumulative scores
python3 mario/pricer.py points 2 1 5 9        # points of one race and the race-winner settlement
python3 mario/pricer.py calib                 # CPU prior sensitivity table
```

Model: performance = skill + noise per race; human skills share a flat prior (sd 1) and are updated from finishing
places with a particle filter; CPUs have a prior mean of -0.6 (humans usually finish top-5, #1 series score about 48,
which matches the packet's example). If after race 1 the humans are all behind several CPUs, rerun with
`--cpu-skill 0` or `+0.3` (desk: `cpu 0`); if a human wins outright and the others are top-4, keep -0.6.

## Calibration (2026-10-23)

300 series simulated from the pricer's own model: race-winner Brier score 0.69 / 0.65 / 0.64 after 1 / 2 / 3 races (0.75 for
flat 25% quotes), series-winner Brier 0.50 / 0.34 / 0.21. Predicted race-winner probabilities of 0.15-0.25 came in at 0.22,
0.25-0.35 at 0.30, 0.35-0.50 at 0.40 and 0.50+ at 0.60: slightly over-confident on favourites, so shade a 55% quote to 50-52.
The likelihood temperature (the /8 in `_loglik`) changes the Brier by under 0.01 between 4 and 32.

## Trading rules of thumb

1. Before race 1 every race-winner contract is worth 25 and every series-winner contract 25: fade anything far from
   that unless you know the racers.
2. Race-winner markets are about the next race only: skill estimates from 1-2 races are weak (sd of the skill estimate
   is still about 0.6 after two races), so do not pay more than about 45 for a favourite after one win.
3. The series-winner market is where the information is: after two races a 6-9 point lead is about an 85% favourite and 10+ about 95% (table below).
4. #1 score and top-2 total are nearly linear in the leader's points: each race adds the leader's points; if the leader is
   averaging 13 per race, #1 settles near 52, and the sd of the remaining races is about 3 points per race left.
5. Position limits: 100 race / 200 series / 1000 score contracts. Size the numeric contracts by edge in points, not %.
6. Keep a written ledger of every race result; run `fair` after each race before quoting.

### Series winner probability of the leader, by lead after k races (equal-skill prior)

| races done | lead 0-2 | lead 3-5 | lead 6-9 | lead 10-14 | lead 15+ |
|---|---|---|---|---|---|
| 1 | 47% (n=7649) | 63% (n=23269) | 79% (n=8382) | 90% (n=700) | - |
| 2 | 50% (n=10847) | 67% (n=8637) | 85% (n=10618) | 95% (n=7772) | 99% (n=2126) |
| 3 | 49% (n=7067) | 70% (n=8157) | 91% (n=8825) | 99% (n=8155) | 100% (n=7796) |

The table assumes the four humans are equally skilled; after race 1 the pricer's skill update moves these numbers (a racer who won race 1 is also more likely to be better).

### Top-two score contracts at the start of a series (equal-skill prior, CPU prior -0.6)

| contract | mean | sd | p10 | p90 |
|---|---|---|---|---|
| #1 score | 48.0 | 7.4 | 38 | 57 |
| #2 score | 36.9 | 7.1 | 27 | 46 |
| top-2 total | 84.9 | 12.0 | 69 | 99 |

Maximum possible: #1 score 60, top-2 total 108 (15+12 per race). Minimum #1 score when four humans split evenly is about 30.

### CPU-strength calibration (what to check after race 1)

```
noise sd 1.0, human skill sd 1.0; per CPU-skill prior (mean, sd):
  cpu prior   P(human 1st overall)  median human place  mean pts/human/race  #1 series score mean (sd)  P(race-winner mkt | equal skill)
  (-0.6, 0.5)     65%                 5                  8.1               47.9 (7.4)              25% by symmetry
  (-0.3, 0.5)     55%                 6                  7.6               45.8 (8.1)              25% by symmetry
  (+0.0, 0.5)     45%                 7                  6.9               43.2 (8.8)              25% by symmetry
  (+0.3, 0.5)     35%                 7                  6.3               40.3 (9.2)              25% by symmetry
  (+0.6, 0.5)     27%                 8                  5.7               37.5 (9.5)              25% by symmetry
  (+0.0, 1.0)     33%                 7                  6.8               41.4 (8.6)              25% by symmetry
```
