"""Exact settlement rules for the rebuilders: value = base + A * (1 - exp(-(sum_k a_k * cum_damage_k + sum_k o_k * outage_k))).

The season-level single-exposure fit (fit_valuation.py) leaves residuals of about 1 point for RECON and MAT; a weighted
sum of company damages inside the saturation fits the settlements exactly. Fit on seasons 1-450, report 451-600.
Writes valuation_params.json[sym] = {"kind": "rebuild_w", "params": [base, A, a_PORT..a_FERRY, o_PORT..o_FERRY]} and resid_sd.

    python3 scripts/fit_rebuilders.py --write
"""
import json, sys, numpy as np
from pathlib import Path
from scipy.optimize import least_squares
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc.wind import SiteState, PHYS
root = Path(__file__).resolve().parents[1] / "data"; case = json.load(open(root / "case.json")); man = json.load(open(root / "history/manifest.json"))
PP = Path(__file__).resolve().parents[1] / "ctc" / "valuation_params.json"
cum, out, sett = [], [], []
for s in man["seasons"]:
    feed = [json.loads(l) for l in open(root / "history" / s["dir"] / "feed.jsonl")]
    states = {k: SiteState(case, k) for k in PHYS}
    for st in s["storms"]:
        for k in PHYS: states[k].new_storm()
        for m in feed:
            if m["round"] == st["round"] and m["type"] == "storm":
                for k in PHYS: states[k].observe(m)
    cum.append([sum(st["damage_pct"][k] for st in s["storms"]) for k in PHYS]); out.append([states[k].weighted_outage() for k in PHYS])
    sett.append(json.load(open(root / "history" / s["dir"] / "settlement.json")))
cum, out = np.array(cum), np.array(out); X = np.c_[cum, out]
tr, te = slice(0, 450), slice(450, None)
def f(p, X):
    return p[0] + p[1] * (1 - np.exp(-np.clip(X @ p[2:], 0, None)))
P = json.loads(PP.read_text())
for sym in ("RECON", "MAT", "GEN"):
    y = np.array([s_[sym] for s_ in sett])
    x0 = [30, 20] + [0.01] * 5 + [0.0] * 5
    res = least_squares(lambda p: f(p, X[tr]) - y[tr], x0=x0, bounds=([0, 0] + [0] * 10, [100, 100] + [1] * 10), max_nfev=20000, xtol=1e-12, ftol=1e-12)
    rm_tr = np.sqrt(np.mean((f(res.x, X[tr]) - y[tr]) ** 2)); rm_te = np.sqrt(np.mean((f(res.x, X[te]) - y[te]) ** 2))
    old = P.get("resid_sd", {}).get(sym)
    print(f"{sym}: base {res.x[0]:.3f} A {res.x[1]:.3f} dmg weights {np.round(res.x[2:7], 5)} outage weights {np.round(res.x[7:], 6)}  rmse fit {rm_tr:.4f} holdout {rm_te:.4f} (was {old})")
    if "--write" in sys.argv:
        P[sym + "_exact"] = {"kind": "rebuild_w", "params": res.x.tolist()}        # used when valuation.EXACT_REBUILD
        P.setdefault("resid_sd_exact", {})[sym] = float(rm_te)
if "--write" in sys.argv:
    PP.write_text(json.dumps(P, indent=1)); print("written")
