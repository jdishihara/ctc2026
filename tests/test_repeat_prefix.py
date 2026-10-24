"""Synthetic prefix-recognition contracts; no downloaded outcomes are read."""
import copy

import numpy as np
import pytest

from ctc.analog import AnalogEnsemble, GRID_AGES
from ctc.wind import PHYS


@pytest.fixture
def models(tmp_path):
    tracks = np.zeros((3, len(GRID_AGES), 4))
    for i, speed in enumerate((0.1, 0.2, -0.1)):
        tracks[i, :, 0] = speed * GRID_AGES
    tracks[:, :, 1] = 500
    tracks[:, :, 2] = 100
    tracks[:, :, 3] = 1
    case = {'islands': {'test': {}}, 'companies': {
        sym: {'sites': [{'x': 40, 'y': 500, 'weight': 1, 'island': 'test'}]}
        for sym in PHYS}}

    def create(enabled, values=None):
        path = tmp_path / f'library-{len(list(tmp_path.iterdir()))}.npz'
        np.savez(path, tracks=tracks if values is None else values,
                 pattern=np.array([0, 1, 2]), flip=np.full(3, -1),
                 C_off=np.full((6, 6), 1 / 6), C_wire=np.full((6, 6), 1 / 6))
        kwargs = {} if enabled is None else {'repeat_prefix': enabled}
        return AnalogEnsemble(case, lib=path, sigma=15, k=0, **kwargs)

    return create, tracks


def observations(tracks, row=0, count=21):
    return [dict(age=int(GRID_AGES[i]), **dict(zip(
        ('x', 'y', 'radius', 'intensity'), map(float, tracks[row, i]))))
        for i in range(count)]


def compare_fallback(candidate, baseline, obs):
    actual = candidate.weights(obs, [], [])
    expected = baseline.weights(obs, [], [])
    np.testing.assert_array_equal(actual, expected)
    return actual


def test_disabled_is_default_and_does_not_concentrate(models):
    create, tracks = models
    obs = observations(tracks)
    default = create(None).weights(obs, [], [])
    disabled = create(False).weights(obs, [], [])
    np.testing.assert_array_equal(default, disabled)
    assert np.count_nonzero(default) == 3


@pytest.mark.parametrize('value', ['false', 1, None, [], 0.5])
def test_option_requires_an_explicit_boolean(models, value):
    create, _ = models
    if value is None:
        base = create(False)
        with pytest.raises(ValueError, match='repeat_prefix'):
            AnalogEnsemble(base.case, repeat_prefix=None)
    else:
        with pytest.raises(ValueError, match='repeat_prefix'):
            create(value)


def test_activation_requires_21_complete_points_and_age_40(models):
    create, tracks = models
    candidate, baseline = create(True), create(False)
    compare_fallback(candidate, baseline, observations(tracks, count=20))
    np.testing.assert_array_equal(candidate.weights(observations(tracks), [], []), [1, 0, 0])
    assert np.count_nonzero(baseline.weights(observations(tracks), [], [])) == 3


@pytest.mark.parametrize('channel', ['x', 'y', 'radius', 'intensity'])
def test_every_weather_channel_and_earliest_observation_must_match(models, channel):
    create, tracks = models
    candidate, baseline = create(True), create(False)
    obs = observations(tracks)
    candidate.weights(obs, [], [])
    obs[0][channel] = np.nextafter(obs[0][channel], np.inf)
    compare_fallback(candidate, baseline, obs)


def test_duplicate_library_prefix_stays_ambiguous_until_observed_divergence(models):
    create, tracks = models
    altered = tracks.copy()
    altered[1, :21] = altered[0, :21]
    candidate, baseline = create(True, altered), create(False, altered)
    compare_fallback(candidate, baseline, observations(altered))
    np.testing.assert_array_equal(candidate.weights(observations(altered, count=22), [], []), [1, 0, 0])


