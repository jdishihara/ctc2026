"""Analog track ensemble: forecast the rest of the current storm from historical storms that look like it so far.

Weight of analog i = track kernel exp(-d_i^2 / 2 sigma^2) * prod over official advisories P(outlook | truth_i at that age)
                     * prod over wire rumors P(outlook | truth_i)^tau
Future track of analog i = its own observations after the current age, shifted by the current position offset.
The ensemble gives a distribution of end-of-storm damage and outage per company, and a pattern posterior.
"""
from __future__ import annotations
import json, math
import numpy as np
from pathlib import Path
from typing import Any
from .wind import PARAMS, PHYS

OUTLOOKS = ["direct", "chain", "recurve", "stall", "eyewall", "erratic"]
OIDX = {o: i for i, o in enumerate(OUTLOOKS)}
GRID_AGES = np.arange(0, 482, 2)      # 241 observations per storm
LIB = Path(__file__).parent / "analog_library.npz"


def build_library(root: Path, seasons: list[dict[str, Any]], out: Path = LIB) -> None:
    tracks, pattern, flip, offs, wires = [], [], [], [], []
    for s in seasons:
        feed = [json.loads(l) for l in open(root / "history" / s["dir"] / "feed.jsonl")]
        for st in s["storms"]:
            obs = {m["age"]: (m["x"], m["y"], m["radius"], m["intensity"]) for m in feed if m["round"] == st["round"] and m["type"] == "storm"}
            tr = np.full((len(GRID_AGES), 4), np.nan)
            for i, a in enumerate(GRID_AGES):
                if int(a) in obs:
                    tr[i] = obs[int(a)]
            # fill gaps by interpolation
            for c in range(4):
                col = tr[:, c]; ok = ~np.isnan(col)
                tr[:, c] = np.interp(GRID_AGES, GRID_AGES[ok], col[ok])
            tracks.append(tr); pattern.append(OIDX[st["pattern"]]); flip.append(-1 if st["turned_erratic_at"] is None else st["turned_erratic_at"])
            offs.append([(m["age"], OIDX[m["outlook"]]) for m in feed if m["round"] == st["round"] and m["type"] == "advisory" and m["source"] == "official"])
            wires.append([(m["age"], OIDX[m["outlook"]]) for m in feed if m["round"] == st["round"] and m["type"] == "advisory" and m["source"] == "wire"])
    tracks = np.array(tracks); pattern = np.array(pattern); flip = np.array(flip)
    # confusion matrices P(outlook | truth), truth = erratic once flipped
    C_off = np.ones((6, 6)); C_wire = np.ones((6, 6))     # Laplace smoothing
    for i in range(len(tracks)):
        for lst, C in ((offs[i], C_off), (wires[i], C_wire)):
            for age, o in lst:
                truth = OIDX["erratic"] if (flip[i] >= 0 and age >= flip[i]) else pattern[i]
                C[truth, o] += 1
    C_off /= C_off.sum(1, keepdims=True); C_wire /= C_wire.sum(1, keepdims=True)
    np.savez_compressed(out, tracks=tracks, pattern=pattern, flip=flip, C_off=C_off, C_wire=C_wire)


