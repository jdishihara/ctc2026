# Game day sheets: one page per desk (Saturday 2026-10-24)

The cases do not overlap (confirmed 2026-10-24), so all four teammates and laptops work one case at a time. Each desk
has two roles: the **reader** puts information into the tool, the **clicker** executes what it outputs. The other two
watch for mistakes and keep the time. Nothing on these pages needs market knowledge beyond noticing that a number is nonsense (a spot of 8 when the
chain shows 80, a fair of 300 for a stock at 60).

Overall rank = 0.45 x Hurricane rank + 0.35 x Derivatives rank + 0.20 x Mario rank. Lower is better.

---

## Hurricane (Systematic Equities, 45%): one watcher, the bot trades

Schedule (organisers' doc, tentative): Case II Systematic Equities **2:35-4:10 pm**. The exchange already serves the
Hurricane competition (`/competitions/current` = "Hurricane Season", state ready, fictional date 2026-08-03, checked
10:00). The live season is dated 2026; the bot's feed-log replay keeps only the season after the last seq restart, so a
same-year warm-up season cannot pollute the real one (fixed 2026-10-24 10:10).

Before the open (15 min). One command does all of the steps below in order and refuses to start the bot if preflight
reports a failure: `zsh scripts/launch_competition.sh` (then `tail -f recordings/bot_live.log`). By hand, paste in
order, in `~/projects/ctc2026`:

```bash
bot/stop.sh                                  # the overnight testnet bot (started 00:22) and its recorders are still running: stop them first
pkill -f record_feed.py; pkill -f record_books.py; pkill -f "mario/desk.py"
caffeinate -i -t 36000 &                     # idle sleep only; keep the lid OPEN, or: sudo pmset -a disablesleep 1 (undo with 0)
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
`connected`, followed by `history complete: trading eligible` once complete history is verified.
Start the recorder and bot before the first storm. A snapshot or a nonzero replay count alone does not authorize trading.

Every 10 s: `t= ... r<round> pnl <season pnl> SYM:mid/fair/position`. Glance at it. Fair within a few percent of mid
for most symbols is normal; during a storm they diverge, that is the trade.

| You see | It means | Do |
|---|---|---|
| `market (re)opened: warm-up` | round open, no orders for 20 s | nothing; watch the first minute |
| `TRADING BLOCKED: missing news history` / `incomplete weather history` (persisting; a few seconds at a round open is normal) | new orders/conversions blocked; resting orders canceled. Reconnects that lose up to 6 messages in a season repair themselves and do not show this | restart from a complete current-season recording (`FEED_LOG=recordings/competition.jsonl zsh bot/run_live.sh`), or wait for the next season from its beginning; manage existing holdings explicitly |
| `waiting for a live news checkpoint` / `new-season account refresh` | feed/account not synchronized | wait for synchronization; investigate if it persists |
| one or two `HTTP 4xx` around a halt | normal | nothing |
| a stream of `HTTP 4xx` | tick, limits or key | `bot/stop.sh`, read the error, fix, `run_live.sh` |
| `disconnected ... reconnecting` once | fine | nothing |
| `RESTARTING: N lost messages ... are in recordings/competition.jsonl` then `=== start` | a long feed hole; the bot exits and the wrapper restarts it in 10 s, replaying the season from the recorder's file; eligible again about a minute later | nothing; if `feed log lacks ...` shows instead, both connections lost the messages: restart by hand only if a later recording has them |
| `disconnected` every few seconds | network | check wifi; a missing sequence needs a restart with complete recorded history |
| `ANNOUNCEMENT [SYM]: <headline> -> pausing` | model has not seen it | read docs/announcements.md rule 1; default: do nothing, it re-anchors to the house in 60 s |
| `announcement wait over: SYM fair anchored to house mid` | resumed on the house's price | nothing |
| position stuck at the limit with fair far from mid for minutes | the model disagrees with the market | note it; if a human can explain why the model is wrong, `echo "SYM =<mid>" >> recordings/control.txt` |
| `SEASON END` | the competition ended or a new id | stop here; this is the real season, there is only one |

Commands while running (no restart): `echo "HAVEN -6%" >> recordings/control.txt`, `... "PORT =61.5"`,
`... "resume GEN"`, `... "pause MAT"`, `... "status"`.

Emergency: `bot/stop.sh` (cancels every order, prints positions). `bot/stop.sh --flatten` also closes positions.

Backup recorder (second laptop, no bot): the recording is what lets a restarted bot rebuild the season exactly, so run a
second copy of the feed recorder on another laptop from the first minute. It only reads the feed (one of the team's 25
market-data connections, no order actions), so it may use the same key, typed into that laptop's git-ignored `.botkey`:

```bash
echo COMPETITION_KEY > .botkey
nohup python3 data/starter_kit/record_feed.py --url wss://cornelltradingcompetition.org --key $(cat .botkey) \
      --out recordings/competition_backup.jsonl --symbols PORT,ISLE,AQUA,GRID,FERRY,RECON,MAT,GEN,HAVEN,REIN,ARCH,REBLD > /dev/null 2>&1 &
wc -l recordings/competition_backup.jsonl        # must grow every few seconds
```

If the bot Mac loses its recording, AirDrop or `scp` that file to it and restart with
`FEED_LOG=recordings/competition_backup.jsonl zsh bot/run_live.sh`.

Rules: nobody trades on the bot key (it uses 120 of the team's 180 actions a minute). Do not restart the bot during a
storm unless it is broken: a restart during round 1 on the testnet missed half the storm's PnL.

---

## Derivatives (35%): reader confirms, clicker clicks, 2.5 minutes per event

Setup: `cd derivatives-overlay && npm run build`, load `derivatives-overlay/dist` in `chrome://extensions` (Developer
mode, Load unpacked), hard-reload the exchange tab. Header must say **DERIVATIVES**. Then the Edge tab's **Ready n/m**
box: every line green before the first event. A red or amber line says what is wrong and what fixes it (the Config field
to patch, or the key to type), e.g. `OIL contracts: none parsed -> Config symbolRegex`, `order form: not found -> Config
dom.qtyLabel / buyText / sellText`, `clock: rate 52, expected ~39 in R3`. `news` stays grey until the first headline, then
shows what was parsed from it. Press `Alt+1` on the OIL laptop and `Alt+2` on the PLANE laptop if you split underlyings.
Dry run `Alt+A`, `Alt+N`, look at the form, do not submit.

