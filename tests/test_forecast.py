import json
import math
from pathlib import Path

import numpy as np
import pytest

from ctc.analog import AnalogEnsemble, GRID_AGES
from ctc.valuation import SeasonModel, expected_values, storm_loss, P
from ctc.wind import PARAMS, PHYS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ensemble(tmp_path):
    tracks = np.zeros((3, len(GRID_AGES), 4))
    for i, speed in enumerate((1, 5, -1)):
        tracks[i, :, 0] = speed * GRID_AGES
    tracks[:, :, 1] = 500
    tracks[:, :, 2] = 100
    tracks[:, :, 3] = 1
    path = tmp_path / "library.npz"
    np.savez(path, tracks=tracks, pattern=np.array([0, 1, 2]),
             flip=np.full(3, -1), C_off=np.full((6, 6), 1 / 6),
             C_wire=np.full((6, 6), 1 / 6))
    case = {"islands": {"test": {}}, "companies": {
        sym: {"sites": [{"x": 480, "y": 500, "weight": 1, "island": "test"}]}
        for sym in PHYS}}
    return AnalogEnsemble(case, lib=path, sigma=2, k=0, shift=False)


def observation(age, x=None):
    return {"age": age, "x": age if x is None else x, "y": 500,
            "radius": 100, "intensity": 1}


def scalar_weights(obs, sigma=2):
    # Independent closed-form trajectories: x = speed * age, y = 500.
    errors = [sum((speed * o["age"] - o["x"]) ** 2 for o in obs) / len(obs)
              for speed in (1, 5, -1)]
    raw = np.array([math.exp(-(e - min(errors)) / (2 * sigma**2)) for e in errors])
    return raw / raw.sum()


def test_observation_gaps_match_actual_ages(ensemble):
    obs = [observation(0), observation(4)]
    np.testing.assert_allclose(ensemble.weights(obs, [], []), scalar_weights(obs), rtol=1e-12)


def test_repeated_appended_corrected_and_reset_evidence(ensemble):
    obs = [observation(0), observation(2)]
    for _ in range(2):
        np.testing.assert_allclose(ensemble.weights(obs, [], []), scalar_weights(obs))
    obs.append(observation(4))
    np.testing.assert_allclose(ensemble.weights(obs, [], []), scalar_weights(obs))
    obs[0]["x"] = 12  # A corrected prefix must invalidate previously accumulated evidence.
    np.testing.assert_allclose(ensemble.weights(obs, [], []), scalar_weights(obs))
    obs[:] = [observation(0, 3)]
    np.testing.assert_allclose(ensemble.weights(obs, [], []), scalar_weights(obs))
    replacement = [observation(0), observation(2, 10), observation(4, 20)]
    np.testing.assert_allclose(ensemble.weights(replacement, [], []), scalar_weights(replacement))


def test_top_k_preserves_equal_weight_ties(ensemble):
    ensemble.k = 1
    np.testing.assert_allclose(ensemble.weights([observation(0)], [], []), [1 / 3] * 3)


def test_fractional_age_is_interpolated(ensemble):
    obs = [observation(0), observation(3)]
    np.testing.assert_allclose(ensemble.weights(obs, [], []), scalar_weights(obs))


def test_late_join_projects_only_remaining_storm(ensemble):
    e, o, selected = ensemble.future_exposure([observation(478)], np.array([1., 0., 0.]))
    assert selected.tolist() == [0]
    for sym in PHYS:
        # Only the observation at age 480 remains, exactly at the company site.
        assert e[sym][0, 0] == pytest.approx(2 * max(1 - PARAMS["thr_dmg"], 0)**PARAMS["p"])
        assert o[sym][0, 0] == 2


def test_terminal_observation_has_no_future_exposure(ensemble):
    e, o, _ = ensemble.future_exposure([observation(480)], np.array([1., 0., 0.]))
    assert all(a.sum() == 0 for a in e.values())
    assert all(a.sum() == 0 for a in o.values())


@pytest.mark.parametrize("varying", [True, False])
def test_wind_conditioning_uses_current_strength_without_changing_library(tmp_path, varying):
    tracks = np.zeros((3, len(GRID_AGES), 4))
    tracks[:, :, 0] = 100
    strength = np.array([0.5, 1, 1.5] if varying else [1, 1, 1])
    tracks[:, :, 2] = 100 * strength[:, None]
    tracks[:, :, 3] = strength[:, None]
    path = tmp_path / "wind-library.npz"
    np.savez(path, tracks=tracks, pattern=np.arange(3), flip=np.full(3, -1),
             C_off=np.full((6, 6), 1 / 6), C_wire=np.full((6, 6), 1 / 6))
    case = {"islands": {"test": {}}, "companies": {
        sym: {"sites": [{"x": 0, "y": 0, "weight": 1, "island": "test"}]}
        for sym in PHYS}}
    model = AnalogEnsemble(case, lib=path, k=0, shift=False, wind_condition=1)
    obs = [{"age": 478, "x": 100, "y": 0, "radius": 200, "intensity": 2}]
    exposure, outage, _ = model.future_exposure(obs, np.full(3, 1 / 3))
    # Perfect persistence has slope 1; a zero-variance library supplies no evidence
    # for a response and must leave the historical values finite and unchanged.
    radius, intensity = (200, 2) if varying else (100, 1)
    wind = intensity * math.exp(-PARAMS["k"] * 100 / radius)
    expected = 2 * max(wind - PARAMS["thr_dmg"], 0)**PARAMS["p"]
    for sym in PHYS:
        np.testing.assert_allclose(exposure[sym], np.full((3, 1), expected))
        np.testing.assert_allclose(outage[sym], np.full((3, 1), 2 * (wind > PARAMS["thr_close"])))
    np.testing.assert_array_equal(model.tracks, tracks)


