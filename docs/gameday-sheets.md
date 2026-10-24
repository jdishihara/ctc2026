# Game day sheets: one page per desk (Saturday 2026-10-24)

Three desks, two roles at each: the **reader** puts information into the tool, the **clicker** executes what it
outputs. Nothing on these pages needs market knowledge beyond noticing that a number is nonsense (a spot of 8 when the
chain shows 80, a fair of 300 for a stock at 60).

Overall rank = 0.45 x Hurricane rank + 0.35 x Derivatives rank + 0.20 x Mario rank. Lower is better.

---

## Hurricane (Systematic Equities, 45%): one watcher, the bot trades

Before the open (15 min). Paste in order, in `~/projects/ctc2026`:

```bash
caffeinate -i -t 36000 &
git pull && git status                       # clean, on main
echo COMPETITION_KEY > .botkey               # from the captain's Team page; never commit it
python3 bot/preflight.py                     # must end with 0 failures. WARN on positions/orders -> bot/stop.sh, rerun
nohup python3 data/starter_kit/record_feed.py --url wss://cornelltradingcompetition.org --key $(cat .botkey) \
      --out recordings/competition.jsonl --symbols PORT,ISLE,AQUA,GRID,FERRY,RECON,MAT,GEN,HAVEN,REIN,ARCH,REBLD > /dev/null 2>&1 &
nohup python3 scripts/record_books.py --key $(cat .botkey) --out recordings/competition_books.jsonl > /dev/null 2>&1 &
FEED_LOG=recordings/competition.jsonl nohup zsh bot/run_live.sh > /dev/null 2>&1 &
tail -f recordings/bot_live.log
```

Healthy start lines, in order: `strategy analog min_edge 0.025 ...`, `final phase exact=True ...`,
`basket edge=0.01 ...`, `announcements: pause named symbols, re-anchor ... 60 s`, `replayed N feed messages`,
`connected`, `snapshot processed: warm-up before trading`.

Every 10 s: `t= ... r<round> pnl <season pnl> SYM:mid/fair/position`. Glance at it. Fair within a few percent of mid
for most symbols is normal; during a storm they diverge, that is the trade.

| You see | It means | Do |
|---|---|---|
| `market (re)opened: warm-up` | round open, no orders for 20 s | nothing; watch the first minute |
| one or two `HTTP 4xx` around a halt | normal | nothing |
| a stream of `HTTP 4xx` | tick, limits or key | `bot/stop.sh`, read the error, fix, `run_live.sh` |
| `disconnected ... reconnecting` once | fine | nothing |
| `disconnected` every few seconds | network | check wifi; the bot rebuilds from the recording on reconnect |
| `ANNOUNCEMENT [SYM]: <headline> -> pausing` | model has not seen it | read docs/announcements.md rule 1; default: do nothing, it re-anchors to the house in 60 s |
| `announcement wait over: SYM fair anchored to house mid` | resumed on the house's price | nothing |
| position stuck at the limit with fair far from mid for minutes | the model disagrees with the market | note it; if a human can explain why the model is wrong, `echo "SYM =<mid>" >> recordings/control.txt` |
| `SEASON END` | the competition ended or a new id | stop here; this is the real season, there is only one |

Commands while running (no restart): `echo "HAVEN -6%" >> recordings/control.txt`, `... "PORT =61.5"`,
`... "resume GEN"`, `... "pause MAT"`, `... "status"`.

Emergency: `bot/stop.sh` (cancels every order, prints positions). `bot/stop.sh --flatten` also closes positions.

