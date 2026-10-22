"""Run a strategy over research seasons in the offline simulator.

python scripts/backtest.py --strategy nowcast --seasons 451-600 --half-spread 0.0015
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc.sim import Sim
from ctc import strategies as S

STRATS = {
    "nothing": lambda a: S.DoNothing(),
    "final": lambda a: S.FinalReportOnly(min_edge=a.min_edge, edge_full=a.edge_full),
    "nowcast": lambda a: S.FairValueTrader(min_edge=a.min_edge, edge_full=a.edge_full, project=True),
    "noproject": lambda a: S.FairValueTrader(min_edge=a.min_edge, edge_full=a.edge_full, project=False),
    "analog": lambda a: S.FairValueTrader(min_edge=a.min_edge, edge_full=a.edge_full, analog=True, sd_mult=a.sd_mult,
                                          sigma=a.sigma, k=a.k, shift=not a.noshift),
}

def parse_seasons(spec, n):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-"); out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [s for s in out if 1 <= s <= n]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="nowcast", choices=list(STRATS))
    ap.add_argument("--seasons", default="451-600")
    ap.add_argument("--half-spread", type=float, default=0.0015)
    ap.add_argument("--latency", type=float, default=0.25)
    ap.add_argument("--depth", type=int, default=0, help="max fill per order per 2 s tick (0 = unlimited)")
    ap.add_argument("--min-edge", type=float, default=0.01)
    ap.add_argument("--edge-full", type=float, default=0.05)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--sd-mult", type=float, default=1.0)
    ap.add_argument("--sigma", type=float, default=25.0)
    ap.add_argument("--k", type=int, default=50)
    ap.add_argument("--noshift", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1] / "data"
    case = json.loads((root / "case.json").read_text())
    man = json.loads((root / "history" / "manifest.json").read_text())
    seasons = parse_seasons(a.seasons, len(man["seasons"]))
    rows = []; t0 = time.time(); by_sym = {}; by_round = {1: [], 2: [], 3: []}
    for n in seasons:
        meta = man["seasons"][n - 1]
        sim = Sim(root / "history" / meta["dir"], case, half_spread=a.half_spread, latency=a.latency, depth=a.depth or None, verbose=a.verbose)
        pnl = sim.run(STRATS[a.strategy](a))
        traded = sum(f.qty * f.price for f in sim.fills)
        for s_, v in sim.pnl_by_symbol().items():
            by_sym.setdefault(s_, []).append(v)
        prev = 0.0
        for r_ in (1, 2, 3):
            by_round[r_].append(sim.round_pnl.get(r_, prev) - prev); prev = sim.round_pnl.get(r_, prev)
        rows.append((n, pnl, len(sim.fills), traded, sim.rejected, [s["pattern"] for s in meta["storms"]]))
        if a.verbose or len(seasons) <= 5:
            print(f"season {n:3d}: pnl {pnl:10.0f}  fills {len(sim.fills):4d}  notional {traded:12.0f}  rejected {sim.rejected}  patterns {rows[-1][5]}")
    p = np.array([r[1] for r in rows])
    print(f"\n{a.strategy}: {len(rows)} seasons in {time.time()-t0:.0f}s | mean {p.mean():.0f} median {np.median(p):.0f} "
          f"sd {p.std():.0f} min {p.min():.0f} p10 {np.percentile(p,10):.0f} p90 {np.percentile(p,90):.0f} max {p.max():.0f} | "
          f"losing seasons {(p<0).mean():.0%} | fills/season {np.mean([r[2] for r in rows]):.0f}")
    print("  per symbol mean pnl: " + "  ".join(f"{k} {np.mean(v):+.0f}" for k, v in by_sym.items()))
    print("  per round mean pnl:  " + "  ".join(f"R{k} {np.mean(v):+.0f} (sd {np.std(v):.0f})" for k, v in by_round.items()))
    Path(a.out).mkdir(exist_ok=True)
    with open(Path(a.out) / f"backtest_{a.strategy}.csv", "w") as f:
        f.write("season,pnl,fills,notional,rejected,patterns\n")
        for r in rows:
            f.write(f"{r[0]},{r[1]:.2f},{r[2]},{r[3]:.0f},{r[4]},{'|'.join(r[5])}\n")

if __name__ == "__main__":
    main()
