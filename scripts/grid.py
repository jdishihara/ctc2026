"""Focused parameter grid for the analog strategy (deterministic complement to scripts/tune.py's random search).

Runs every combination in GRID on the TUNE seasons under both liquidity regimes with a pool of parallel backtests,
appends rows to out/tune/ledger.csv (same columns as tune.py) and prints the top configurations by tune.py's score.
Then verifies the top --verify-top configurations on the VERIFY seasons.

    python3 scripts/grid.py --workers 6 --verify-top 3
"""
import argparse, csv, itertools, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tune import run, score, TUNE, VERIFY, REGIMES, LEDGER   # noqa: E402

GRID = {
    "min_edge": [0.015, 0.02, 0.025],
    "edge_full": [0.03, 0.04],
    "sd_mult": [0.5, 0.7, 0.85],
    "carry": [0.35, 0.5],
}


def evaluate(params: dict, seasons: str) -> dict:
    return {name: run(params, seasons, args) for name, args in REGIMES}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6); ap.add_argument("--verify-top", type=int, default=3)
    ap.add_argument("--grid", default=None, help="JSON overriding GRID")
    a = ap.parse_args()
    grid = dict(GRID, **(json.loads(a.grid) if a.grid else {}))
    combos = [dict(zip(grid, vals)) for vals in itertools.product(*grid.values())]
    done = {r["params"] for r in csv.DictReader(LEDGER.open())} if LEDGER.exists() else set()
    todo = [c for c in combos if json.dumps(c, sort_keys=True) not in done]
    print(f"{len(combos)} combinations, {len(todo)} to run, {a.workers} in parallel (2 backtests each)", flush=True)
    results = []
    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        for params, res in zip(todo, ex.map(lambda p: evaluate(p, TUNE), todo)):
            sc = score(res); key = json.dumps(params, sort_keys=True)
            row = {"time": time.strftime("%Y-%m-%d %H:%M"), "params": key, "score": f"{sc:.0f}",
                   **{f"{r}_{m}": f"{res[r][m]:.0f}" for r in res for m in ("mean", "median", "p10", "min", "losing")}}
            new = not LEDGER.exists()
            with LEDGER.open("a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(row)); (w.writeheader() if new else None); w.writerow(row)
            results.append((sc, params, res))
            print(f"[{len(results)}/{len(todo)} {time.time()-t0:.0f}s] score {sc:.0f} deep {res['deep']['mean']:.0f} (p10 {res['deep']['p10']:.0f}) thin {res['thin']['mean']:.0f} (p10 {res['thin']['p10']:.0f})  {key}", flush=True)
    results.sort(key=lambda x: -x[0])
    print("\ntop by tune score:")
    for sc, params, res in results[:8]:
        print(f"  {sc:6.0f}  deep {res['deep']['mean']:.0f} (p10 {res['deep']['p10']:.0f}) thin {res['thin']['mean']:.0f} (p10 {res['thin']['p10']:.0f})  {json.dumps(params, sort_keys=True)}")
    print("\nverify (526-600):")
    with ThreadPoolExecutor(a.workers) as ex:
        tops = [p for _, p, _ in results[: a.verify_top]]
        for params, ver in zip(tops, ex.map(lambda p: evaluate(p, VERIFY), tops)):
            print(f"  deep {ver['deep']['mean']:.0f} (p10 {ver['deep']['p10']:.0f}, min {ver['deep']['min']:.0f}, losing {ver['deep']['losing']:.0f}%) thin {ver['thin']['mean']:.0f} (p10 {ver['thin']['p10']:.0f}, min {ver['thin']['min']:.0f}, losing {ver['thin']['losing']:.0f}%)  {json.dumps(params, sort_keys=True)}", flush=True)


if __name__ == "__main__":
    main()
