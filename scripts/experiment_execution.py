"""Predeclared cadence/sizing experiments; tune and verify are separate invocations.

    python scripts/experiment_execution.py --workers 4
    python scripts/experiment_execution.py --split verify --configs baseline,cadence8

Every replay enforces the live bot's 120-action budget. Each job has a distinct
output file; the runner never selects a candidate using verification results.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc.ladder import Ladder
from ctc.sim import Sim
from ctc.strategies import FairValueTrader

ROOT = Path(__file__).resolve().parents[1]
BASE = dict(min_edge=0.025, edge_full=0.03, analog=True, sd_mult=0.7,
            sigma=15.0, k=100, cone_w=1.0, cone_s0=20.0, passive=0.75,
            warmup=20.0, max_cross=0.02, carry=0.5, ent_cut=1.2)
CONFIGS = {"baseline": {}, "cadence8": {"rebalance_every": 8.0},
           "cadence4": {"rebalance_every": 4.0}, "cadence30": {"rebalance_every": 30.0},
           "ramp1": {"edge_ramp": 0.01}, "ramp3": {"edge_ramp": 0.03},
           "wind": {"wind_condition": 1.0}, "final_exact": {"final_exact": True},
           "final_edge05": {"final_exact": True, "final_edge": 0.005},
           "final_edge1": {"final_exact": True, "final_edge": 0.01},
           "final_full": {"final_exact": True, "final_edge": 0.005, "final_edge_full": 0.01},
           "final_limit": {"final_exact": True, "final_edge": 0.005, "final_edge_full": 0.005}}
REGIMES = {"deep": (10.0, 1.0), "thin": (30.0, 0.5)}


class AuditedSim(Sim):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.peak_actions = self.total_actions = self.rate_blocks = 0

    def _action_ok(self):
        accepted = super()._action_ok()
        if accepted:
            self.total_actions += 1
            self.peak_actions = max(self.peak_actions, len(self.actions))
        else:
            self.rate_blocks += 1
        return accepted


def evaluate(name, regime, seasons, latency):
    case = json.loads((ROOT / "data/case.json").read_text())
    manifest = json.loads((ROOT / "data/history/manifest.json").read_text())
    params = {**BASE, **CONFIGS[name]}
    refill, scale = REGIMES[regime]
    rows = []
    start = time.monotonic()
    for n in seasons:
        folder = ROOT / "data/history" / manifest["seasons"][n - 1]["dir"]
        sim = AuditedSim(folder, case, rate_limit=120, latency=latency,
                         ladder=Ladder(refill_secs=refill, scale=scale))
        pnl = sim.run(FairValueTrader(**params))
        rows.append(dict(season=n, pnl=pnl, fills=len(sim.fills), rejected=sim.rejected,
                         notional=sum(f.qty * f.price for f in sim.fills),
                         peak_actions=sim.peak_actions, actions=sim.total_actions,
                         rate_blocks=sim.rate_blocks, by_symbol=sim.pnl_by_symbol()))
    p = np.array([r["pnl"] for r in rows])
    summary = dict(mean=float(p.mean()), median=float(np.median(p)),
                   p10=float(np.percentile(p, 10)), minimum=float(p.min()),
                   losing=int((p < 0).sum()), fills=float(np.mean([r["fills"] for r in rows])),
                   peak_actions=max(r["peak_actions"] for r in rows),
                   rate_blocks=sum(r["rate_blocks"] for r in rows),
                   rejected=sum(r["rejected"] for r in rows))
    return dict(config=name, regime=regime, parameters=params, rate_limit=120,
                latency=latency, elapsed_seconds=time.monotonic() - start,
                summary=summary, rows=rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=["tune", "verify"], default="tune")
    ap.add_argument("--configs", default=",".join(CONFIGS))
    ap.add_argument("--seasons", help="optional comma-separated subset of the selected split")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--latency", type=float, default=0.25)
    ap.add_argument("--out")
    args = ap.parse_args()
    names = args.configs.split(",")
    if any(n not in CONFIGS for n in names) or len(names) != len(set(names)):
        ap.error("configs must be distinct known configuration names")
    if args.split == "verify" and (len(names) > 2 or "baseline" not in names):
        ap.error("verify only the frozen candidate and baseline")
    allowed = range(451, 526) if args.split == "tune" else range(526, 601)
    seasons = [int(n) for n in args.seasons.split(",")] if args.seasons else list(allowed)
    if not seasons or len(seasons) != len(set(seasons)) or any(n not in allowed for n in seasons):
        ap.error("seasons must be distinct members of the selected split")
    out = Path(args.out) if args.out else ROOT / "out" / f"execution-{args.split}-{time.time_ns()}"
    try:
        out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        ap.error(f"output directory already exists: {out}; choose a fresh run directory")
    (out / "invocation.json").write_text(json.dumps(dict(
        split=args.split, seasons=seasons, latency=args.latency, rate_limit=120,
        configurations={name: {**BASE, **CONFIGS[name]} for name in names},
        regimes=REGIMES), indent=2) + "\n")
    print(f"output: {out}", flush=True)
    results = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(evaluate, name, regime, seasons, args.latency)
                   for name in names for regime in REGIMES]
        for future in as_completed(futures):
            result = future.result()
            name, regime = result["config"], result["regime"]
            (out / f"{name}-{regime}.json").write_text(json.dumps(result, indent=2) + "\n")
            results.setdefault(name, {})[regime] = result["summary"]
            print(json.dumps({"config": name, "regime": regime, **result["summary"]}), flush=True)
    for name in names:
        deep, thin = results[name]["deep"], results[name]["thin"]
        score = 0.5 * (deep["mean"] + thin["mean"] + min(0, thin["p10"]))
        print(f"score {name}: {score:.2f}", flush=True)


if __name__ == "__main__":
    main()
