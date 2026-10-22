"""Sample of historical storms for the future-storm prior: per storm in seasons 1-450, company damage (5), weighted
outage seconds added by that storm (5) and insured loss. Writes ctc/storm_sample.npz (used by ctc/valuation.py)."""
import json, sys, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc.wind import SiteState, PHYS
root = Path(__file__).resolve().parents[1] / "data"
case = json.load(open(root / "case.json")); man = json.load(open(root / "history/manifest.json"))
dmg, out, loss = [], [], []
for s in man["seasons"][:450]:
    feed = [json.loads(l) for l in open(root / "history" / s["dir"] / "feed.jsonl")]
    states = {k: SiteState(case, k) for k in PHYS}
    for st in s["storms"]:
        before = {k: states[k].weighted_outage() for k in PHYS}
        for k in PHYS: states[k].new_storm()
        for m in feed:
            if m["round"] == st["round"] and m["type"] == "storm":
                for k in PHYS: states[k].observe(m)
        dmg.append([st["damage_pct"][k] for k in PHYS]); out.append([states[k].weighted_outage() - before[k] for k in PHYS]); loss.append(st["industry_loss_musd"])
dmg, out, loss = np.array(dmg), np.array(out), np.array(loss)
np.savez_compressed(Path(__file__).resolve().parents[1] / "ctc" / "storm_sample.npz", dmg=dmg, outage=out, loss=loss)
print(f"{len(loss)} storms; mean dmg {dict(zip(PHYS, np.round(dmg.mean(0), 2)))} mean loss {loss.mean():.1f} sd {loss.std():.1f} mean outage {np.round(out.mean(0), 1)}")
print("loss quantiles", np.percentile(loss, [10, 25, 50, 75, 90, 99]).round(0))
