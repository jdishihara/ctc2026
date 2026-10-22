"""Summarise recorded order books (scripts/record_books.py) into a liquidity ladder per symbol: cumulative size
available within given relative distances of the mid, and the top-of-book spread. Writes ctc/ladder.json."""
import json, sys, numpy as np
from pathlib import Path
path = Path(sys.argv[1] if len(sys.argv) > 1 else "recordings/books.jsonl")
BANDS = [0.0025, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12]
rows = [json.loads(l) for l in open(path)]
by = {}
for r in rows:
    if not r.get("bids") or not r.get("asks") or r.get("state") != "running":
        continue
    bid, ask = r["bids"][0]["price"], r["asks"][0]["price"]; mid = (bid + ask) / 2
    cum = []
    for side in ("bids", "asks"):
        lv = [(abs(x["price"] - mid) / mid, x["quantity"]) for x in r[side]]
        cum.append([sum(q for d, q in lv if d <= b) for b in BANDS])
    by.setdefault(r["symbol"], []).append(((ask - bid) / mid, cum[0], cum[1]))
ladder = {}
print(f"{len(rows)} snapshots; bands {BANDS}")
print("sym    spread%  median cumulative size within band (bid side / ask side)")
for s, v in by.items():
    sp = float(np.median([x[0] for x in v])); b = np.median([x[1] for x in v], 0); a = np.median([x[2] for x in v], 0)
    ladder[s] = {"spread": sp, "bands": BANDS, "bid": b.tolist(), "ask": a.tolist(), "n": len(v)}
    print(f"{s:6s} {sp*100:5.2f}   " + " ".join(f"{int(x):4d}" for x in b) + "  / " + " ".join(f"{int(x):4d}" for x in a))
json.dump(ladder, open("ctc/ladder.json", "w"), indent=1)
