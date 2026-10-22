"""Summarise recorded order books (scripts/record_books.py) into a liquidity ladder per symbol: cumulative size
available within given relative distances of the mid, and the top-of-book spread. Writes ctc/ladder.json.

    python3 scripts/calibrate_book.py recordings/books.jsonl [--before EPOCH] [--after EPOCH] [--out ctc/ladder.json] [--stat median|p25]

Snapshots that carry our own open orders (recorder field "ours": [{symbol, side, price, quantity}]) have those sizes
removed first, so the ladder is other participants' liquidity only.
"""
import argparse, json, numpy as np
from pathlib import Path
ap = argparse.ArgumentParser()
ap.add_argument("path", nargs="?", default="recordings/books.jsonl")
ap.add_argument("--before", type=float, default=None); ap.add_argument("--after", type=float, default=None)
ap.add_argument("--out", default="ctc/ladder.json"); ap.add_argument("--stat", default="median", choices=["median", "p25"])
a = ap.parse_args()
BANDS = [0.0025, 0.005, 0.01, 0.02, 0.03, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12]
rows = [json.loads(l) for l in open(a.path)]
by = {}
for r in rows:
    if not r.get("bids") or not r.get("asks") or r.get("state") != "running":
        continue
    if (a.before and r["t"] >= a.before) or (a.after and r["t"] < a.after):
        continue
    ours = {}
    for o in r.get("ours") or []:
        if o.get("symbol") == r["symbol"]:
            k = ("bids" if o["side"] == "buy" else "asks", round(float(o["price"]), 2))
            ours[k] = ours.get(k, 0) + int(o.get("quantity", 0)) - int(o.get("filled_quantity", 0) or 0)
    levels = {side: [(x["price"], max(0, x["quantity"] - ours.get((side, round(x["price"], 2)), 0))) for x in r[side]] for side in ("bids", "asks")}
    levels = {side: [(p, q) for p, q in lv if q > 0] for side, lv in levels.items()}
    if not levels["bids"] or not levels["asks"]:
        continue
    bid, ask = levels["bids"][0][0], levels["asks"][0][0]; mid = (bid + ask) / 2
    cum = []
    for side in ("bids", "asks"):
        lv = [(abs(p - mid) / mid, q) for p, q in levels[side]]
        cum.append([sum(q for d, q in lv if d <= b) for b in BANDS])
    by.setdefault(r["symbol"], []).append(((ask - bid) / mid, cum[0], cum[1]))
agg = (lambda v: np.median(v, 0)) if a.stat == "median" else (lambda v: np.percentile(v, 25, axis=0))
ladder = {}
print(f"{len(rows)} snapshots; bands {BANDS}; stat {a.stat}")
print("sym    spread%  cumulative size within band (bid side / ask side)")
for s, v in by.items():
    sp = float(np.median([x[0] for x in v])); b = agg([x[1] for x in v]); ak = agg([x[2] for x in v])
    ladder[s] = {"spread": sp, "bands": BANDS, "bid": b.tolist(), "ask": ak.tolist(), "n": len(v)}
    print(f"{s:6s} {sp*100:5.2f}   " + " ".join(f"{int(x):4d}" for x in b) + "  / " + " ".join(f"{int(x):4d}" for x in ak) + f"   n={len(v)}")
json.dump(ladder, open(a.out, "w"), indent=1)
