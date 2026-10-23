"""Wind field and damage model, fitted on the research seasons (scripts/fit_damage.py).

wind(site) = intensity * exp(-k * dist / radius)
A site closes while wind > thr_close.
Damage per storm at a site: remaining * (1 - exp(-c_company * E)), E = sum over 2 s observations of wind.
Company damage % = sum of site weight * site damage.
"""
from __future__ import annotations
import json, math
from pathlib import Path
from typing import Any

PARAMS = json.loads((Path(__file__).parent / "damage_params.json").read_text())
PHYS = ["PORT", "ISLE", "AQUA", "GRID", "FERRY"]


def wind_at(obs: dict[str, Any], x: float, y: float) -> float:
    d = math.hypot(obs["x"] - x, obs["y"] - y)
    return obs["intensity"] * math.exp(-PARAMS["k"] * d / obs["radius"])


class SiteState:
    """Per-site cumulative damage and outage for one company, updated observation by observation."""

    def __init__(self, case: dict[str, Any], sym: str):
        self.sym = sym
        self.sites = case["companies"][sym]["sites"]
        self.cum = [0.0] * len(self.sites)       # cumulative damage % per site (0..100), before this storm
        self.exposure = [0.0] * len(self.sites)  # E of the current storm
        self.outage = [0.0] * len(self.sites)    # closure seconds, whole season
        self.c = PARAMS["c"][sym]

    def new_storm(self) -> None:
        for j in range(len(self.sites)):
            self.cum[j] += self.storm_damage_site(j)
            self.exposure[j] = 0.0

    def observe(self, obs: dict[str, Any], dt: float = 2.0) -> None:
        """Integrate one observation; `dt` is the real seconds it stands for (2 s on the live feed, more for a
        snapshot track replay)."""
        for j, s in enumerate(self.sites):
            w = wind_at(obs, s["x"], s["y"])
            self.exposure[j] += max(w - PARAMS["thr_dmg"], 0.0) ** PARAMS["p"] * dt
            if w > PARAMS["thr_close"]:
                self.outage[j] += dt

    def storm_damage_site(self, j: int, extra_exposure: float = 0.0) -> float:
        return (100.0 - self.cum[j]) * (1.0 - math.exp(-self.c * (self.exposure[j] + extra_exposure)))

    def storm_damage(self, extra: list[float] | None = None) -> float:
        """Company damage % added by the current storm so far (plus optional extra exposure per site)."""
        return sum(s["weight"] * self.storm_damage_site(j, extra[j] if extra else 0.0) for j, s in enumerate(self.sites))

    def cum_damage(self) -> float:
        return sum(s["weight"] * self.cum[j] for j, s in enumerate(self.sites))

    def weighted_outage(self) -> float:
        return sum(s["weight"] * self.outage[j] for j, s in enumerate(self.sites))

    def add_outage_estimate(self, seconds: float) -> None:
        """No wind history for this storm (model rebuilt from a snapshot): book the same closure seconds at every site,
        so weighted_outage() rises by `seconds`."""
        for j in range(len(self.sites)):
            self.outage[j] += seconds

    def set_from_report(self, company_damage_pct: float) -> None:
        """Match reported company damage, redistributing excess from saturated sites.

        Preserve predicted site ratios wherever capacity allows. If the track
        omitted damaged sites, distribute the remainder across their capacity.
        """
        remaining = [max(0.0, 100.0 - c) for c in self.cum]
        weights = [s["weight"] for s in self.sites]
        raw = [self.storm_damage_site(j) for j in range(len(self.sites))]
        target = [0.0] * len(self.sites)
        capacity = sum(w * r for w, r in zip(weights, remaining))
        needed = min(capacity, max(0.0, company_damage_pct))
        active = {j for j in range(len(self.sites)) if raw[j] > 1e-12 and weights[j] > 0}
        while active and needed > 1e-12:
            scale = needed / sum(weights[j] * raw[j] for j in active)
            saturated = {j for j in active if scale * raw[j] >= remaining[j]}
            if not saturated:
                for j in active:
                    target[j] = scale * raw[j]
                needed = 0.0
                break
            for j in saturated:
                target[j] = remaining[j]
                needed -= weights[j] * target[j]
            active -= saturated
        if needed > 1e-12:
            available = sum(w * (r - d) for w, r, d in zip(weights, remaining, target))
            if available > 0:
                for j in range(len(target)):
                    target[j] += (remaining[j] - target[j]) * min(1.0, needed / available)
        for j in range(len(self.sites)):
            frac = target[j] / max(1e-12, remaining[j])
            self.exposure[j] = -math.log(max(1e-12, 1 - frac)) / self.c


def project_track(obs: dict[str, Any], age_end: float, dissipate: float = 60.0, dt: float = 2.0) -> list[dict[str, Any]]:
    """Naive forecast: constant velocity from the latest observation until age_end, intensity fading in the last `dissipate` s."""
    out = []
    age, x, y = obs["age"], obs["x"], obs["y"]
    vx, vy, r, inten = obs["vx"], obs["vy"], obs["radius"], obs["intensity"]
    while age + dt <= age_end:
        age += dt
        x += vx * dt
        y += vy * dt
        remaining = age_end - age
        fade = min(1.0, remaining / dissipate) if dissipate > 0 else 1.0
        out.append({"age": age, "x": x, "y": y, "radius": r, "intensity": inten * fade})
    return out
