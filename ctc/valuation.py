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

# Sample of historical storms (scripts/build_storm_sample.py, seasons 1-450) for the future-storm prior: the fair value
# with n storms still to come is the average of the valuation over n-storm combinations, not the valuation at the
# mean storm (insurers and rebuilders are convex / concave in the loss).
_SP = Path(__file__).parent / "storm_sample.npz"
_SAMPLE_M = 400
FUTURE: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
if _SP.exists():
    _d = np.load(_SP); _rng = np.random.default_rng(0)
    _n = len(_d["loss"])
    _i1 = _rng.choice(_n, _SAMPLE_M, replace=False)
    FUTURE[1] = (_d["dmg"][_i1], _d["outage"][_i1], _d["loss"][_i1])
    _i2a, _i2b = _rng.integers(0, _n, _SAMPLE_M), _rng.integers(0, _n, _SAMPLE_M)
    FUTURE[2] = (_d["dmg"][_i2a] + _d["dmg"][_i2b], _d["outage"][_i2a] + _d["outage"][_i2b], _d["loss"][_i2a] + _d["loss"][_i2b])
    _i3 = [_rng.integers(0, _n, _SAMPLE_M) for _ in range(3)]
    FUTURE[3] = (sum(_d["dmg"][i] for i in _i3), sum(_d["outage"][i] for i in _i3), sum(_d["loss"][i] for i in _i3))


def values_vec(cum: np.ndarray, outage: np.ndarray, loss: np.ndarray, case: dict[str, Any]) -> dict[str, np.ndarray]:
    """Vectorised `values`: cum, outage are (N, 5) in PHYS order, loss is (N,). Returns symbol -> (N,) array."""
    v = {}
    for j, k in enumerate(PHYS):
        b = P[k]["beta"]
        v[k] = b[0] + b[1] * cum[:, j] + b[2] * cum[:, j] ** 2 + b[3] * outage[:, j]
    idx = {k: j for j, k in enumerate(PHYS)}
    for k in ("RECON", "MAT", "GEN"):
        if _rp(k).get("kind") == "rebuild_w":
            q = np.array(_rp(k)["params"])
            e = cum @ q[2:7] + outage @ q[7:12]
            v[k] = q[0] + q[1] * (1 - np.exp(-np.clip(e, 0, None)))
            continue
        base, A, sc, o = P[k]["params"]
        if k == "RECON":
            D, O = cum[:, idx["PORT"]] + cum[:, idx["GRID"]] + cum[:, idx["FERRY"]], 0.0
        elif k == "MAT":
            D, O = cum.sum(1), 0.0
        else:
            D, O = cum[:, idx["GRID"]], outage[:, idx["GRID"]]
        v[k] = base + A * (1 - np.exp(-D / sc)) + o * O
    q = P["HAVEN"]; L0, L1 = q["params"]
    v["HAVEN"] = q["top"] - (q["top"] - q["floor"]) * np.clip((loss - L0) / (L1 - L0), 0.0, 1.0)
    q = P["REIN"]; L1, slope = q["params"]
    v["REIN"] = q["top"] - slope * np.clip(loss - L1, 0.0, None)
    for etf, spec in case["etfs"].items():
        v[etf] = sum(n * v[s_] for s_, n in spec["basket"].items())
    return v


def expected_values(cum: np.ndarray, outage: np.ndarray, loss: np.ndarray, n_future: int, case: dict[str, Any],
                    mode: str = "sample", with_sd: bool = False):
    """Expected valuation with `n_future` storms still to come, for each of the N states given (cum (N,5), outage (N,5),
    loss (N,)). mode "sample": average over historical n-storm combinations; "point": the mean storm added n times."""
    prior = P["prior"]
    if n_future <= 0 or mode != "sample" or n_future not in FUTURE:
        if n_future <= 0:
            ev = values_vec(cum, outage, loss, case)
        else:
            pd = np.array([prior["dmg"][k] for k in PHYS]); po = np.array([prior["outage"][k] for k in PHYS])
            ev = values_vec(cum + n_future * pd, outage + n_future * po, loss + n_future * prior["loss"], case)
        return (ev, {k: np.zeros_like(a) for k, a in ev.items()}) if with_sd else ev
    sd, so, sl = FUTURE[n_future]
    N, M = len(loss), len(sl)
    c = (cum[:, None, :] + sd[None, :, :]).reshape(N * M, -1)
    o = (outage[:, None, :] + so[None, :, :]).reshape(N * M, -1)
    l = (loss[:, None] + sl[None, :]).reshape(N * M)
    v = values_vec(c, o, l, case)
    ev = {k: a.reshape(N, M).mean(1) for k, a in v.items()}
    if with_sd:
        return ev, {k: a.reshape(N, M).std(1) for k, a in v.items()}
    return ev