@pytest.mark.parametrize('fault', ['missing_first', 'gap', 'duplicate', 'reverse', 'off_grid', 'too_long'])
def test_incomplete_or_malformed_age_grid_falls_back(models, fault):
    create, tracks = models
    obs = observations(tracks, count=23)
    if fault == 'missing_first':
        obs.pop(0)
    elif fault == 'gap':
        obs.pop(7)
    elif fault == 'duplicate':
        obs.insert(8, copy.deepcopy(obs[7]))
    elif fault == 'reverse':
        obs[7], obs[8] = obs[8], obs[7]
    elif fault == 'off_grid':
        obs[7]['age'] += 0.5
    else:
        obs = observations(tracks, count=241)
        obs.append({**obs[-1], 'age': 482})
    compare_fallback(create(True), create(False), obs)


@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), -float('inf'), '100', True])
@pytest.mark.parametrize('channel', ['radius', 'intensity'])
def test_invalid_strength_values_do_not_activate(models, value, channel):
    create, tracks = models
    obs = observations(tracks)
    obs[5][channel] = value
    compare_fallback(create(True), create(False), obs)


def test_missing_strength_field_retains_baseline(models):
    create, tracks = models
    obs = observations(tracks)
    del obs[8]['radius']
    compare_fallback(create(True), create(False), obs)


def test_divergence_then_correction_truncation_and_new_storm(models):
    create, tracks = models
    candidate, baseline = create(True), create(False)
    obs = observations(tracks)
    np.testing.assert_array_equal(candidate.weights(obs, [], []), [1, 0, 0])
    obs.append({**observations(tracks, count=22)[-1], 'x': 250})
    compare_fallback(candidate, baseline, obs)
    obs[-1] = observations(tracks, count=22)[-1]
    np.testing.assert_array_equal(candidate.weights(obs, [], []), [1, 0, 0])
    compare_fallback(candidate, baseline, obs[:10])
    np.testing.assert_array_equal(candidate.weights(observations(tracks, 2), [], []), [0, 0, 1])


def test_strength_correction_invalidates_owned_prefix_cache(models):
    create, tracks = models
    candidate, baseline = create(True), create(False)
    obs = observations(tracks)
    candidate.weights(obs, [], [])
    obs[0]['radius'] += 1
    compare_fallback(candidate, baseline, obs)
    obs[0]['radius'] -= 1
    np.testing.assert_array_equal(candidate.weights(obs, [], []), [1, 0, 0])


def test_matching_selection_cannot_read_unobserved_library_suffix(models):
    create, tracks = models
    altered = tracks.copy()
    altered[:, 21:, :] = np.random.default_rng(7).normal(size=altered[:, 21:, :].shape)
    obs = observations(tracks)
    np.testing.assert_array_equal(create(True, altered).weights(obs, [], []), [1, 0, 0])
    np.testing.assert_array_equal(create(True).weights(obs, [], []), [1, 0, 0])


def test_advisory_does_not_break_exact_recognition(models):
    create, tracks = models
    candidate = create(True)
    candidate.C_off[:, :] = 0.01
    candidate.C_off[2, 2] = 0.9
    np.testing.assert_array_equal(candidate.weights(observations(tracks), [(40, 'recurve')], []), [1, 0, 0])


def test_ordinary_cache_remains_current_after_long_matching_period(models):
    create, tracks = models
    candidate, baseline = create(True), create(False)
    for n in [21, 22, 60, 140]:
        obs = observations(tracks, count=n)
        candidate.weights(obs, [], [])
        baseline.weights(obs, [], [])
    obs.append({**observations(tracks, count=141)[-1], 'y': 499})
    compare_fallback(candidate, baseline, obs)


def test_prediction_uses_matched_historical_continuation_without_mutating_it(models):
    create, tracks = models
    candidate = create(True)
    obs = observations(tracks)
    before = candidate.tracks.copy()
    weights = candidate.weights(obs, [], [])
    future, selected = candidate.future_tracks(obs, weights)
    assert selected.tolist() == [0]
    np.testing.assert_array_equal(future, tracks[0:1, 21:, :])
    np.testing.assert_array_equal(candidate.tracks, before)
