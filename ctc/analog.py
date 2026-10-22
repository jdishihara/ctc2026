"""Analog track ensemble: forecast the rest of the current storm from historical storms that look like it so far.

Weight of analog i = track kernel exp(-d_i^2 / 2 sigma^2) * prod over official advisories P(outlook | truth_i at that age)
                     * prod over wire rumors P(outlook | truth_i)^tau
Future track of analog i = its own observations after the current age, shifted by the current position offset.
The ensemble gives a distribution of end-of-storm damage and outage per company, and a pattern posterior.
"""
from __future__ import annotations
import json
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
                 shift: bool = True, lib: Path = LIB):
        d = np.load(lib)
        self.tracks, self.pattern, self.flip = d["tracks"], d["pattern"], d["flip"]
        self.C_off, self.C_wire = d["C_off"], d["C_wire"]
        self.sigma, self.tau, self.k, self.shift = sigma, tau_wire, k, shift
        self.case = case
        self.sites = {sym: np.array([[s["x"], s["y"], s["weight"]] for s in case["companies"][sym]["sites"]]) for sym in PHYS}

    def weights(self, obs: list[dict[str, Any]], official: list[tuple[int, str]], wire: list[tuple[int, str]]) -> np.ndarray:
        """Posterior weight of each analog given the observations and advisories so far."""
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
