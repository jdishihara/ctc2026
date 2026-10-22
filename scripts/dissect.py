"""Dissect losing seasons: PnL per symbol per round, and what the ensemble believed when the losing trades were made.

python3 scripts/dissect.py --seasons 526-600 --refill 30 --ladder-scale 0.5 --worst 8
"""
import argparse, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc.sim import Sim
from ctc.ladder import Ladder
from ctc import strategies as S
from ctc.valuation import SYMS
from backtest import parse_seasons


class Recorder(S.FairValueTrader):
    """FairValueTrader that records per-round PnL by symbol and the model's belief at each fill."""
    def on_start(self, sim):
        super().on_start(sim)
        self.round_marks = {}; self.end_mid = {}; self.trades = []; self._nfills = 0

    def on_round(self, sim):
        if sim.round > 1:
            self.round_marks[sim.round - 1] = sim.pnl_by_symbol()
            self.end_mid[sim.round - 1] = dict(sim.mid)

    def on_quotes(self, sim):
        super().on_quotes(sim)
        new = sim.fills[self._nfills:]
        if new:
            post = self.model.posterior
            top = max(post, key=post.get) if post else None
            ent = -sum(p * np.log(p) for p in post.values() if p > 0) if post else float("nan")
            age = self.model.last_obs["age"] if self.model.last_obs else -1
            md = self.model
            phase = "pre" if md.round < sim.round else "storm" if md.storm_active else "aftermath" if not md.storm_reported else "post"
            for f in new:
                self.trades.append(dict(t=f.t, round=sim.round, sym=f.symbol, side=f.side, qty=f.qty, px=f.price, phase=phase,
                                        fair=self.fair.get(f.symbol), sd=self.model.fair_sd.get(f.symbol), top=top, ent=ent, age=age,
                                        reported=self.model.storm_reported))
            self._nfills = len(sim.fills)

    def on_end(self, sim):
        self.round_marks[3] = sim.pnl_by_symbol()
        self.end_mid[3] = dict(sim.mid)
        for t in self.trades:                      # pnl of each fill marked at the end of its round
            t["mtm"] = (1 if t["side"] == "buy" else -1) * t["qty"] * (self.end_mid[t["round"]][t["sym"]] - t["px"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="526-600"); ap.add_argument("--refill", type=float, default=10.0)
    ap.add_argument("--ladder-scale", type=float, default=1.0); ap.add_argument("--worst", type=int, default=6)
    ap.add_argument("--min-edge", type=float, default=0.02); ap.add_argument("--edge-full", type=float, default=0.03)
    ap.add_argument("--sd-mult", type=float, default=0.7); ap.add_argument("--sigma", type=float, default=15.0); ap.add_argument("--k", type=int, default=100)
    ap.add_argument("--json", default=None, help="write per-season detail here")
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1] / "data"
    case = json.loads((root / "case.json").read_text()); man = json.loads((root / "history" / "manifest.json").read_text())
    res = {}
    for n in parse_seasons(a.seasons, len(man["seasons"])):
        meta = man["seasons"][n - 1]
        sim = Sim(root / "history" / meta["dir"], case, ladder=Ladder(refill_secs=a.refill, scale=a.ladder_scale))
        st = Recorder(min_edge=a.min_edge, edge_full=a.edge_full, analog=True, sd_mult=a.sd_mult, sigma=a.sigma, k=a.k, passive=0.75, warmup=20, max_cross=0.02)
        pnl = sim.run(st)
        cell = {}
        prev = {s: 0.0 for s in SYMS}
        for r in (1, 2, 3):
            m = st.round_marks.get(r, prev)
            for s in SYMS:
                cell[(s, r)] = m[s] - prev[s]
            prev = m
        res[n] = dict(pnl=pnl, cell=cell, trades=st.trades, patterns=[s["pattern"] for s in meta["storms"]],
                      flips=[s.get("turned_erratic_at") for s in meta["storms"]])
    # aggregate: which cells lose, how big are the tails
    allcells = defaultdict(list)
    for n, r in res.items():
        for k, v in r["cell"].items():
            allcells[k].append(v)
    print("per symbol x round: mean / p10 / min / share of total loss cells < -1000")
    for s in SYMS:
        print(f"  {s:5s} " + "  ".join(f"R{r}: {np.mean(allcells[(s,r)]):+6.0f} {np.percentile(allcells[(s,r)],10):+6.0f} {np.min(allcells[(s,r)]):+7.0f} n<-1k {sum(v<-1000 for v in allcells[(s,r)]):2d}" for r in (1, 2, 3)))
    print("\nfill pnl to round-end mark, by phase x symbol group (sum over seasons; n fills):")
    groups = {"phys": ["PORT", "ISLE", "AQUA", "GRID", "FERRY"], "rebuild": ["RECON", "MAT", "GEN"], "ins": ["HAVEN", "REIN"], "etf": ["ARCH", "REBLD"]}
    for ph in ("pre", "storm", "aftermath", "post"):
        line = []
        for g, syms in groups.items():
            tr = [t for r in res.values() for t in r["trades"] if t["phase"] == ph and t["sym"] in syms]
            line.append(f"{g} {sum(t['mtm'] for t in tr):+8.0f} ({len(tr):4d})")
        print(f"  {ph:9s} " + "  ".join(line))
    print("by storm age bucket during the storm (all symbols):")
    for lo, hi in ((0, 60), (60, 120), (120, 240), (240, 360), (360, 481)):
        tr = [t for r in res.values() for t in r["trades"] if t["phase"] == "storm" and lo <= t["age"] < hi]
        print(f"  age {lo:3d}-{hi:3d}: {sum(t['mtm'] for t in tr):+8.0f} ({len(tr):4d} fills)  ins {sum(t['mtm'] for t in tr if t['sym'] in groups['ins']):+8.0f}")
    pn = np.array([r["pnl"] for r in res.values()])
    print(f"\nmean {pn.mean():.0f} p10 {np.percentile(pn,10):.0f} min {pn.min():.0f} losing {(pn<0).mean():.0%}")
    worst = sorted(res, key=lambda n: res[n]["pnl"])[: a.worst]
    for n in worst:
        r = res[n]
        print(f"\n=== season {n}: pnl {r['pnl']:.0f} patterns {r['patterns']} flips {r['flips']}")
        cells = sorted(r["cell"].items(), key=lambda kv: kv[1])[:5]
        print("  worst cells: " + ", ".join(f"{s} R{rd} {v:+.0f}" for (s, rd), v in cells))
        for (s, rd), v in cells[:3]:
            tr = [t for t in r["trades"] if t["sym"] == s and t["round"] == rd]
            if not tr:
                continue
            buys = sum(t["qty"] for t in tr if t["side"] == "buy"); sells = sum(t["qty"] for t in tr if t["side"] == "sell")
            first = tr[0]
            print(f"    {s} R{rd}: {len(tr)} fills, bought {buys} sold {sells}; first fill age {first['age']} top={first['top']} ent={first['ent']:.2f} "
                  f"fair {first['fair']:.2f} sd {first['sd']:.2f} px {first['px']:.2f} reported={first['reported']}")
            ages = [t["age"] for t in tr]; tops = {t["top"] for t in tr}
            print(f"    ages {min(ages)}..{max(ages)}  posterior tops seen {tops}  true pattern {r['patterns'][rd-1]} flip {r['flips'][rd-1]}")
    if a.json:
        Path(a.json).write_text(json.dumps({n: {"pnl": r["pnl"], "cell": {f"{s}:{rd}": v for (s, rd), v in r["cell"].items()},
                                                 "patterns": r["patterns"], "trades": r["trades"]} for n, r in res.items()}, default=float))


if __name__ == "__main__":
    main()