def island_value(sym: str, cum: float, outage: float) -> float:
    b = P[sym]["beta"]
    return b[0] + b[1] * cum + b[2] * cum ** 2 + b[3] * outage


def storm_loss(dmg: dict[str, float]) -> float:
    return sum(l * dmg[k] for l, k in zip(P["loss"]["beta"], PHYS))


EXACT_REBUILD = False     # use the exact weighted-saturation rules (scripts/fit_rebuilders.py); rejected on verify PnL, see EXPERIMENTS.md


def _rp(sym: str) -> dict:
    return P[sym + "_exact"] if EXACT_REBUILD and sym + "_exact" in P else P[sym]


def rebuild_value(sym: str, cum: dict[str, float], outage: dict[str, float]) -> float:
    if _rp(sym).get("kind") == "rebuild_w":       # exact rule: weighted damages and outages inside one saturation
        q = _rp(sym)["params"]
        e = sum(q[2 + i] * cum[k] + q[7 + i] * outage[k] for i, k in enumerate(PHYS))
        return q[0] + q[1] * (1 - math.exp(-max(0.0, e)))
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


# closure seconds per damage point (least squares through the origin on ctc/storm_sample.npz, seasons 1-450; corr 0.7-0.8):
# used only when a model is rebuilt from a snapshot and the wind history of earlier storms is gone
OUTAGE_PER_DMG = {"PORT": 1.70, "ISLE": 2.27, "AQUA": 1.98, "GRID": 1.67, "FERRY": 2.14}


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
        self.adv: dict[str, Any] | None = None             # latest official advisory of the current storm (cone, island probabilities)
        self.adv_prev: dict[str, Any] | None = None
        self.ensemble = None                                # AnalogEnsemble, attached by the strategy
        self.posterior: dict[str, float] = {}
        self.fair_sd: dict[str, float] = {}                 # ensemble spread of the fair value per symbol
        self.reported_rounds: set[int] = set()              # rounds whose final report we applied
        self.prelim_seen = False                            # preliminary report of the current storm applied
        self.prior_mode = "sample"                          # future storms: "sample" of historical storms or "point" mean
        self.future_sd_mult = 0.0                           # add this multiple of the future-storm valuation sd to fair_sd
        self.future_sd: dict[str, float] = {}

    # ---- feed handling ----
    def on_message(self, m: dict[str, Any]) -> None:
        t = m["type"]
        if m.get("round") and t in ("storm", "track", "advisory", "impact") and m["round"] != self.round:
            # joined mid-storm without storm_formed: open the storm now (snapshot fills in earlier rounds)
            self.on_message({"type": "storm_formed", "round": m["round"]})
        if t == "storm_formed":
            self.round = m["round"]
            for s in self.states.values():
                s.new_storm()
            self.storm_active, self.storm_reported, self.last_obs, self.current_loss_est = True, False, None, 0.0
            self.prelim_seen = False
            self.obs, self.official, self.wire, self.posterior, self.fair_sd = [], [], [], {}, {}
            self.adv = None; self.adv_prev = None
        elif t == "storm":
            dt = m.get("_dt", 2.0)
            self.last_obs = m
            self.obs.append(m)
            for s in self.states.values():
                s.observe(m, dt)
        elif t == "advisory":
            (self.official if m.get("source") == "official" else self.wire).append((m["age"], m["outlook"]))
            if m.get("source") == "official":
                self.adv = dict(m); self.adv["_all"] = ((self.adv_prev or {}).get("_all") or []) + [m]; self.adv_prev = self.adv
        elif t == "storm_dissipated":
            self.storm_active = False
        elif t == "damage_report":
            if m["stage"] == "final":
                for k in PHYS:
                    self.states[k].set_from_report(m["damage_pct"][k])
                self.loss_final += m["industry_loss_musd"]
                self.storm_reported, self.current_loss_est, self.prelim_seen = True, 0.0, False
                self.reported_rounds.add(m["round"])
            else:
                # the preliminary report is noisier than our own nowcast (rmse 9 vs 6 points for PORT): combine them
                # with the coefficients fitted in scripts/fit_prelim.py instead of taking the prelim as truth
                q = P.get("prelim")
                now = {k: self.states[k].storm_damage() for k in PHYS}
                if q:
                    comb = {k: max(0.0, q["dmg"][k][0] + q["dmg"][k][1] * m["damage_pct"][k] + q["dmg"][k][2] * now[k]) for k in PHYS}
                    a, b, c = q["loss"]
                    self.current_loss_est = max(1e-6, a + b * m["industry_loss_musd"] + c * storm_loss(now))
                else:
                    comb = dict(m["damage_pct"]); self.current_loss_est = m["industry_loss_musd"]
                for k in PHYS:
                    self.states[k].set_from_report(comb[k])
                self.prelim_seen = True

    def on_snapshot(self, snap: dict[str, Any]) -> None:
        """After a late connection, rebuild from the snapshot: final reports of earlier rounds we missed, then the
        current storm's track (sparse, so each point carries its age gap) and preliminary report if any."""
        reports = [{**r, "type": "damage_report"} for r in (snap.get("damage") or [])]   # snapshot entries carry no type
        finals = [r for r in reports if r.get("stage") == "final"]
        phase = snap.get("phase")
        need_rounds = not ({r["round"] for r in finals} <= self.reported_rounds)
        need_storm = phase in ("storm", "aftermath") and not self.obs
        if not (need_rounds or need_storm):
            return
        cur_obs, cur_official, cur_wire, cur_adv = list(self.obs), list(self.official), list(self.wire), self.adv
        self.states = {k: SiteState(self.case, k) for k in PHYS}
        self.loss_final, self.reported_rounds, self.round = 0.0, set(), 0
        for rep in sorted(finals, key=lambda r: r["round"]):
            self.on_message({"type": "storm_formed", "round": rep["round"]})
            self.on_message(rep)
            # the report gives damage, not closure seconds; without them PORT/GRID/FERRY/GEN fair values sit 2-5 points
            # too high for the rest of the season (measured 2026-10-23). Book the historical ratio of outage to damage.
            for k in PHYS:
                self.states[k].add_outage_estimate(OUTAGE_PER_DMG[k] * rep["damage_pct"][k])
        obs = snap.get("obs")
        rnd = snap.get("round") or self.round + 1
        if obs and phase in ("storm", "aftermath") and rnd not in self.reported_rounds:
            self.on_message({"type": "storm_formed", "round": rnd})
            if cur_obs:
                for o in cur_obs:
                    self.on_message({**o, "type": "storm", "round": rnd})
            else:
                pts = snap.get("track") or []
                # the snapshot track is subsampled (about 40 points): interpolate it to the 2 s observation grid and use the
                # storm's own intensity (not 1.0) so the exposure integral matches a model that saw every observation
                T, D = self.timing["storm"], self.case["storm"]["dissipate"]
                def fade(a):
                    return 1.0 if a < T - D else max(0.0, (T - a) / D)
                a_obs = obs.get("age", 0)
                i0 = min(1.5, max(0.5, obs.get("intensity", 1.0) / max(0.1, fade(a_obs))))
                ages = np.arange(0, a_obs + 1e-9, 2.0)
                prev_age = -2.0
                if len(pts) >= 2:
                    arr = np.array(pts, dtype=float)
                    xs, ys, rs = (np.interp(ages, arr[:, 0], arr[:, c]) for c in (1, 2, 3))
                    for a, x, y, r in zip(ages, xs, ys, rs):
                        if a >= a_obs:
                            break
                        self.on_message({"type": "storm", "round": rnd, "age": float(a), "x": float(x), "y": float(y), "radius": float(r),
                                         "intensity": i0 * fade(a), "vx": obs.get("vx", 0), "vy": obs.get("vy", 0), "_dt": 2.0})
                        prev_age = a
                self.on_message({"type": "storm", "round": rnd, **{k: v for k, v in obs.items() if k != "type"}, "_dt": max(2.0, a_obs - prev_age)})
            self.official, self.wire, self.adv = cur_official, cur_wire, cur_adv
            adv = snap.get("advisory")
            if adv and not cur_official:
                # the snapshot's advisory record carries no "type" field; the live bot crashed on it at each reconnect
                self.on_message({"type": "advisory", **adv})
            for rep in reports:
                if rep.get("stage") == "preliminary" and rep.get("round") == rnd:
                    self.on_message(rep)
            if phase == "aftermath":
                self.on_message({"type": "storm_dissipated", "round": rnd})

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
        q = P.get("prelim") if self.prelim_seen else None
        rmses = q["dmg_sd"] if q else self.DAMAGE_RMSE
        for c, rmse in rmses.items():
            cum2 = dict(cum); cum2[c] += rmse
            d = dict(cur); d[c] += rmse
            loss2 = loss + (storm_loss(d) - storm_loss(cur)) if not self.current_loss_est else loss
            v2 = values(cum2, outage, loss2, self.case)
            for k in base:
                acc[k] += (v2[k] - base[k]) ** 2
        if self.current_loss_est:                            # the loss estimate (prelim-based) has its own error
            v2 = values(cum, outage, loss + (q["loss_sd"] if q else 60.0), self.case)
            for k in base:
                acc[k] += (v2[k] - base[k]) ** 2
        return {k: v ** 0.5 for k, v in acc.items()}

    def resid_sd(self, sym: str) -> float:
        """Std of the valuation residual for `sym` once all damage is known (fit residual); 0 if the symbol is exact."""
        tab = {**P.get("resid_sd", {}), **(P.get("resid_sd_exact", {}) if EXACT_REBUILD else {})}
        sd = tab.get(sym, 0.0)
        if sym in ("ARCH", "REBLD"):
            sd = sum(n * tab.get(s, 0.0) for s, n in self.case["etfs"][sym]["basket"].items())
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
            msd = self.model_sd(f)
            self.fair_sd = {k: math.hypot(msd[k], self.future_sd_mult * self.future_sd.get(k, 0.0)) for k in f}
            return f
        w = self.ensemble.weights(self.obs, self.official, self.wire, self.adv)
        self.posterior = self.ensemble.pattern_posterior(w)
        E, O, sel = self.ensemble.future_exposure(self.obs, w)
        wsel = w[sel]
        K = len(sel)
        cum_a, out_a = np.empty((K, len(PHYS))), np.empty((K, len(PHYS)))
        loss_a = np.full(K, self.loss_final, dtype=float)
        for j, k in enumerate(PHYS):
            st = self.states[k]
            site_weights = np.array([site["weight"] for site in st.sites])
            damage = (100.0 - np.asarray(st.cum)) * (1.0 - np.exp(-st.c * (np.asarray(st.exposure) + E[k])))
            cum_a[:, j] = base_cum[k] + (damage * site_weights).sum(1)
            out_a[:, j] = st.weighted_outage() + (O[k] * site_weights).sum(1)
            if not self.current_loss_est:
                loss_a += P["loss"]["beta"][j] * (cum_a[:, j] - base_cum[k])
        if self.current_loss_est:
            loss_a += self.current_loss_est
        ev, fsd = expected_values(cum_a, out_a, loss_a, n_future, self.case, self.prior_mode, with_sd=True)
        keys = list(ev)
        arr = np.array([ev[k] for k in keys]).T                 # (K, n_symbols)
        self.future_sd = {k: float((wsel * fsd[k]).sum()) for k in keys}
        mean = (wsel[:, None] * arr).sum(0)
        sd = np.sqrt((wsel[:, None] * (arr - mean) ** 2).sum(0))
        fair = dict(zip(keys, mean.tolist()))
        msd = self.model_sd(fair)
        self.fair_sd = {k: math.hypot(v, msd[k]) for k, v in zip(keys, sd.tolist())}   # future-storm sd only applies outside the storm
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
        ev, fsd = expected_values(np.array([[cum[k] for k in PHYS]]), np.array([[outage[k] for k in PHYS]]), np.array([loss]),
                                  n_future, self.case, self.prior_mode, with_sd=True)
        self.future_sd = {k: float(v[0]) for k, v in fsd.items()}
        return {k: float(v[0]) for k, v in ev.items()}