def test_vectorized_damage_preserves_scalar_valuation():
    case = json.loads((ROOT / "data/case.json").read_text())
    model = SeasonModel(case)
    model.on_message({"type": "storm_formed", "round": 2})
    model.on_message({"type": "storm", "round": 2, "age": 0, "x": 500,
                      "y": 600, "radius": 120, "intensity": 1, "vx": 0, "vy": -1})
    model.loss_final = 230
    for j, state in enumerate(model.states.values()):
        state.cum = [2 + j + i for i in range(len(state.sites))]
        state.outage = [10 + 2 * i for i in range(len(state.sites))]
    e = {s: np.array([[0.5 + i for i in range(len(st.sites))],
                      [3 + 2 * i for i in range(len(st.sites))]])
         for s, st in model.states.items()}
    o = {s: e[s] * 2 for s in PHYS}

    class TwoFutures:
        def weights(self, *args): return np.array([0.25, 0.75])
        def pattern_posterior(self, weights): return {"direct": 0.25, "chain": 0.75}
        def future_exposure(self, *args): return e, o, np.array([0, 1])

    model.ensemble = TwoFutures()
    cum, outage, loss = [], [], []
    for i in range(2):
        dmg = {s: st.storm_damage(list(e[s][i])) for s, st in model.states.items()}
        cum.append([model.states[s].cum_damage() + dmg[s] for s in PHYS])
        outage.append([model.states[s].weighted_outage() + sum(
            x["weight"] * sec for x, sec in zip(model.states[s].sites, o[s][i])) for s in PHYS])
        loss.append(230 + storm_loss(dmg))
    ev, fsd = expected_values(np.array(cum), np.array(outage), np.array(loss), 1, case, with_sd=True)
    expected = {s: float(v[0] * 0.25 + v[1] * 0.75) for s, v in ev.items()}
    fair = model.fair_analog()
    msd = model.model_sd(expected)
    for sym in fair:
        assert fair[sym] == pytest.approx(expected[sym], rel=1e-12, abs=1e-11)
        variance = sum(w * (v - expected[sym])**2 for w, v in zip((0.25, 0.75), ev[sym]))
        assert model.fair_sd[sym] == pytest.approx(math.sqrt(variance + msd[sym]**2), rel=1e-11, abs=1e-11)
        assert model.future_sd[sym] == pytest.approx(0.25 * fsd[sym][0] + 0.75 * fsd[sym][1], rel=1e-11, abs=1e-11)


def test_exact_rebuilders_activate_only_after_all_final_reports():
    case = json.loads((ROOT / "data/case.json").read_text())
    candidate = SeasonModel(case, final_exact=True)
    baseline = SeasonModel(case)
    for model in (candidate, baseline):
        for i, state in enumerate(model.states.values()):
            state.cum = [20.0 + i] * len(state.sites)
            state.outage = [10.0] * len(state.sites)
        model.round = 3
        model.storm_reported = True
        model.reported_rounds = {1, 3}  # The missing round is not silently treated as known.
    assert candidate.fair() == baseline.fair()
    assert candidate.resid_sd("RECON") == baseline.resid_sd("RECON")
    candidate.reported_rounds.add(2)
    actual = candidate.fair()
    q = P["RECON_exact"]["params"]
    exposure = sum(q[2 + i] * (20 + i) + q[7 + i] * 10 for i in range(5))
    expected = q[0] + q[1] * (1 - math.exp(-exposure))
    assert actual["RECON"] == pytest.approx(expected)
    assert actual["RECON"] != pytest.approx(baseline.fair()["RECON"])
    assert candidate.resid_sd("RECON") == P["resid_sd_exact"]["RECON"]
    assert actual["REBLD"] == pytest.approx(sum(
        n * actual[s] for s, n in case["etfs"]["REBLD"]["basket"].items()))


def test_exact_final_setting_does_not_leak_to_other_models():
    case = json.loads((ROOT / "data/case.json").read_text())
    baseline = SeasonModel(case)
    expected = baseline.fair()
    candidate = SeasonModel(case, final_exact=True)
    candidate.round = 3
    candidate.storm_reported = True
    candidate.reported_rounds = {1, 2, 3}
    candidate.fair()
    assert baseline.fair() == expected
