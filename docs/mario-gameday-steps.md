# Mario Markets: step by step (CTC 2026, Saturday 2026-10-24)

Mario Markets is 20% of the overall score. Four humans (Birdo, Daisy, Peach, Yoshi) and eight CPUs race; two series
of four races. We trade 23 contracts per series on cornelltradingcompetition.org (checked on the live site this
morning: competition "Mario Kart Series 1", everything halted until the organisers open it):

- TOP_PEA / TOP_DAI / TOP_YOS / TOP_BIR: series winner (pays 100, 50 each if tied), limit 200, whole-point prices.
- RACE1_PEA ... RACE4_BIR: race winner = best-placed human of that race (a CPU may win overall), limit 100, whole points.
- SCORE_1ST (max 60), SCORE_2ND (max 54), SCORE_TOP2SUM (max 108): the top two human series scores and their sum, limit 1000.

Only series 1 is listed now. Series 2 should appear as "Mario Kart Series 2" with the same symbol names; the desk
handles the switch (step 11).

## Roles (four people, four laptops)

| role | who | does |
|---|---|---|
| Desk | Jayden | runs `mario/desk.py` and the Chrome window it opens; the desk's prefill types into THAT window, so the clicker sits here |
| Typist | one person | watches the race stream and types each result into the dashboard within seconds of the finish |
| Checker | one person | second pair of eyes on every typed result (reads the places off the results screen aloud), watches the order budget and positions in the exchange UI |
| Watcher | one person | the dashboard on their own laptop: PnL, fills, anything that looks like nonsense |

With the organisers' approval of bot clicks the desk also clicks (`--auto-execute`) and the only human input is the
typed race result. Without it, the Desk person clicks.

## Before the open (start 30 minutes early)

1. Desk laptop, in `~/projects/ctc2026`:
   ```
   git pull && git status            # clean, on main
   python3 -m pytest -q tests/test_mario_*.py     # all pass
   python3 mario/desk.py --host 0.0.0.0           # add --auto-execute ONLY if the organisers said a bot may click submit
   ```
   A Chrome window opens on the exchange. Log in with Google there (once; the login is kept in its own profile).
2. Open http://localhost:8787 on the desk laptop. The status line must say `connected`. In the log you must see
   `23 contracts mapped as series 1 (competition 'Mario Kart Series 1'; races 1-4)` and no `UNMAPPED`.
   Type `map` in the command box: every row has a role. If anything is UNMAPPED or wrong, stop and tell Jayden
   (fix `mario/contracts.json`, restart the desk).
3. Find the desk laptop's address: `ipconfig getifaddr en0`. The other three open `http://<that address>:8787`
   (same Wi-Fi). Everyone also opens the exchange UI in their own browser, logged in, to watch.
4. Ask in the Slack #questions channel: "May a bot click the submit button for us in Mario Markets, with a human only
   typing the race results?" (pre-fill with a human click was approved on 10/23). If yes: on the desk laptop press
   Ctrl-C, restart with `python3 mario/desk.py --host 0.0.0.0 --auto-execute`, then type `go` only when the status
   shows AUTO-EXECUTE and the market is open.
5. Sanity before race 1: every race-winner and series-winner should be about 25; #1 score about 48, #2 about 37,
   top-2 about 85. The dashboard shows a `fair` for each; if a fair is wildly off those, tell Jayden.
6. While the market is halted the dashboard shows books empty and no actions. That is correct. Do not type anything.

## During the races

7. After EVERY race, the Typist types the overall finishing places (1-12) of the four humans:
   `race <Birdo> <Daisy> <Peach> <Yoshi>`, for example `race 1 2 5 9`, or with names in any order:
   `race peach 5 birdo 1 yoshi 9 daisy 2` (first three letters are enough). The Checker reads the places off the
   results screen and confirms. A wrong line: type `undo`, then the correct line. The log answers
   `race N recorded: BIRDO 1 DAISY 2 ...` and `fairs recomputed after N race(s)`. Everything else is automatic.
8. After race 1 only: if all four humans finished behind several CPUs, type `cpu 0`. If a human won outright and the
   others were top 4, leave it.
9. Clicking (no auto-execute). The action list is best first; orange rows are settlement guarantees (riskless if every
   leg fills), white rows are model edges. For each row from the top: click **prepare** (or type `prepare N`) ->
   the exchange window selects the contract, side and Limit and types the size and price -> glance that the button
   reads `Buy <size> <symbol>` (or Sell) as on the row -> click it -> next row. Multi-leg orange rows: prepare and
   click every leg (`prepare N 2`, `prepare N 3` ...); if a leg does not fill, send the rest anyway or close the
   filled legs. Pace: about one order every 1.5 s (the browser limit is 40 a minute). Never type a price that is not a
   whole number on a binary; the form rejects it.
10. Clicking (auto-execute on). Watch the log: `ORDER <sym> <side> <qty> @ <px> (arb|edge) -> sent`, then `filled`,
    `partial`, `open (resting)` or `unconfirmed`. `INCOMPLETE ARB` = one leg of a riskless set did not go: the Desk
    person sends the missing legs by hand (step 9). Anything that looks wrong: type `stop` (sent orders stay), fix,
    `go`. `orders` lists everything sent this session.
11. After race 4 the series 1 contracts settle and the competition becomes "Mario Kart Series 2" with the same symbol
    names. The desk logs `23 contracts mapped as series 2 (... races 5-8)`. Type race 4's result immediately if it is
    not in yet; until it is, the log shows `WARNING: series 2 contracts but only 3 race result(s) entered`. Do not
    restart the desk. Races 5-8 are typed exactly like races 1-4 (`race ...`, the desk knows they are series 2).
12. After race 8 everything settles. Stop clicking; leave the desk running until the organisers close the case.

## Reading the dashboard

- Actions table: `profit` is in contract points (PnL at settlement if the fair is right). `model sd` is how much the
  fair moves between reasonable model settings; the desk already demands that much edge.
- Contracts table: bid/ask, fair, sd, hard bounds (a score contract can never settle outside them), position, avg.
- PnL: mark-to-fair next to the exchange's own number.
- Rules of thumb without the model: before race 1 every binary is worth about 25; do not pay above about 45 for a race
  favourite after one win; after two races a series lead of 6-9 points is about 85%, 10+ about 95%.

## If something breaks

| symptom | do |
|---|---|
| dashboard says stale / `poll failed` | the Chrome tab closed or logged out; the desk reopens it, log in again |
| `prepare` says `X is halted` | the organisers have not opened that symbol; wait |
| `prepare` says no row / no button | type the order by hand in the exchange window: group tab, outcome row, BUY/SELL, Limit, Qty, Price, the Buy/Sell button |
| desk crashed | restart it with every result so far: `python3 mario/desk.py --host 0.0.0.0 --races "1 2 5 9" "3 1 7 2" ...` |
| desk dead for good | `python3 mario/pricer.py --races "..." ...`, type `race ...` and `fair` in the terminal, trade from that |
| a stream of rejected orders | price off the tick (whole points for binaries), over the position limit (100 race / 200 series / 1000 score), or over 40 orders a minute |
