import copy
import json
from pathlib import Path

import pytest

from ctc.valuation import SeasonModel

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def captured():
    return json.loads((ROOT / 'tests/fixtures/live_midstorm_snapshot.json').read_text())


@pytest.fixture
def model():
    return SeasonModel(json.loads((ROOT / 'data/case.json').read_text()))


@pytest.mark.parametrize('boot_count', [3, 18])
def test_snapshot_recovers_missing_prefix_and_preserves_actual_observations(model, captured, boot_count):
    observed = captured['observed'][:boot_count]
    for message in observed:
        model.on_message(message)
    model.on_snapshot(captured['snapshot'])
    assert [o['age'] for o in model.obs] == list(range(0, 121, 2))
    by_age = {o['age']: o for o in model.obs}
    for message in observed:
        if message['type'] == 'storm':
            assert by_age[message['age']] == message
    assert model.reported_rounds == {1, 2}
    assert not model.outage_history_complete  # Interpolation is not exact history.


def test_snapshot_fills_internal_gap_without_replacing_received_weather(model):
    def weather(age, x):
        return dict(type='storm', round=1, age=age, x=x, y=500,
                    radius=100, intensity=1, vx=5, vy=0)
    first, actual, last = weather(0, 0), weather(2, 12), weather(6, 30)
    for message in [first, actual, last]:
        model.on_message(message)
    model.on_snapshot({'round': 1, 'phase': 'storm', 'damage': [], 'obs': last,
                       'track': [[0, 0, 500, 100], [6, 30, 500, 100]]})
    assert [o['age'] for o in model.obs] == [0, 2, 4, 6]
    assert model.obs[1] == actual
    assert model.obs[2]['x'] == 20
    assert not model.outage_history_complete


def test_recovery_retains_observations_newer_than_snapshot(model, captured):
    for message in captured['observed']:
        model.on_message(message)
    newer = {**model.last_obs, 'age': 122, 'x': 777, 'seq': 648}
    model.on_message(newer)
    model.on_snapshot(captured['snapshot'])
    assert model.obs[0]['age'] == 0
    assert model.last_obs == newer
    assert [o['age'] for o in model.obs] == list(range(0, 123, 2))


def test_snapshot_does_not_relabel_previous_storm_observations(model, captured):
    old = {**captured['observed'][0], 'round': 2, 'x': -9999}
    model.on_message(old)
    model.on_snapshot(captured['snapshot'])
    assert model.round == 3
    assert model.obs[0]['age'] == 0
    assert all(o['round'] == 3 and o['x'] != -9999 for o in model.obs)


def test_older_round_snapshot_cannot_rewind_current_storm(model, captured):
    for message in captured['observed']:
        model.on_message(message)
    original = copy.deepcopy(model.obs)
    old = {**captured['snapshot'], 'round': 2,
           'damage': [r for r in captured['snapshot']['damage'] if r['round'] == 1]}
    model.on_snapshot(old)
    assert model.round == 3
    assert model.obs == original


def test_redundant_snapshot_preserves_complete_live_weather(model):
    for age in [0, 2, 4, 6]:
        model.on_message(dict(type='storm', round=1, age=age, x=age, y=500,
                              radius=100, intensity=1, vx=1, vy=0))
    original = copy.deepcopy(model.obs)
    model.on_snapshot({'round': 1, 'phase': 'storm', 'damage': [],
                       'obs': model.last_obs, 'track': [[0, 0, 500, 100], [6, 6, 500, 100]]})
    assert model.obs == original
    assert model.outage_history_complete
