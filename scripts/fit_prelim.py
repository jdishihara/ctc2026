"""Preliminary-report error model: combine the preliminary damage report with our own end-of-storm nowcast.

Fit on seasons 1-450:  final_k = a_k + b_k * prelim_k + c_k * nowcast_k  per company, residual sd;
                       final_loss = a + b * prelim_loss + c * storm_loss(nowcast), residual sd.
Writes valuation_params.json["prelim"]. Reports fit and holdout (451-600) rmse of prelim alone, nowcast alone, combined.

    python3 scripts/fit_prelim.py --write
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc.wind import PHYS
from ctc.valuation import SeasonModel, storm_loss
root = Path(__file__).resolve().parents[1] / "data"
case = json.load(open(root / "case.json")); man = json.load(open(root / "history/manifest.json"))
PP = Path(__file__).resolve().parents[1] / "ctc" / "valuation_params.json"


def rows(seasons):
    """One row per storm: prelim damage (5), nowcast damage at the prelim (5), final damage (5), prelim loss, final loss."""
    out = []
    for s in seasons:
        md = SeasonModel(case); pre = None
        for l in open(root / "history" / s["dir"] / "feed.jsonl"):
            m = json.loads(l)
            if m["type"] == "damage_report" and m["stage"] == "preliminary":
                now = {k: md.states[k].storm_damage() for k in PHYS}
                pre = (m, now)
                continue                                   # do not let the model absorb the prelim
            if m["type"] == "damage_report" and m["stage"] == "final" and pre is not None:
                p, now = pre
                out.append([p["damage_pct"][k] for k in PHYS] + [now[k] for k in PHYS] + [m["damage_pct"][k] for k in PHYS]
                           + [p["industry_loss_musd"], storm_loss(now), m["industry_loss_musd"]])
                pre = None
            md.on_message(m)
    return np.array(out)


def fit(R):
    res = {"dmg": {}, "dmg_sd": {}}
    for i, k in enumerate(PHYS):
        X = np.c_[np.ones(len(R)), R[:, i], R[:, 5 + i]]; y = R[:, 10 + i]
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        res["dmg"][k] = beta.tolist(); res["dmg_sd"][k] = float(np.std(y - X @ beta))
    X = np.c_[np.ones(len(R)), R[:, 15], R[:, 16]]; y = R[:, 17]
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    res["loss"] = beta.tolist(); res["loss_sd"] = float(np.std(y - X @ beta))
    return res


def report(R, res, label):
    rm = lambda e: np.sqrt(np.mean(e ** 2))
    print(f"{label}: {len(R)} storms   rmse prelim / nowcast / combined")
    for i, k in enumerate(PHYS):
        a, b, c = res["dmg"][k]; y = R[:, 10 + i]
        print(f"  {k:5s} {rm(y-R[:,i]):5.2f} / {rm(y-R[:,5+i]):5.2f} / {rm(y-(a+b*R[:,i]+c*R[:,5+i])):5.2f}   (a {a:+.2f} b {b:.2f} c {c:.2f})")
    a, b, c = res["loss"]; y = R[:, 17]
    print(f"  loss  {rm(y-R[:,15]):5.1f} / {rm(y-R[:,16]):5.1f} / {rm(y-(a+b*R[:,15]+c*R[:,16])):5.1f}   (a {a:+.1f} b {b:.2f} c {c:.2f})")


Rf = rows(man["seasons"][:450]); Rh = rows(man["seasons"][450:])
res = fit(Rf)
report(Rf, res, "fit 1-450"); report(Rh, res, "holdout 451-600")
if "--write" in sys.argv:
    P = json.loads(PP.read_text()); P["prelim"] = res; PP.write_text(json.dumps(P, indent=1)); print("written")
