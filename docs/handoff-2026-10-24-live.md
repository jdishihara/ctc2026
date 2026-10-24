# Live handoff: Hurricane season, Saturday 2026-10-24 (written 2:59 pm by the autonomous session)

Read this first in a fresh session. Jayden wants zero manual work; the bot trades on its own.

## What is running on this Mac (repo ~/projects/ctc2026, main at 4fc3212 + derivatives commits)
- `zsh bot/run_live.sh --rate 60 --max-cross 0.005` (restart wrapper) -> `python3 bot/live.py ... --feed-log recordings/competition.jsonl`
  started 2:58:35 pm. Flags passed after the wrapper's own `--rate 120` win (argparse last-wins).
- `data/starter_kit/record_feed.py --out recordings/competition.jsonl` and `scripts/record_books.py --out recordings/competition_books.jsonl`
  (started 2:11 pm by `scripts/launch_competition.sh`; they must keep running: the bot's self-restart replays that file).
- Log: `recordings/bot_live.log` (each start begins with `=== start <date>`). Control file: `recordings/control.txt` (empty).

## Timeline so far
- 2:50:32 pm market state `running`, clock rate 30. 2:51 storm 1 formed, trading eligible. 2:53:03 first fill.
- Round 1 whipsaw: bought PORT 200 @ 75.94 and HAVEN 250 @ 44.22 when the model's fair said "miss"; the next advisories
  turned the storm onto them; the bot flipped to short at ~62 / ~35. Realized about -8.4k by 2:57, unrealized positive.
- 2:43 pm restart with `--rate 60` (organisers: 60 orders/min per key, 180/team, 100 req/s, 25 feed connections).
- 2:58 pm restart with `--max-cross 0.005`: 39% of filled volume had been >1.5% through the mid (the house pulls quotes
  after advisories and only a 1,000-lot backstop 4-7% away remains); net slippage paid ~$4.3k. Now the bot posts inside
  0.5% of the mid and waits instead of hitting the backstop.

## How to check (every ~3 min)
```
L=$(awk '/^=== start/{n=NR} END{print n}' recordings/bot_live.log); tail -n +$L recordings/bot_live.log > /tmp/cur_bot.log
grep -v "^t=\|^snapshot processed\|^ORDER\|^FILL\|^CANCEL" /tmp/cur_bot.log | tail -5     # events (BLOCKED, feed hole, RESTARTING, announcements)
grep "^t=" /tmp/cur_bot.log | tail -1                                                      # pnl and positions (mid/fair/pos per symbol)
grep -c "HTTP 4\|HTTP 5\|Traceback" /tmp/cur_bot.log                                       # must stay 0
curl -s -H "X-API-Key: $(cat .botkey)" -H "User-Agent: ctc2026-bot/1.0" https://cornelltradingcompetition.org/api/v1/positions
```
Normal: `TRADING BLOCKED: incomplete weather history` for a few seconds at each round open; `snapshot processed` every 30 s;
`feed hole ... filled from the recorder's file` after a reconnect.
Act on: a persisting BLOCKED (see docs/gameday-sheets.md Hurricane table), HTTP errors, the bot gone from `pgrep -f bot/live.py`
(the wrapper restarts it in 10 s; if the wrapper itself is gone: `FEED_LOG=recordings/competition.jsonl nohup zsh bot/run_live.sh --rate 60 --max-cross 0.005 > /dev/null 2>&1 &`).
Emergency stop: `zsh bot/stop.sh` (cancels orders, prints positions; `--flatten` closes positions).

## Rules
- No code changes during the season. Flag-only restarts are acceptable when the live evidence is concrete (as above).
- Never a second trading process on the key. Do not arm the Derivatives browser overlay (it shows on the Hurricane page too; capture-only is harmless).
- Email jaydenishihara@gmail.com only for a blocking problem. Season ends ~4:10 pm; settlement after round 3.
- After the season: `bot/stop.sh` is NOT needed (positions settle); leave recorders until the state leaves `running`. Then write the
  result into EXPERIMENTS.md and docs/competition-results.md.
