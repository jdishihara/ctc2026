"""Model-uncertainty check for the Mario pricer: how much do the fair values move when the model's free parameters
(race noise sd, human skill prior sd, CPU strength prior) are changed within a plausible range?

    python3 mario/robustness.py --races "1 2 5 9"              # fairs under every grid member + the spread (sd) per contract
    python3 mario/robustness.py --races "1 2 5 9" "3 1 7 2"
    python3 mario/robustness.py brier --n 150 --seed 1          # Brier of the base pricer vs the ensemble mean under three truths

The desk uses `ensemble_sd` to widen its trading margin where the parameterisations disagree (mario/engine.py,
Params.model_sd_k): a contract whose fair swings 8 points between reasonable models is not a 3-point edge.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mario.pricer import Pricer, POINTS  # noqa: E402
from mario.contracts import RACERS  # noqa: E402

# (noise sd, skill sd, cpu prior mean): the base is (1.0, 1.0, -0.6); grid_for() re-centres the CPU column on the desk's prior
GRID = [(1.0, 1.0, -0.6), (0.7, 1.0, -0.6), (1.4, 1.0, -0.6), (1.0, 0.6, -0.6), (1.0, 1.4, -0.6), (1.0, 1.0, -0.3), (1.0, 1.0, 0.0), (1.4, 0.6, -0.3)]


def grid_for(cpu_base: float = -0.6) -> list[tuple]:
    """The grid with its CPU column shifted so that the base member uses cpu_base (the desk's `cpu` command)."""
    return [(n, s, round(c + 0.6 + cpu_base, 2)) for n, s, c in GRID]


def ensemble(races: list[list[int]], grid=None, n_particles: int = 2000, n_sims: int = 1500, seed: int = 0, cpu_base: float = -0.6) -> list[dict]:
    """fairs() of one pricer per grid member, all fitted to the same races."""
    out = []
    for i, (noise, ssd, cpu) in enumerate(grid if grid is not None else grid_for(cpu_base)):
        p = Pricer(n_particles=n_particles, n_sims=n_sims, skill_sd=ssd, noise_sd=noise, cpu_skill=cpu, seed=seed + 17 * i)
        for r in races:
            p.add_race(r)
        out.append(p.fairs())
    return out


def symbol_model_sd(fairs_list: list[dict], roles: dict[str, tuple]) -> dict[str, float]:
    """ensemble_sd keyed by exchange symbol, for mario/engine.py."""
    sd = ensemble_sd(fairs_list); out = {}
    for sym, role in roles.items():
        key = (role[0], role[1])
        if key not in sd:
            continue
        if role[0] in ("race", "swin"):
            if role[2] in RACERS:
                out[sym] = float(sd[key][RACERS.index(role[2])])
        else:
            out[sym] = float(sd[key])
    return out


def ensemble_sd(fairs_list: list[dict]) -> dict:
    """Per role: sd across the ensemble of the contract fair (points of a 100-settling binary; points for scores)."""
    sd = {}
    for key in fairs_list[0]:
        if not isinstance(key, tuple):
            continue
        kind = key[0]
        if kind in ("race", "swin"):
            arr = np.array([f[key] for f in fairs_list], dtype=float)
            if kind == "race":
                arr = arr * 100.0
            sd[key] = arr.std(0)
        else:
            arr = np.array([f[key][0] for f in fairs_list], dtype=float)
            sd[key] = float(arr.std())
    return sd


def table(races: list[list[int]]) -> str:
    fl = ensemble(races)
    sd = ensemble_sd(fl)
    n = len(races)
    s = n // 4 + 1 if n < 8 else 2
    lines = [f"races {races}: fairs under {len(GRID)} parameterisations (noise sd, skill sd, cpu prior); last column = sd across them"]
    hdr = "  contract          " + " ".join(f"{a:.1f}/{b:.1f}/{c:+.1f}" for a, b, c in GRID) + "    sd"
    lines.append(hdr)
    race_no = n + 1
    if race_no <= 8:
        for i, h in enumerate(RACERS):
            vals = [100 * f[("race", race_no)][i] for f in fl]
            lines.append(f"  R{race_no} win {h:6s}   " + " ".join(f"{v:12.1f}" for v in vals) + f"  {sd[('race', race_no)][i]:5.1f}")
    for i, h in enumerate(RACERS):
        vals = [f[("swin", s)][i] for f in fl]
        lines.append(f"  S{s} win {h:6s}   " + " ".join(f"{v:12.1f}" for v in vals) + f"  {sd[('swin', s)][i]:5.1f}")
    for k, lab in (("s1", "#1 score"), ("s2", "#2 score"), ("top2", "top-2 total")):
        vals = [f[(k, s)][0] for f in fl]
        lines.append(f"  S{s} {lab:12s}  " + " ".join(f"{v:12.1f}" for v in vals) + f"  {sd[(k, s)]:5.1f}")
    return "\n".join(lines)


def brier(n: int, seed: int) -> str:
    """Simulate series under three truths; score the next-race-winner and series-winner probabilities after 1-3 races
    of (a) the base pricer and (b) the ensemble mean. Lower is better; 0.75 is the flat 25% quote (race winner)."""
    rng = np.random.default_rng(seed)
    truths = {"as modelled (1.0, 1.0, -0.6)": (1.0, 1.0, -0.6), "noisier races (1.5, 1.0, -0.6)": (1.5, 1.0, -0.6),
              "strong CPUs, close humans (1.0, 0.6, 0.0)": (1.0, 0.6, 0.0)}
    out = []
    for name, (noise, ssd, cpu) in truths.items():
        res = {k: [] for k in ("race_base", "race_ens", "swin_base", "swin_ens", "disagree")}
        for t in range(n):
            h = rng.normal(0, ssd, 4); c = rng.normal(cpu, 0.5, 8)
            races, pts = [], np.zeros(4)
            for r in range(4):
                perf = np.concatenate([h, c]) + rng.normal(0, noise, 12)
                place = (np.argsort(np.argsort(-perf)) + 1)[:4]
                races.append(place.tolist()); pts += POINTS[place - 1]
            top = pts.max(); win_true = (pts == top) * (100.0 / (pts == top).sum())
            for k in (1, 2, 3):
                fl = ensemble(races[:k], n_particles=1000, n_sims=800, seed=t * 7 + k)
                base = fl[0]; ens_race = np.mean([f[("race", k + 1)] for f in fl], 0); ens_swin = np.mean([f[("swin", 1)] for f in fl], 0)
                nxt = np.array(races[k]); truth_race = (nxt == nxt.min()).astype(float)
                res["race_base"].append(((base[("race", k + 1)] - truth_race) ** 2).sum())
                res["race_ens"].append(((ens_race - truth_race) ** 2).sum())
                res["swin_base"].append(((base[("swin", 1)] / 100 - win_true / 100) ** 2).sum())
                res["swin_ens"].append(((ens_swin / 100 - win_true / 100) ** 2).sum())
                res["disagree"].append(ensemble_sd(fl)[("swin", 1)].mean())
        out.append(f"truth {name}: race-winner Brier base {np.mean(res['race_base']):.3f} ens {np.mean(res['race_ens']):.3f} | "
                   f"series-winner Brier base {np.mean(res['swin_base']):.3f} ens {np.mean(res['swin_ens']):.3f} | mean ensemble sd of series fair {np.mean(res['disagree']):.1f} pts")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", default="table", choices=["table", "brier"])
    ap.add_argument("--races", nargs="*", default=[])
    ap.add_argument("--n", type=int, default=100); ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    races = [[int(x) for x in r.split()] for r in a.races]
    if a.cmd == "brier":
        print(brier(a.n, a.seed))
    else:
        print(table(races))


if __name__ == "__main__":
    main()
