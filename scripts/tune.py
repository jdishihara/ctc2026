"""Unattended parameter search for the analog strategy.

Each trial samples a parameter set, backtests it on the TUNE seasons under two liquidity regimes (unlimited depth and
100 shares per tick at a 0.3% half spread), and appends a row to out/tune/ledger.csv. The score is the mean of the
two regimes' mean PnL, penalised by the worst-decile loss. Every `--verify-every` trials the best-so-far is re-run on
the VERIFY seasons, which the search never sees, and written to out/tune/best.json. Resumable: re-running appends.

    python3 scripts/tune.py --hours 8
"""
import argparse, csv, json, random, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "tune"; OUT.mkdir(parents=True, exist_ok=True)
LEDGER, BEST = OUT / "ledger.csv", OUT / "best.json"
TUNE, VERIFY = "451-525", "526-600"
SPACE = {
    "min_edge": [0.005, 0.01, 0.015, 0.02, 0.03],
    "edge_full": [0.03, 0.05, 0.08, 0.12],
    "sd_mult": [0.5, 0.7, 1.0, 1.5, 2.0, 3.0],
    "sigma": [15, 25, 40],
    "k": [30, 50, 100],
}
REGIMES = [("deep", ["--liquidity", "ladder", "--refill", "10"]), ("thin", ["--liquidity", "ladder", "--refill", "30", "--ladder-scale", "0.5"])]


def run(params: dict, seasons: str, regime_args: list[str]) -> dict:
    cmd = [sys.executable, str(ROOT / "scripts" / "backtest.py"), "--strategy", "analog", "--seasons", seasons, "--out", str(OUT / "runs")]
    for k, v in params.items():
        cmd += [f"--{k.replace('_', '-')}", str(v)]
    cmd += regime_args
    txt = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT).stdout
    line = next((l for l in txt.splitlines() if l.startswith("analog:")), "")
    toks = line.replace("|", " ").split()
    def grab(name):
        return float(toks[toks.index(name) + 1]) if name in toks else float("nan")
    losing = next((t for t in toks if t.endswith("%")), "nan%")
    return {"mean": grab("mean"), "median": grab("median"), "p10": grab("p10"), "min": grab("min"), "losing": float(losing.rstrip("%"))}


def score(res: dict) -> float:
    return 0.5 * (res["deep"]["mean"] + res["thin"]["mean"]) + 0.5 * min(0.0, res["thin"]["p10"])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--hours", type=float, default=8.0); ap.add_argument("--verify-every", type=int, default=5); ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args(); rng = random.Random(a.seed)
    rows = list(csv.DictReader(LEDGER.open())) if LEDGER.exists() else []
    seen = {r["params"] for r in rows}
    best = json.loads(BEST.read_text()) if BEST.exists() else {"score": -1e18}
    t_end = time.time() + a.hours * 3600; n = 0
    while time.time() < t_end:
        params = {k: rng.choice(v) for k, v in SPACE.items()}
        if n == 0 and not rows:
            params = {"min_edge": 0.02, "edge_full": 0.03, "sd_mult": 0.7, "sigma": 15, "k": 100}   # baseline first (strategy params; cone 1.0 / s0 20 / carry 0.5 / ent_cut 1.2 come from the backtest defaults since 2026-10-23)
        if (ROOT / "scripts" / "tune_space.json").exists():
            SPACE.update(json.loads((ROOT / "scripts" / "tune_space.json").read_text()))
        key = json.dumps(params, sort_keys=True)
        if key in seen:
            continue
        res = {name: run(params, TUNE, args) for name, args in REGIMES}
        sc = score(res)
        row = {"time": time.strftime("%Y-%m-%d %H:%M"), "params": key, "score": f"{sc:.0f}",
               **{f"{r}_{m}": f"{res[r][m]:.0f}" for r in res for m in ("mean", "median", "p10", "min", "losing")}}
        new = not LEDGER.exists()
        with LEDGER.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row)); (w.writeheader() if new else None); w.writerow(row)
        seen.add(key); rows.append(row); n += 1
        print(f"[{n}] score {sc:.0f} deep {res['deep']['mean']:.0f} thin {res['thin']['mean']:.0f} p10 {res['thin']['p10']:.0f}  {key}", flush=True)
        if sc > best["score"]:
            ver = {name: run(params, VERIFY, args) for name, args in REGIMES}
            best = {"score": sc, "params": params, "tune": res, "verify": ver, "time": row["time"]}
            BEST.write_text(json.dumps(best, indent=1))
            print(f"    new best; verify deep {ver['deep']['mean']:.0f} thin {ver['thin']['mean']:.0f} (p10 {ver['thin']['p10']:.0f})", flush=True)


if __name__ == "__main__":
    main()
