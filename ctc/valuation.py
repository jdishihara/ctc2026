"""Fair-value model for the 12 symbols, from fitted settlement rules (scripts/fit_valuation.py).

Island business:  value = base - a*cum_damage - b*cum_damage^2 - o*weighted_outage_seconds
Season loss ($M): sum_k l_k * damage_k, summed over storms
Rebuilder:        value = base + A*(1 - exp(-D/s)) + o*outage, D = relevant cumulative damage
Insurer:          HAVEN = 75 -> 21 linearly over [L0, L1]; REIN = 90 - slope*(L - L1)+
ETF:              basket value
"""
from __future__ import annotations
import json, math
from pathlib import Path
from typing import Any
from .wind import SiteState, PHYS, project_track

P = json.loads((Path(__file__).parent / "valuation_params.json").read_text())
SYMS = ["PORT", "ISLE", "AQUA", "GRID", "FERRY", "RECON", "MAT", "GEN", "HAVEN", "REIN", "ARCH", "REBLD"]


def island_value(sym: str, cum: float, outage: float) -> float:
    b = P[sym]["beta"]
    return b[0] + b[1] * cum + b[2] * cum ** 2 + b[3] * outage


def storm_loss(dmg: dict[str, float]) -> float:
    return sum(l * dmg[k] for l, k in zip(P["loss"]["beta"], PHYS))


def rebuild_value(sym: str, cum: dict[str, float], outage: dict[str, float]) -> float:
    base, A, s, o = P[sym]["params"]
    if sym == "RECON":
        D, O = cum["PORT"] + cum["GRID"] + cum["FERRY"], 0.0
    elif sym == "MAT":
        D, O = sum(cum.values()), 0.0
    else:
        D, O = cum["GRID"], outage["GRID"]
    return base + A * (1 - math.exp(-D / s)) + o * O


def insurer_value(sym: str, L: float) -> float:
    q = P[sym]
    if sym == "HAVEN":
        L0, L1 = q["params"]
        return q["top"] - (q["top"] - q["floor"]) * min(1.0, max(0.0, (L - L0) / (L1 - L0)))
    L1, slope = q["params"]
    return q["top"] - slope * max(0.0, L - L1)


def values(cum: dict[str, float], outage: dict[str, float], loss: float, case: dict[str, Any]) -> dict[str, float]:
    v = {k: island_value(k, cum[k], outage[k]) for k in PHYS}
    for k in ("RECON", "MAT", "GEN"):
        v[k] = rebuild_value(k, cum, outage)
    for k in ("HAVEN", "REIN"):
        v[k] = insurer_value(k, loss)
    for etf, spec in case["etfs"].items():
        v[etf] = sum(n * v[s] for s, n in spec["basket"].items())
    return v


class SeasonModel:
    """Tracks the season state from the feed and produces fair values under simple assumptions about the future."""

    def __init__(self, case: dict[str, Any]):
        self.case = case
        self.states = {k: SiteState(case, k) for k in PHYS}
        self.loss_final = 0.0           # insured losses from final reports of finished storms
        self.round = 0
        self.storm_active = False
        self.last_obs: dict[str, Any] | None = None
        self.storm_reported = False     # final report received for the current storm
        self.current_loss_est = 0.0     # preliminary report of the current storm, if any
        self.timing = case["timing"]

    # ---- feed handling ----
    def on_message(self, m: dict[str, Any]) -> None:
        t = m["type"]
        if t == "storm_formed":
            self.round = m["round"]
            for s in self.states.values():
                s.new_storm()
            self.storm_active, self.storm_reported, self.last_obs, self.current_loss_est = True, False, None, 0.0
        elif t == "storm":
            self.last_obs = m
            for s in self.states.values():
                s.observe(m)
        elif t == "storm_dissipated":
            self.storm_active = False
        elif t == "damage_report":
            for k in PHYS:
                self.states[k].set_from_report(m["damage_pct"][k])
            if m["stage"] == "final":
                self.loss_final += m["industry_loss_musd"]
                self.storm_reported, self.current_loss_est = True, 0.0
            else:
                self.current_loss_est = m["industry_loss_musd"]

    # ---- uncertainty ----
    def resid_sd(self, sym: str) -> float:
        """Std of the valuation residual for `sym` once all damage is known (fit residual); 0 if the symbol is exact."""
        sd = P.get("resid_sd", {}).get(sym, 0.0)
        if sym in ("ARCH", "REBLD"):
            sd = sum(n * P.get("resid_sd", {}).get(s, 0.0) for s, n in self.case["etfs"][sym]["basket"].items())
        return sd

    # ---- state ----
    def storms_left_after_current(self) -> int:
        return max(0, 3 - max(self.round, 1))

    def current_storm_damage(self, horizon_age: float | None = None) -> tuple[dict[str, float], dict[str, float]]:
        """(damage %, extra weighted outage seconds) this storm adds per company: observed so far, plus a naive
        constant-velocity projection to `horizon_age`."""
        from .wind import wind_at, PARAMS
        extra = {k: None for k in PHYS}
        outage = {k: 0.0 for k in PHYS}
        if horizon_age is not None and self.last_obs is not None and self.storm_active:
            future = project_track(self.last_obs, horizon_age, self.case["storm"]["dissipate"])
            for k, st in self.states.items():
                ex = [0.0] * len(st.sites)
                for obs in future:
                    for j, site in enumerate(st.sites):
                        w = wind_at(obs, site["x"], site["y"])
                        ex[j] += max(w - PARAMS["thr_dmg"], 0.0) ** PARAMS["p"] * 2.0
                        if w > PARAMS["thr_close"]:
                            outage[k] += site["weight"] * 2.0
                extra[k] = ex
        return {k: self.states[k].storm_damage(extra[k]) for k in PHYS}, outage

    def fair(self, project: bool = True) -> dict[str, float]:
        """Fair values: finished storms exact, current storm nowcast (optionally projected), future storms at the prior."""
        prior = P["prior"]
        age_end = self.timing["storm"] if project else None
        cur, cur_out = self.current_storm_damage(age_end)
        cum = {k: self.states[k].cum_damage() + cur[k] for k in PHYS}
        outage = {k: self.states[k].weighted_outage() + cur_out[k] for k in PHYS}
        loss = self.loss_final
        if not self.storm_reported and self.round >= 1:
            loss += storm_loss(cur) if not self.current_loss_est else self.current_loss_est
        n_future = self.storms_left_after_current() if self.round >= 1 else 3
        for k in PHYS:
            cum[k] += n_future * prior["dmg"][k]
            outage[k] += n_future * prior["outage"][k]
        loss += n_future * prior["loss"]
        return values(cum, outage, loss, self.case)