**The only human inputs on this desk:** (1) press **arm auto** on ONE laptop if the organisers allow a bot to click (else
the clicker clicks `Alt+N` tickets); (2) type a spot or vol (`Alt+S` / `Alt+V`, Enter, then `Alt+A`) only when a target
shows **needs you: ...**; (3) Round 3: pick the converter only when the Vol tab says **not identified** (P(ITM) and
vega also need the strike); (4) `Alt+P` the moment anything looks wrong. Everything else is automatic.

Scoring is the sum over rounds of rank^1.5: one bad round costs more than a great one earns. Be flat between events.

Each event, by the clock. Times are from the news (`NEWS IN m:ss` in the header):

| When | Reader | Clicker |
|---|---|---|
| news +0 s | targets appear amber. Compare spot and vol with the headline. Round 1: both numbers are in the news. Fix a wrong one: `Alt+S` / `Alt+V`, type, Enter. Then `Alt+A`. | wait |
| +5 s to +110 s | watch the queue; if the live spot warning appears at +60 s, re-check and `Alt+A` again | `Alt+N` (form fills: contract, BUY/SELL, Limit, qty, price) -> glance -> click the Buy/Sell button -> `Alt+N`. Switch the OIL/PLANE tab yourself when the ticket says so |
| +120 s snap | overlay switches to Risk | `Alt+F` loads closing tickets; click them until delta and vega are near zero |
| last 30 s | red **FLATTEN NOW** = still carrying risk | keep flattening; accept the spread |

Order budget: header `orders n/40` per minute, amber at 30, red at 36. The hourglass in the queue means over budget.

**Auto-pilot (built 2026-10-23).** Auto-confirm is on by default: when the news parses completely (spot plus the
announced IV in Round 1, spot plus all three analysts in Rounds 2 and 3) and the numbers pass the sanity bounds, the
targets are accepted without `Alt+A`. The reader only acts on a line that says "needs you: ..." under a target. In
Round 3 the converter is identified from the first analyst message by matching the market IV; the Vol tab says
"auto-identified" or asks you to pick. **Auto-submit is off by default.** If the organisers confirm a bot may submit,
press **arm auto** in the header (or Config -> Auto-submit): the overlay then loads, verifies and clicks each ticket
itself, edge tickets during the event, flatten tickets after the snap and in the open minutes before a day's first news,
at most 36 orders a minute. Flatten orders are priced up to 2% (at least 5 ticks) through the touch so one order clears
several levels: the snap-to-next-news window is only 30 s, and 12 of the 36 orders a minute are kept for it. The header shows a red AUTO ON badge; `Alt+P` pauses and
resumes; the Capture tab lists every auto submission with the exchange's answer. With it armed the clicker only watches
the queue and the Risk tab. Overnight drills (2026-10-24, mock, all ten events armed, real speed): EXPERIMENTS.md.

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
Checked on the live site the morning of 2026-10-24: 23 symbols (TOP_PEA.. series winners, RACE1_PEA .. RACE4_BIR,
SCORE_1ST / SCORE_2ND / SCORE_TOP2SUM), all map, competition "Mario Kart Series 1", everything halted until the open.
Only series 1 is listed; when the competition becomes "Series 2" the desk re-maps the same names as series 2 (races 5-8)
and needs the four series 1 results typed (or `--races "..." x4` on a restart). Binaries trade in whole points.

