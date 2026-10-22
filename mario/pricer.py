"""Mario Markets pricer: Monte Carlo fair values for every contract, with Bayesian updating of racer skill from results.

Model: each race, racer i (4 humans + 8 CPUs) draws performance = skill_i + noise. Finishing order is the sort of
performance. Points: 15,12,10,9,8,7,6,5,4,3,2,1 by overall position. Human skills start from a common prior
(identical characters and karts) and are updated from observed finishing positions by importance-reweighting a
particle set of skill vectors.

Usage (interactive):
    python3 mario/pricer.py
    > race 1 2 5 9            # finishing positions (1..12) of humans A B C D in the latest race
    > fair                    # print fair values of all unsettled contracts
    > prob                    # pattern of race-winner probabilities for the next race
    > undo                    # drop the last race
Non-interactive:
    python3 mario/pricer.py --races "1 2 5 9" "3 1 7 2"
"""
from __future__ import annotations
import argparse, sys
import numpy as np

POINTS = np.array([15, 12, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
HUMANS = ["A", "B", "C", "D"]


class Pricer:
    def __init__(self, n_particles: int = 4000, n_sims: int = 2000, skill_sd: float = 1.0, noise_sd: float = 1.0,
                 cpu_skill: float = -0.3, cpu_sd: float = 0.5, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        self.P, self.S, self.noise = n_particles, n_sims, noise_sd
        # particles: human skills (P,4) and cpu skills (P,8)
        self.h = self.rng.normal(0, skill_sd, (n_particles, 4))
        self.c = self.rng.normal(cpu_skill, cpu_sd, (n_particles, 8))
        self.w = np.ones(n_particles) / n_particles
        self.races: list[list[int]] = []          # human finishing positions per race (1..12)
        self.series_len = 4

    # ---- likelihood of an observed race under a particle: P(humans finish at those overall positions) ----
    def _loglik(self, positions: list[int], n_mc: int = 64) -> np.ndarray:
        """Approximate log-likelihood per particle by Monte Carlo: fraction of simulated races whose human
        finishing-order ranks match the observed ranks among humans, weighted by closeness of overall positions."""
        obs = np.array(positions)
        perf = np.concatenate([self.h, self.c], 1)[:, None, :] + self.rng.normal(0, self.noise, (self.P, n_mc, 12))
        order = np.argsort(-perf, axis=2)                      # (P, n_mc, 12) racer index by finishing place
        place = np.argsort(order, axis=2) + 1                  # (P, n_mc, 12) finishing place by racer
        hp = place[:, :, :4]                                   # human places
        # score: squared distance between simulated and observed human places, soft-matched
        d2 = ((hp - obs) ** 2).sum(2)                          # (P, n_mc)
        lik = np.exp(-d2 / 8.0).mean(1) + 1e-12
        return np.log(lik)

    def add_race(self, positions: list[int]) -> None:
        assert len(positions) == 4 and len(set(positions)) == 4 and all(1 <= p <= 12 for p in positions)
        self.races.append(list(positions))
        self.w = self.w * np.exp(self._loglik(positions))
        self.w /= self.w.sum()
        ess = 1.0 / (self.w ** 2).sum()
        if ess < self.P / 2:                                   # resample + jitter
            idx = self.rng.choice(self.P, self.P, p=self.w)
            self.h = self.h[idx] + self.rng.normal(0, 0.15, self.h.shape)
            self.c = self.c[idx] + self.rng.normal(0, 0.1, self.c.shape)
            self.w = np.ones(self.P) / self.P

    def undo(self) -> None:
        races = self.races[:-1]
        self.__init__(self.P, self.S, seed=int(self.rng.integers(1e9)))
        for r in races:
            self.add_race(r)

    # ---- simulation of the remaining races of the current series ----
    def simulate(self, races_done_in_series: list[list[int]], n_remaining: int) -> dict:
        idx = self.rng.choice(self.P, self.S, p=self.w)
        skills = np.concatenate([self.h[idx], self.c[idx]], 1)       # (S, 12)
        pts = np.zeros((self.S, 4))
        for r in races_done_in_series:
            pts += POINTS[np.array(r) - 1]
        next_win = None
        for k in range(n_remaining):
            perf = skills + self.rng.normal(0, self.noise, skills.shape)
            place = np.argsort(np.argsort(-perf, axis=1), axis=1) + 1
            hp = place[:, :4]
            pts += POINTS[hp - 1]
            if k == 0:
                best = hp.min(1, keepdims=True)
                next_win = (hp == best).mean(0)
        srt = np.sort(pts, axis=1)[:, ::-1]
        top = pts.max(1, keepdims=True); tied = (pts == top); nt = tied.sum(1, keepdims=True)
        series_win = (tied * (100.0 / nt * (nt == 1) + 50.0 * (nt > 1))).mean(0)   # 100 if sole, 50 if tied
        return {"race_winner": next_win, "series_winner": series_win,
                "score1": srt[:, 0].mean(), "score2": srt[:, 1].mean(), "top2": (srt[:, 0] + srt[:, 1]).mean(),
                "score1_sd": srt[:, 0].std(), "score2_sd": srt[:, 1].std(), "top2_sd": (srt[:, 0] + srt[:, 1]).std()}

    def fair(self) -> str:
        n = len(self.races)
        series = n // self.series_len + 1 if n < 8 else 2
        done = self.races[(series - 1) * self.series_len: n]
        remaining = self.series_len - len(done)
        out = [f"races so far: {n}  (series {series}, {remaining} race(s) left in it)"]
        if remaining == 0 and series == 1:
            series, done, remaining = 2, [], 4
            out.append("series 1 settled; pricing series 2")
        r = self.simulate(done, remaining)
        skill = (self.w[:, None] * self.h).sum(0)
        out.append("human skill estimate: " + "  ".join(f"{h} {s:+.2f}" for h, s in zip(HUMANS, skill)))
        if remaining:
            out.append("next race winner (binary, settles 100): " + "  ".join(f"{h} {p*100:5.1f}" for h, p in zip(HUMANS, r["race_winner"])))
        out.append(f"series {series} winner (binary, 50 on tie):    " + "  ".join(f"{h} {p:5.1f}" for h, p in zip(HUMANS, r["series_winner"])))
        out.append(f"series {series} #1 score {r['score1']:.1f} (sd {r['score1_sd']:.1f})  #2 score {r['score2']:.1f} (sd {r['score2_sd']:.1f})  top-2 total {r['top2']:.1f} (sd {r['top2_sd']:.1f})")
        if remaining == 0:
            pts = sum((POINTS[np.array(x) - 1] for x in done), np.zeros(4))
            out.append("series complete; settlement by points: " + "  ".join(f"{h} {int(p)}" for h, p in zip(HUMANS, pts)))
        return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--races", nargs="*", default=[])
    a = ap.parse_args(); pr = Pricer()
    for r in a.races:
        pr.add_race([int(x) for x in r.split()])
    print(pr.fair())
    if not sys.stdin.isatty():
        return
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if line.startswith("race"):
            try:
                pr.add_race([int(x) for x in line.split()[1:]]); print(pr.fair())
            except AssertionError:
                print("need 4 distinct positions 1..12 for humans A B C D")
        elif line == "fair":
            print(pr.fair())
        elif line == "undo":
            pr.undo(); print(pr.fair())
        elif line in ("q", "quit"):
            break


if __name__ == "__main__":
    main()