class AnalogEnsemble:
    def __init__(self, case: dict[str, Any], sigma: float = 25.0, tau_wire: float = 0.5, k: int = 50,
                 shift: bool = True, lib: Path = LIB, cone_w: float = 0.0, isl_w: float = 0.0, cone_s0: float = 10.0, cone_nu: float = 0.0):
        d = np.load(lib)
        self.tracks, self.pattern, self.flip = d["tracks"], d["pattern"], d["flip"]
        self.C_off, self.C_wire = d["C_off"], d["C_wire"]
        self.sigma, self.tau, self.k, self.shift = sigma, tau_wire, k, shift
        # official advisory likelihoods (measured on holdout storms 2026-10-23: the cone's position error is 60-70% of the
        # ensemble's at 1-2 minutes ahead and its stated spread is calibrated; the island probabilities are calibrated too)
        self.cone_w, self.isl_w, self.cone_s0 = cone_w, isl_w, cone_s0     # tempering powers; cone_s0 = spread floor (map units)
        self.cone_nu = cone_nu          # >0: Student-t cone likelihood with this many degrees of freedom (a wrong cone does not zero out the right analogs)
        self.case = case
        self.sites = {sym: np.array([[s["x"], s["y"], s["weight"]] for s in case["companies"][sym]["sites"]]) for sym in PHYS}
        isl: dict[str, list] = {i: [] for i in case["islands"]}
        for sym in PHYS:
            for st in case["companies"][sym]["sites"]:
                isl[st["island"]].append((st["x"], st["y"]))
        self.island_sites = {i: np.array(v) for i, v in isl.items() if v}
        # hit_after[isl][i, j]: analog i produces hurricane conditions on island isl at some age >= GRID_AGES[j]
        # (unshifted library tracks; precomputed once so the island likelihood costs nothing per update)
        self.hit_after: dict[str, np.ndarray] = {}
        if isl_w > 0:
            for i, pts in self.island_sites.items():
                dist = np.hypot(self.tracks[:, :, 0][:, :, None] - pts[:, 0], self.tracks[:, :, 1][:, :, None] - pts[:, 1])
                wind = self.tracks[:, :, 3][:, :, None] * np.exp(-PARAMS["k"] * dist / self.tracks[:, :, 2][:, :, None])
                hit = (wind > PARAMS["thr_close"]).any(2)                       # (N, T)
                self.hit_after[i] = np.flip(np.logical_or.accumulate(np.flip(hit, 1), axis=1), 1)

    def weights(self, obs: list[dict[str, Any]], official: list[tuple[int, str]], wire: list[tuple[int, str]],
                adv: dict[str, Any] | None = None) -> np.ndarray:
        """Posterior weight of each analog given the observations and advisories so far; `adv` is the latest official
        advisory message (its cone and island probabilities are extra likelihood terms when cone_w / isl_w > 0)."""
        n = len(obs)
        idx = min(n, len(GRID_AGES)) - 1
        cur = np.array([[o["x"], o["y"]] for o in obs[: idx + 1]])
        lib = self.tracks[:, : idx + 1, :2]
        d2 = ((lib - cur[None]) ** 2).sum(-1).mean(1)
        logw = -d2 / (2 * self.sigma ** 2)
        for age, o in official:
            truth = np.where((self.flip >= 0) & (age >= self.flip), OIDX["erratic"], self.pattern)
            logw += np.log(self.C_off[truth, OIDX[o]])
        for age, o in wire:
            truth = np.where((self.flip >= 0) & (age >= self.flip), OIDX["erratic"], self.pattern)
            logw += self.tau * np.log(self.C_wire[truth, OIDX[o]])
        if adv and (self.cone_w > 0 or self.isl_w > 0):
            age_now = obs[-1]["age"]
            off = (np.array([obs[-1]["x"], obs[-1]["y"]]) - self.tracks[:, idx, :2]) if self.shift else 0.0
            if self.cone_w > 0:
                for cp in adv.get("cone") or []:
                    j = int(cp["age"] // 2)
                    if cp["age"] <= age_now or j >= len(GRID_AGES):
                        continue
                    pos = self.tracks[:, j, :2] + off
                    dc = ((pos - np.array([cp["x"], cp["y"]])) ** 2).sum(1)
                    var = cp["spread"] ** 2 + self.cone_s0 ** 2
                    if self.cone_nu > 0:        # bivariate t: log density ~ -(nu + 2) / 2 * log(1 + d^2 / (nu var))
                        logw -= self.cone_w * (self.cone_nu + 2) / 2 * np.log1p(dc / (self.cone_nu * var))
                    else:
                        logw -= self.cone_w * dc / (2 * var)
            conds = adv.get("hurricane_conditions") if self.isl_w > 0 else None
            if conds and idx + 1 < len(GRID_AGES):
                for isl, p in conds.items():
                    if isl not in self.hit_after:
                        continue
                    hit = self.hit_after[isl][:, idx + 1]
                    p = min(0.98, max(0.02, float(p)))
                    logw += self.isl_w * np.where(hit, math.log(p), math.log(1 - p))
        w = np.exp(logw - logw.max())
        if self.k and self.k < len(w):
            cut = np.sort(w)[-self.k]
            w = np.where(w >= cut, w, 0.0)
        return w / w.sum()

    def pattern_posterior(self, w: np.ndarray) -> dict[str, float]:
        return {o: float(w[self.pattern == i].sum()) for o, i in OIDX.items()}

    def future_exposure(self, obs: list[dict[str, Any]], w: np.ndarray) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
        """Per company: arrays (n_analog, n_sites) of future exposure E and future closure seconds, for analogs with w > 0."""
        idx = min(len(obs), len(GRID_AGES)) - 1
        sel = np.nonzero(w > 0)[0]
        fut = self.tracks[sel, idx + 1:, :]                      # (K, F, 4)
        if self.shift:
            off = np.array([obs[-1]["x"], obs[-1]["y"]]) - self.tracks[sel, idx, :2]
            fut = fut.copy(); fut[:, :, :2] += off[:, None, :]
        E, O = {}, {}
        for sym, sites in self.sites.items():
            dist = np.hypot(fut[:, :, 0][:, :, None] - sites[:, 0], fut[:, :, 1][:, :, None] - sites[:, 1])   # (K, F, S)
            wind = fut[:, :, 3][:, :, None] * np.exp(-PARAMS["k"] * dist / fut[:, :, 2][:, :, None])
            E[sym] = (np.clip(wind - PARAMS["thr_dmg"], 0, None) ** PARAMS["p"]).sum(1) * 2.0
            O[sym] = (wind > PARAMS["thr_close"]).sum(1) * 2.0
        return E, O, sel
