#!/bin/zsh
# Keep the live bot running on the testnet; restarts on crash; logs to recordings/bot_live.log
cd "$(dirname "$0")/.." || exit 1
KEY=$(cat .botkey)
FEED_LOG=${FEED_LOG:-recordings/testnet.jsonl}   # competition day: FEED_LOG=recordings/competition.jsonl zsh bot/run_live.sh
while true; do
  echo "=== start $(date)" >> recordings/bot_live.log
  python3 bot/live.py --key "$KEY" --rate 120 --feed-log "$FEED_LOG" "$@" >> recordings/bot_live.log 2>&1
  echo "=== exited $(date), restarting in 10 s" >> recordings/bot_live.log
  sleep 10
done
