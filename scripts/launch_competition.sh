#!/bin/zsh
# Competition-day launch for the Hurricane bot, in the order of docs/gameday-sheets.md. Run from the repo root on the ONE
# laptop that trades:  zsh scripts/launch_competition.sh
# It stops the overnight testnet processes, updates main, runs preflight, and starts the feed recorder, the book recorder
# and the bot (FEED_LOG=recordings/competition.jsonl). It refuses to start if preflight reports a failure.
set -u
cd "$(dirname "$0")/.." || exit 1
echo "== stopping the overnight bot and recorders"
zsh bot/stop.sh
pkill -f "data/starter_kit/record_feed.py" 2>/dev/null; pkill -f "scripts/record_books.py" 2>/dev/null; sleep 1
echo "== git pull"
git pull --ff-only || { echo "git pull failed; fix the tree first"; exit 1; }
(nohup caffeinate -i -s -t 36000 >/dev/null 2>&1 &)   # a fresh one: an older caffeinate may expire mid-case
echo "== preflight"
python3 bot/preflight.py --no-sim | tee recordings/preflight_competition.log
grep -q " 0 failures" recordings/preflight_competition.log || { echo "preflight failed: not starting"; exit 1; }
echo "== starting recorders"
nohup python3 data/starter_kit/record_feed.py --url wss://cornelltradingcompetition.org --key "$(cat .botkey)" \
      --out recordings/competition.jsonl --symbols PORT,ISLE,AQUA,GRID,FERRY,RECON,MAT,GEN,HAVEN,REIN,ARCH,REBLD > /dev/null 2>&1 &
nohup python3 scripts/record_books.py --key "$(cat .botkey)" --out recordings/competition_books.jsonl > /dev/null 2>&1 &
sleep 3
echo "== starting the bot"
FEED_LOG=recordings/competition.jsonl nohup zsh bot/run_live.sh > /dev/null 2>&1 &
sleep 8
echo "== processes"; pgrep -fl "record_feed|record_books|run_live|bot/live.py" | cut -c1-120
echo "== last log lines"; tail -8 recordings/bot_live.log | cut -c1-200
echo "watch with: tail -f recordings/bot_live.log"
