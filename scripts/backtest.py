"""Run a strategy over research seasons in the offline simulator.

python scripts/backtest.py --strategy nowcast --seasons 451-600 --half-spread 0.0015
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc.sim import Sim
from ctc.ladder import Ladder
from ctc import strategies as S

STRATS = {
    "nothing": lambda a: S.DoNothing(),
    "final": lambda a: S.FinalReportOnly(min_edge=a.min_edge, edge_full=a.edge_full),
    "nowcast": lambda a: S.FairValueTrader(min_edge=a.min_edge, edge_full=a.edge_full, project=True),
    "noproject": lambda a: S.FairValueTrader(min_edge=a.min_edge, edge_full=a.edge_full, project=False),
    "analog": lambda a: S.FairValueTrader(min_edge=a.min_edge, edge_full=a.edge_full, analog=True, sd_mult=a.sd_mult,
                                          basket_edge=a.basket_edge, basket_participation=a.basket_participation,
                                          rebalance_every=a.rebalance_every, edge_ramp=a.edge_ramp,
                                          final_exact=a.final_exact, final_edge=a.final_edge, final_edge_full=a.final_edge_full, final_every=a.final_every,
                                          wind_condition=a.wind_condition,
                                          sigma=a.sigma, k=a.k, shift=not a.noshift, cone_w=a.cone_w, isl_w=a.isl_w, cone_s0=a.cone_s0, cone_nu=a.cone_nu, vel_w=a.vel_w, vel_sd=a.vel_sd, cone_all=a.cone_all, loss_limit=a.loss_limit or None, prior_mode=a.prior, passive=a.passive, warmup=a.warmup, future_sd=a.future_sd, fair_jump=a.fair_jump, max_cross=a.max_cross, carry=a.carry, ent_cut=a.ent_cut, rebuild_min_edge=a.rebuild_min_edge, late_cut=a.late_cut),
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
    ap.add_argument("--liquidity", default="ladder", choices=["ladder", "spread"], help="ladder = measured testnet book; spread = flat half-spread model")
    ap.add_argument("--refill", type=float, default=10.0, help="ladder: seconds for consumed depth to regenerate")
    ap.add_argument("--ladder-scale", type=float, default=1.0, help="ladder: multiply all sizes")
    ap.add_argument("--min-edge", type=float, default=0.03)
    ap.add_argument("--edge-full", type=float, default=0.03)
    ap.add_argument('--basket-edge', type=float, default=0.01, help='net quoted ETF/basket edge (0 disables the overlay)')
    ap.add_argument('--basket-participation', type=float, default=0.5, help='maximum fraction of displayed external depth per closing leg')
    ap.add_argument("--rebalance-every", type=float, default=15.0, help="seconds between normal rebalances")
    ap.add_argument("--rate-limit", type=int, default=120, help="order actions/minute; matches the live bot")
    ap.add_argument("--edge-ramp", type=float, default=0.0, help="experimental minimum excess-edge sizing width (0 = original)")
    ap.add_argument("--wind-condition", type=float, default=0.0, help="experimental training-derived strength response (0 = original)")
    ap.add_argument("--final-exact", action=argparse.BooleanOptionalAction, default=True,
                    help="use exact final rules after three reports and complete recorded weather")
    ap.add_argument("--final-edge", type=float, default=0.01, help="entry floor in the exact final phase (0 = normal floor)")
    ap.add_argument("--final-edge-full", type=float, default=0.005, help="full-size edge in the exact final phase (0 = normal)")
    ap.add_argument("--final-every", type=float, default=0.0, help="rebalance cadence (s) once the exact final phase is active (0 = the normal --rebalance-every)")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--sd-mult", type=float, default=0.7)
    ap.add_argument("--sigma", type=float, default=15.0)
    ap.add_argument("--k", type=int, default=100)
    ap.add_argument("--noshift", action="store_true")
    ap.add_argument("--cone-w", type=float, default=1.0, help="analog likelihood power for the official advisory cone (0 = off; 1.0 accepted 2026-10-23)")
    ap.add_argument("--cone-s0", type=float, default=20.0, help="spread floor (map units) added in quadrature to the cone spread")
    ap.add_argument("--cone-nu", type=float, default=0.0, help="Student-t degrees of freedom for the cone likelihood (0 = Gaussian)")
    ap.add_argument("--vel-w", type=float, default=0.0, help="analog kernel weight on the current velocity (0 = off)")
    ap.add_argument("--vel-sd", type=float, default=0.3, help="velocity kernel scale, map units per second")
    ap.add_argument("--cone-all", action="store_true", help="use the cones of all official advisories so far, not only the latest")
    ap.add_argument("--isl-w", type=float, default=0.0, help="analog likelihood power for the advisory island probabilities (0 = off)")
    ap.add_argument("--prior", default="sample", choices=["sample", "point"], help="future storms: historical sample or point mean")
    ap.add_argument("--passive", type=float, default=0.75, help="rest orders inside the spread at edge = passive*floor (0 = off)")
    ap.add_argument("--future-sd", type=float, default=0.0, help="multiple of the future-storm valuation sd added to the edge floor")
    ap.add_argument("--warmup", type=float, default=20.0, help="seconds after each round opens with no trading")
    ap.add_argument("--fair-jump", type=float, default=0.0, help="skip a symbol for one cycle when its fair moved by more than this fraction (0 = off)")
    ap.add_argument("--max-cross", type=float, default=0.02, help="aggressive orders never pay more than this fraction through the touch (0 = off; 0.02 accepted 2026-10-22)")
    ap.add_argument("--carry", type=float, default=0.5, help="between storms the position limit is carry x the exchange limit (1 = off; 0.5 accepted 2026-10-23 together with the cone)")
    ap.add_argument("--ent-cut", type=float, default=1.2, help="do not add while the pattern posterior entropy exceeds this, nats (0 = off)")
    ap.add_argument("--loss-limit", type=float, default=0.0, help="per symbol per round: stop adding after losing this much (0 = off)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--late-cut", type=float, default=0.0, help="do not add to a position once the storm is older than this (s; 0 = off)")
    ap.add_argument("--rebuild-min-edge", type=float, default=0.0, help="edge floor for RECON/MAT/GEN (0 = the global floor); for --exact-rebuild")
    ap.add_argument("--exact-rebuild", action="store_true", help="exact RECON/MAT/GEN settlement rules (rejected on verify PnL)")
    a = ap.parse_args()
    if a.exact_rebuild:
        import ctc.valuation as _V; _V.EXACT_REBUILD = True
    root = Path(__file__).resolve().parents[1] / "data"
    case = json.loads((root / "case.json").read_text())
    man = json.loads((root / "history" / "manifest.json").read_text())
    seasons = parse_seasons(a.seasons, len(man["seasons"]))
    rows = []; t0 = time.time(); by_sym = {}; by_round = {1: [], 2: [], 3: []}
    for n in seasons:
        meta = man["seasons"][n - 1]
        lad = Ladder(refill_secs=a.refill, scale=a.ladder_scale) if a.liquidity == "ladder" else None
        sim = Sim(root / "history" / meta["dir"], case, half_spread=a.half_spread, latency=a.latency, depth=a.depth or None,
                  rate_limit=a.rate_limit, verbose=a.verbose, ladder=lad)
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
