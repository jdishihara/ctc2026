#!/bin/zsh
# Kill switch: stop the restart wrapper and the bot, cancel every resting order, print positions.
#   bot/stop.sh            # testnet
#   bot/stop.sh --flatten  # also send market-ish limit orders to close every position (asks first)
cd "$(dirname "$0")/.." || exit 1
URL=${CTC_URL:-https://cornelltradingcompetition.org}
KEY=$(cat .botkey)
echo "stopping wrapper and bot"
pkill -f "bot/run_live.sh" 2>/dev/null
sleep 0.5
pkill -f "bot/live.py" 2>/dev/null
sleep 1
if pgrep -f "bot/live.py" >/dev/null; then echo "bot still alive, killing hard"; pkill -9 -f "bot/live.py"; fi
echo "cancelling all orders"
curl -s -X DELETE -H "X-API-Key: $KEY" -H "User-Agent: ctc2026-bot/1.0" "$URL/api/v1/orders/all"; echo
echo "positions:"
curl -s -H "X-API-Key: $KEY" -H "User-Agent: ctc2026-bot/1.0" "$URL/api/v1/positions"; echo
if [[ "$1" == "--flatten" ]]; then
  echo "flattening positions"
  python3 - "$URL" "$KEY" <<'EOF'
import json, sys, urllib.request
url, key = sys.argv[1], sys.argv[2]
H = {"X-API-Key": key, "User-Agent": "ctc2026-bot/1.0", "Content-Type": "application/json"}
def call(method, path, body=None):
    req = urllib.request.Request(url + "/api/v1" + path, data=json.dumps(body).encode() if body else None, method=method, headers=H)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)
pos = call("GET", "/positions")
plist = pos if isinstance(pos, list) else pos.get("positions", pos)
items = plist.items() if isinstance(plist, dict) else [(p.get("symbol"), p.get("quantity", p.get("position"))) for p in plist]
for sym, q in items:
    if not q:
        continue
    book = call("GET", f"/orderbook/{sym}")
    bids, asks = book.get("bids", []), book.get("asks", [])
    if q > 0 and bids:
        px = round(bids[-1]["price"] if len(bids) < 3 else bids[2]["price"], 2)
        print(sym, "sell", q, "@", px, call("POST", "/orders", {"symbol": sym, "side": "sell", "order_type": "limit", "quantity": int(q), "price": px}))
    elif q < 0 and asks:
        px = round(asks[-1]["price"] if len(asks) < 3 else asks[2]["price"], 2)
        print(sym, "buy", -q, "@", px, call("POST", "/orders", {"symbol": sym, "side": "buy", "order_type": "limit", "quantity": int(-q), "price": px}))
EOF
  sleep 3
  echo "positions after flatten:"
  curl -s -H "X-API-Key: $KEY" -H "User-Agent: ctc2026-bot/1.0" "$URL/api/v1/positions"; echo
fi
echo "done"
