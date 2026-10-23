"""Analog track ensemble: forecast the rest of the current storm from historical storms that look like it so far.

Weight of analog i = track kernel exp(-d_i^2 / 2 sigma^2) * prod over official advisories P(outlook | truth_i at that age)
                     * prod over wire rumors P(outlook | truth_i)^tau
Future track of analog i = its own observations after the current age, shifted by the current position offset.
The ensemble gives a distribution of end-of-storm damage and outage per company, and a pattern posterior.
"""
from __future__ import annotations
import json, math
from functools import lru_cache
import numpy as np
from pathlib import Path
from typing import Any
from .wind import PARAMS, PHYS

OUTLOOKS = ["direct", "chain", "recurve", "stall", "eyewall", "erratic"]
OIDX = {o: i for i, o in enumerate(OUTLOOKS)}
GRID_AGES = np.arange(0, 482, 2)      # 241 observations per storm
LIB = Path(__file__).parent / "analog_library.npz"


@lru_cache(maxsize=4)
def _strength_response(path: str, modified_ns: int) -> np.ndarray:
    """Training-only linear response of future radius/intensity to current values.

    Cache identity includes the library's modification time. Rows are current
    ages, columns future ages; zero-variance current ages get zero response.
    """
    with np.load(path) as data:
        strength = data["tracks"][:, :, 2:4]
    responses = []
    for channel in range(2):
        centered = strength[:, :, channel] - strength[:, :, channel].mean(0)
        covariance = centered.T @ centered
        variance = np.diag(covariance)[:, None]
        responses.append(np.divide(covariance, variance, out=np.zeros_like(covariance), where=variance > 1e-9))
    return np.stack(responses)


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
                 shift: bool = True, lib: Path = LIB, cone_w: float = 0.0, isl_w: float = 0.0, cone_s0: float = 10.0, cone_nu: float = 0.0, vel_w: float = 0.0, vel_sd: float = 0.3, cone_all: bool = False,
                 wind_condition: float = 0.0, cone_center: float = 0.0):
        if not 0 <= wind_condition <= 1:
            raise ValueError("wind_condition must be between zero and one")
        self.wind_condition = wind_condition
        if not 0 <= cone_center <= 1:
            raise ValueError('cone_center must be between zero and one')
        self.cone_center = cone_center
        self.strength_response = (_strength_response(str(lib.resolve()), lib.stat().st_mtime_ns)
                                  if wind_condition else None)
        with np.load(lib) as d:
            self.tracks, self.pattern, self.flip = d["tracks"], d["pattern"], d["flip"]
            self.C_off, self.C_wire = d["C_off"], d["C_wire"]
        self.sigma, self.tau, self.k, self.shift = sigma, tau_wire, k, shift
        # official advisory likelihoods (measured on holdout storms 2026-10-23: the cone's position error is 60-70% of the
        # ensemble's at 1-2 minutes ahead and its stated spread is calibrated; the island probabilities are calibrated too)
        self.cone_w, self.isl_w, self.cone_s0 = cone_w, isl_w, cone_s0     # tempering powers; cone_s0 = spread floor (map units)
        self.cone_nu = cone_nu          # >0: Student-t cone likelihood with this many degrees of freedom (a wrong cone does not zero out the right analogs)
        self.vel_w, self.vel_sd = vel_w, vel_sd    # >0: kernel on the current velocity vs the analog's velocity at the same age (map units / s)
        self.cone_all = cone_all        # use the cones of all official advisories so far, not only the latest
        self.vel = np.gradient(self.tracks[:, :, :2], 2.0, axis=1)       # (N, T, 2) analog velocities from the 2 s grid
        self.case = case
        # Verify the prefix on every call: reconnects, corrections, and new storms
        # can replace observations. Only new observations need an N-analog pass.
        self._observed = np.empty((0, 3))  # age, x, y; owned copy, never aliases feed objects
        self._track_error = np.zeros(len(self.tracks))
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

    def _positions_at(self, ages: np.ndarray) -> np.ndarray:
        """Library positions at actual observation ages, interpolated on the 2s grid."""
        index = np.clip(ages / 2.0, 0, len(GRID_AGES) - 1)
        lo = index.astype(int)
        fraction = index - lo
        positions = self.tracks[:, lo, :2]
        if np.any(fraction):
            hi = np.minimum(lo + 1, len(GRID_AGES) - 1)
            positions = positions + fraction[None, :, None] * (self.tracks[:, hi, :2] - positions)
        return positions

    def weights(self, obs: list[dict[str, Any]], official: list[tuple[int, str]], wire: list[tuple[int, str]],
                adv: dict[str, Any] | None = None) -> np.ndarray:
        """Posterior weight of each analog given the observations and advisories so far; `adv` is the latest official
        advisory message (its cone and island probabilities are extra likelihood terms when cone_w / isl_w > 0)."""
        if not obs:
            raise ValueError("An analog forecast needs at least one storm observation")
        cur = np.array([[o["age"], o["x"], o["y"]] for o in obs], dtype=float)
        n = len(cur)
        idx = int(np.clip(cur[-1, 0] // 2, 0, len(GRID_AGES) - 1))
        previous = len(self._observed)
        if previous > n or not np.array_equal(cur[:previous], self._observed):
            previous = 0
            self._track_error.fill(0)
        if previous < n:
            added = cur[previous:]
            delta = self._positions_at(added[:, 0]) - added[None, :, 1:]
            self._track_error += np.square(delta).sum(axis=(1, 2))
        self._observed = cur
        d2 = self._track_error / n
        logw = -d2 / (2 * self.sigma ** 2)
        if self.vel_w > 0 and "vx" in obs[-1]:
            dv = ((self.vel[:, idx, :] - np.array([obs[-1]["vx"], obs[-1]["vy"]])) ** 2).sum(1)
            logw -= self.vel_w * dv / (2 * self.vel_sd ** 2)
        for age, o in official:
            truth = np.where((self.flip >= 0) & (age >= self.flip), OIDX["erratic"], self.pattern)
            logw += np.log(self.C_off[truth, OIDX[o]])
        for age, o in wire:
            truth = np.where((self.flip >= 0) & (age >= self.flip), OIDX["erratic"], self.pattern)
            logw += self.tau * np.log(self.C_wire[truth, OIDX[o]])
        if adv and (self.cone_w > 0 or self.isl_w > 0):
            age_now = obs[-1]["age"]
            off = (cur[-1, 1:] - self._positions_at(cur[-1:, 0])[:, 0, :]) if self.shift else 0.0
            if self.cone_w > 0:
                cones = [cp for a in (adv.get("_all") or [adv]) for cp in (a.get("cone") or [])] if self.cone_all else (adv.get("cone") or [])
                for cp in cones:
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
            cut = np.partition(w, -self.k)[-self.k]
            w = np.where(w >= cut, w, 0.0)
        return w / w.sum()

    def pattern_posterior(self, w: np.ndarray) -> dict[str, float]:
        return {o: float(w[self.pattern == i].sum()) for o, i in OIDX.items()}

    def future_tracks(self, obs: list[dict[str, Any]], w: np.ndarray,
                      adv: dict[str, Any] | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Projected paths; optional cone centering translates all selected paths equally."""
        idx = int(np.clip(obs[-1]["age"] // 2, 0, len(GRID_AGES) - 1))
        sel = np.nonzero(w > 0)[0]
        fut = self.tracks[sel, idx + 1:, :]                      # (K, F, 4)
        if self.shift:
            positions = self._positions_at(np.array([obs[-1]["age"]]))[sel, 0, :]
            off = np.array([obs[-1]["x"], obs[-1]["y"]]) - positions
            fut = fut.copy(); fut[:, :, :2] += off[:, None, :]
        if self.strength_response is not None:
            # Remove the mismatch between this storm's observed strength and
            # each analog's strength, using only training-library responses.
            next_idx = min(idx + 1, len(GRID_AGES) - 1)
            fraction = float(np.clip(obs[-1]["age"] / 2 - idx, 0, 1))
            current = ((1 - fraction) * self.tracks[sel, idx, 2:4]
                       + fraction * self.tracks[sel, next_idx, 2:4])
            response = ((1 - fraction) * self.strength_response[:, idx, idx + 1:]
                        + fraction * self.strength_response[:, next_idx, idx + 1:]).T
            observed = np.array([obs[-1]["radius"], obs[-1]["intensity"]])
            fut[:, :, 2:4] += self.wind_condition * (observed - current)[:, None, :] * response[None, :, :]
            fut[:, :, 2] = np.maximum(fut[:, :, 2], 1e-6)
            fut[:, :, 3] = np.maximum(fut[:, :, 3], 0)
        age = obs[-1]['age']
        cones = [cp for cp in (adv or {}).get('cone', []) if age < cp['age'] <= GRID_AGES[-1]]
        if self.cone_center and cones and fut.shape[1]:
            fut = fut.copy()
            grid = GRID_AGES[idx + 1:]
            mean = np.einsum('i,ijk->jk', w[sel], fut[:, :, :2])
            knots, corrections = [age], [np.zeros(2)]
            for cp in sorted(cones, key=lambda cp: cp['age']):
                projected = np.array([np.interp(cp['age'], grid, mean[:, axis]) for axis in range(2)])
                knots.append(cp['age'])
                corrections.append(np.array([cp['x'], cp['y']]) - projected)
            # Beyond the last official prediction, return smoothly to the analogs.
            knots.append(knots[-1] + 60)
            corrections.append(np.zeros(2))
            correction = np.stack([np.interp(grid, knots, np.array(corrections)[:, axis])
                                   for axis in range(2)], axis=1)
            fut[:, :, :2] += self.cone_center * correction[None]
        return fut, sel

    def future_exposure(self, obs: list[dict[str, Any]], w: np.ndarray,
                        adv: dict[str, Any] | None = None) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], np.ndarray]:
        """Per company: future exposure and closure seconds for analogs with positive weight."""
        fut, sel = self.future_tracks(obs, w, adv)
        E, O = {}, {}
        for sym, sites in self.sites.items():
            dist = np.hypot(fut[:, :, 0][:, :, None] - sites[:, 0], fut[:, :, 1][:, :, None] - sites[:, 1])   # (K, F, S)
            wind = fut[:, :, 3][:, :, None] * np.exp(-PARAMS["k"] * dist / fut[:, :, 2][:, :, None])
            E[sym] = (np.clip(wind - PARAMS["thr_dmg"], 0, None) ** PARAMS["p"]).sum(1) * 2.0
            O[sym] = (wind > PARAMS["thr_close"]).sum(1) * 2.0
        return E, O, sel