After every race, within seconds: `race <Birdo> <Daisy> <Peach> <Yoshi>` with the overall finishing places (1-12) in
that alphabetical order, from the stream, or with names in any order: `race peach 5 birdo 1 yoshi 9 daisy 2` (first
three letters are enough). A bad line is refused with the reason. Typo: `undo`, retype. The dashboard reprices all 46
contracts and recomputes the **model sd** column (how much the fair moves between reasonable model settings); the
engine demands at least that much edge, so before race 1 the score contracts need 3-5 points of edge, not 2.

**The only human inputs on this desk:** the `race ...` line after each race, `cpu 0` after race 1 if all four humans
finished behind several CPUs, and (without organiser approval of bot clicks) clicking the prepared order. Everything
else is automatic; with `--auto-execute` the clicking is too.

After race 1 only: if the humans all finished behind several CPUs, `cpu 0`; if a human won outright and the others were
top 4, leave it.

Clicker: the action list is best first. Orange rows show settlement guarantees (race-winner sets sum to 100; series-winner
sets pay 100 to 200 because every tied winner pays 50; top-2 equals #1 + #2). Multi-leg guarantees require every leg to
fill at the stated prices. Recheck available size and positions after each fill. Then consider model edges. Click
**prepare** on a row (or type `prepare N`): the exchange tab's form fills; you click the submit button. Size is already
inside the position limit and the book. Browser cap is 40 orders a minute, about one every 1.5 s.

**Auto-execute (if the organisers approve bot submission):** start with `python3 mario/desk.py --auto-execute`. The desk
then prefills and clicks the submit button itself, arbs first, inside the 40-orders-a-minute cap, and the only human
step is typing `race P1 P2 P3 P4` after each race. The status line shows AUTO-EXECUTE ON and the orders sent this
minute; `stop` pauses it, `go` resumes, `orders` lists every order and whether it filled. An `INCOMPLETE ARB` line means
one leg of a riskless set did not go: send the missing legs by hand. Without approval leave the flag off and click.

Sanity checks the clicker can do without the model: before race 1 every race-winner and series-winner is worth about
25. Do not pay above about 45 for a race favourite after one win. After two races, a series lead of 6-9 points is about
85%, 10 or more about 95%. #1 score settles near 48 with sd 7 before the series; maximum possible 60. Top-2 total
maximum 108.

Settlements: race winners after each race, series contracts after races 4 and 8. Series 2 contracts are not listed
during series 1 (checked on the live site).

If it breaks: dashboard not refreshing -> Chrome tab closed or logged out; the desk reopens the tab, log in again.
Prefill fails -> type the symbol, side, size and price from the row by hand: group tab, outcome row, BUY/SELL, Limit,
Qty, Price (whole points for binaries), then the "Buy N SYMBOL" button (Cmd+Enter also submits). "X is halted ·
orders rejected" in place of the form means the organisers have not opened that symbol. Desk dead -> `python3
mario/pricer.py --races ...`, type `race ...` and `fair` in the terminal and trade from that.

---

## Before you leave tonight

- [x] Schedule: no overlap. Per case: Hurricane = one laptop runs the bot, one watches the log, two watch the exchange UI and the
      clock. Derivatives = OIL laptop (the only one that may arm auto), PLANE laptop, one reader on the news, one on Risk.
      Mario = one desk laptop, one typist watching the stream, one clicker, one on the dashboard checking fills and limits.
- [x] Hurricane: the full-size `run_live.sh` bot traded testnet seasons all night (00:22-07:50, `recordings/bot_live.log`
      SEASON END lines): ten complete seasons, realized + last-mark unrealized +4.2k, -0.7k, +8.3k, +7.3k, +2.7k, +1.4k,
      +13.6k, -0.5k, +11.1k, +14.4k (training-overlap seasons, not out-of-sample; the simulator's verify mean is 9.9k deep / 6.4k thin).
- [x] Derivatives: real-speed drills with auto armed over all ten mock events (`node scripts/drill-autopilot.mjs --fast 1`,
      overnight 2026-10-24; results in EXPERIMENTS.md).
- [x] Mario: 8-race auto-execute drills against the mock (`out/mario_drill/run_drill.sh`, overnight 2026-10-24).
- [ ] Charge laptops. Business casual. Check-in 8:00-8:30, 34 N Loop Rd, Roosevelt Island.
