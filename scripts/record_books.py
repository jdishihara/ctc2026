"""Poll GET /orderbook/{symbol} for all symbols every `--every` seconds and append to a jsonl file (for calibrating
the simulator's liquidity ladder). Runs until killed."""
import argparse, json, time, urllib.request
from pathlib import Path
ap = argparse.ArgumentParser(); ap.add_argument("--url", default="https://cornelltradingcompetition.org"); ap.add_argument("--key", required=True)
ap.add_argument("--out", default="recordings/books.jsonl"); ap.add_argument("--every", type=float, default=5.0)
a = ap.parse_args()
H = {"User-Agent": "ctc2026-bot/1.0", "X-API-Key": a.key}
def get(p):
    with urllib.request.urlopen(urllib.request.Request(a.url + p, headers=H), timeout=10) as r:
        return json.load(r)
syms = list(get("/cases/hurricane.json")["limits"])
Path(a.out).parent.mkdir(exist_ok=True)
with open(a.out, "a") as f:
    while True:
        t0 = time.time()
        try:
            tm = get("/api/v1/competitions/time")
            for s in syms:
                b = get(f"/api/v1/orderbook/{s}")
                f.write(json.dumps({"t": t0, "time": tm.get("fictional_time"), "state": tm.get("state"), **b}) + "\n")
            f.flush()
        except Exception as exc:
            print("error", exc, flush=True)
        time.sleep(max(0.5, a.every - (time.time() - t0)))