Rules: nobody trades on the bot key (it uses 120 of the team's 180 actions a minute). Do not restart the bot during a
storm unless it is broken: a restart during round 1 on the testnet missed half the storm's PnL.

---

## Derivatives (35%): reader confirms, clicker clicks, 2.5 minutes per event

Setup: load `derivatives-overlay/dist` in `chrome://extensions` (Developer mode, Load unpacked), hard-reload the
exchange tab. Header must say **DERIVATIVES**. Capture tab: `ws:quote` counting up. Edge tab: `spot: WS` (or DOM).
Press `Alt+1` on the OIL laptop and `Alt+2` on the PLANE laptop if you split underlyings. Dry run `Alt+A`, `Alt+N`,
look at the form, do not submit.

Scoring is the sum over rounds of rank^1.5: one bad round costs more than a great one earns. Be flat between events.

Each event, by the clock. Times are from the news (`NEWS IN m:ss` in the header):

| When | Reader | Clicker |
|---|---|---|
| news +0 s | targets appear amber. Compare spot and vol with the headline. Round 1: both numbers are in the news. Fix a wrong one: `Alt+S` / `Alt+V`, type, Enter. Then `Alt+A`. | wait |
| +5 s to +110 s | watch the queue; if the live spot warning appears at +60 s, re-check and `Alt+A` again | `Alt+N` (form fills: contract, BUY/SELL, Limit, qty, price) -> glance -> click the Buy/Sell button -> `Alt+N`. Switch the OIL/PLANE tab yourself when the ticket says so |
| +120 s snap | overlay switches to Risk | `Alt+F` loads closing tickets; click them until delta and vega are near zero |
| last 30 s | red **FLATTEN NOW** = still carrying risk | keep flattening; accept the spread |

Order budget: header `orders n/40` per minute, amber at 30, red at 36. The hourglass in the queue means over budget.

Round 2 (analysts, no IV): the three estimates arrive in the news and fill the Vol tab grid; type any the parser
missed (Tab between cells, Enter). Event 4: blend = median. From event 5: switch blend to **weighted (learned)**.

Round 3 (a quantity "linked to IV"): read the first analyst message. Vol tab -> Round 3 converter -> pick what it is
(variance, daily move, move to expiry, ATM straddle, option price at K, P(ITM), vega, or a custom formula in `x S T K`).
Use "try x =" and check the resulting vol is near the market IV shown at the bottom of the Vol tab. If it is far off, the
pick is wrong; try the next one. Decide within the first event; later events reuse it.

If it breaks: no quotes -> Capture tab, patch `fields.quote` in Config. Prefill fails -> the ticket card's **copy**
button, type the order by hand. Overlay in the way -> `Alt+O`. Fallbacks: `derivs/desk.xlsx` and the exchange's own
Black-Scholes calculator.

---

## Mario (20%): reader types results, clicker clicks the action list

Setup: `python3 mario/desk.py` (add `--host 0.0.0.0` to share the dashboard). Log in with Google in the Chrome it
opens, once. Open `http://localhost:8787`. At the prompt type `map`: every symbol must have a role (race N / series N
winner for a racer, or #1 / #2 / top-2 score). Fix any UNMAPPED in `mario/contracts.json` and restart before race 1.

After every race, within seconds: `race <Birdo> <Daisy> <Peach> <Yoshi>` with the overall finishing places (1-12) in
that alphabetical order, from the stream. Typo: `undo`, retype. The dashboard reprices all 46 contracts.

After race 1 only: if the humans all finished behind several CPUs, `cpu 0`; if a human won outright and the others were
top 4, leave it.

Clicker: the action list is best first. Orange rows show settlement guarantees (race-winner sets sum to 100; series-winner
sets pay 100 to 200 because every tied winner pays 50; top-2 equals #1 + #2). Multi-leg guarantees require every leg to
fill at the stated prices. Recheck available size and positions after each fill. Then consider model edges. Click
**prepare** on a row (or type `prepare N`): the exchange tab's form fills; you click the submit button. Size is already
inside the position limit and the book. Browser cap is 40 orders a minute, about one every 1.5 s.

Sanity checks the clicker can do without the model: before race 1 every race-winner and series-winner is worth about
25. Do not pay above about 45 for a race favourite after one win. After two races, a series lead of 6-9 points is about
85%, 10 or more about 95%. #1 score settles near 48 with sd 7 before the series; maximum possible 60. Top-2 total
maximum 108.

Settlements: race winners after each race, series contracts after races 4 and 8. Series 2 contracts trade during
series 1 at the prior (25 each binary) until race 5.

If it breaks: dashboard not refreshing -> Chrome tab closed or logged out; the desk reopens the tab, log in again.
Prefill fails -> type the symbol, side, size and price from the row by hand. Desk dead -> `python3 mario/pricer.py`,
type `race ...` and `fair` in the terminal and trade from that.

---

## Before you leave tonight

- [ ] Schedule from Slack: do the cases overlap? Assign readers and clickers per desk.
- [ ] Hurricane: a supervised testnet season on current main (nothing has run since 06:29 today; the basket overlay and
      the merged efficiency branch have never traded live). Compare the `SEASON END` PnL with `scripts/backtest.py
      --seasons N`.
- [ ] Derivatives: one real-speed drill (`npm run mock`, dev build loaded, `derivs/drill.py --round 2`).
- [ ] Mario: one drill (`mario/mock_exchange.py --race-every 60`, `mario/desk.py --mock --tap browser`).
- [ ] Charge laptops. Business casual. Check-in 8:00-8:30, 34 N Loop Rd, Roosevelt Island.
