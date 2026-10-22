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
from .wind import SiteState, PHYS, project_track, wind_at, PARAMS
import numpy as np

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
        self.obs: list[dict[str, Any]] = []                 # observations of the current storm
        self.official: list[tuple[int, str]] = []           # (age, outlook) of the current storm
        self.wire: list[tuple[int, str]] = []
        self.ensemble = None                                # AnalogEnsemble, attached by the strategy
        self.posterior: dict[str, float] = {}
        self.fair_sd: dict[str, float] = {}                 # ensemble spread of the fair value per symbol

    # ---- feed handling ----
    def on_message(self, m: dict[str, Any]) -> None:
        t = m["type"]
        if t == "storm_formed":
            self.round = m["round"]
            for s in self.states.values():
                s.new_storm()
            self.storm_active, self.storm_reported, self.last_obs, self.current_loss_est = True, False, None, 0.0
            self.obs, self.official, self.wire, self.posterior, self.fair_sd = [], [], [], {}, {}
        elif t == "storm":
            self.last_obs = m
            self.obs.append(m)
            for s in self.states.values():
                s.observe(m)
        elif t == "advisory":
            (self.official if m.get("source") == "official" else self.wire).append((m["age"], m["outlook"]))
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

    def on_snapshot(self, snap: dict[str, Any]) -> None:
        """Rebuild the state from a snapshot after a late connection: damage reports of all rounds, then the track."""
        if self.obs or self.loss_final:
            return                                          # we have been listening; nothing to rebuild
        reports = snap.get("damage") or []
        for rep in reports:
            if rep.get("stage") == "final":
                self.on_message({"type": "storm_formed", "round": rep["round"]})
                self.on_message(rep)
        obs = snap.get("obs")
        if obs and snap.get("phase") in ("storm", "aftermath"):
            rnd = snap.get("round") or self.round + 1
            self.on_message({"type": "storm_formed", "round": rnd})
            for age, x, y, r in snap.get("track") or []:
                self.on_message({"type": "storm", "round": rnd, "age": age, "x": x, "y": y, "radius": r,
                                 "intensity": obs.get("intensity", 1.0), "vx": obs.get("vx", 0), "vy": obs.get("vy", 0)})
            self.on_message({"type": "storm", "round": rnd, **obs})
            if snap.get("phase") == "aftermath":
                self.on_message({"type": "storm_dissipated", "round": rnd})
            adv = snap.get("advisory")
            if adv:
                self.on_message(adv)

    # ---- uncertainty ----
    DAMAGE_RMSE = {"PORT": 6.3, "ISLE": 3.2, "AQUA": 3.6, "GRID": 3.6, "FERRY": 3.8}   # holdout rmse of the damage model, points

    def model_sd(self, fair: dict[str, float]) -> dict[str, float]:
        """Valuation uncertainty from the damage model itself while the current storm is not yet final-reported:
        quadrature sum over companies of the fair-value change from a one-rmse damage perturbation."""
        if self.storm_reported or self.round == 0:
            return {k: 0.0 for k in fair}
        prior = P["prior"]; n_future = self.storms_left_after_current()
        cur, cur_out = self.current_storm_damage(None)
        cum = {k: self.states[k].cum_damage() + cur[k] + n_future * prior["dmg"][k] for k in PHYS}
        outage = {k: self.states[k].weighted_outage() + cur_out[k] + n_future * prior["outage"][k] for k in PHYS}
        loss = self.loss_final + (self.current_loss_est or storm_loss(cur)) + n_future * prior["loss"]
        base = values(cum, outage, loss, self.case)
        acc = {k: 0.0 for k in base}
        for c, rmse in self.DAMAGE_RMSE.items():
            cum2 = dict(cum); cum2[c] += rmse
            d = dict(cur); d[c] += rmse
            loss2 = loss + (storm_loss(d) - storm_loss(cur)) if not self.current_loss_est else loss
            v2 = values(cum2, outage, loss2, self.case)
            for k in base:
                acc[k] += (v2[k] - base[k]) ** 2
        return {k: v ** 0.5 for k, v in acc.items()}

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

    def fair_analog(self) -> dict[str, float]:
        """Fair value as the ensemble average of the valuation over analog futures of the current storm."""
        prior = P["prior"]
        n_future = self.storms_left_after_current()
        base_cum = {k: self.states[k].cum_damage() for k in PHYS}
        if not (self.storm_active and self.obs and self.ensemble is not None):
            f = self.fair(project=False)
            self.fair_sd = self.model_sd(f)
            return f
        w = self.ensemble.weights(self.obs, self.official, self.wire)
        self.posterior = self.ensemble.pattern_posterior(w)
        E, O, sel = self.ensemble.future_exposure(self.obs, w)
        wsel = w[sel]
        vals = []
        for i in range(len(sel)):
            cum, out = {}, {}
            for k, st in self.states.items():
                extra = list(E[k][i])
                cum[k] = base_cum[k] + st.storm_damage(extra)
                out[k] = st.weighted_outage() + float((O[k][i] * np.array([x["weight"] for x in st.sites])).sum())
            storm_dmg = {k: cum[k] - base_cum[k] for k in PHYS}
            loss = self.loss_final + (self.current_loss_est or storm_loss(storm_dmg))
            for k in PHYS:
                cum[k] += n_future * prior["dmg"][k]; out[k] += n_future * prior["outage"][k]
            loss += n_future * prior["loss"]
            vals.append(values(cum, out, loss, self.case))
        keys = list(vals[0])
        arr = np.array([[v[k] for k in keys] for v in vals])
        mean = (wsel[:, None] * arr).sum(0)
        sd = np.sqrt((wsel[:, None] * (arr - mean) ** 2).sum(0))
        fair = dict(zip(keys, mean.tolist()))
        msd = self.model_sd(fair)
        self.fair_sd = {k: float(np.hypot(v, msd[k])) for k, v in zip(keys, sd.tolist())}
        return fair

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
