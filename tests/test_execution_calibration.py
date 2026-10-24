import copy

import pytest

from scripts.experiment_execution_costs import calibrated_profiles


BASE = {'A': {'spread': .002, 'bands': [.001, .005, .01],
              'bid': [10, 20, 30], 'ask': [12, 24, 36]}}


def quote(**changes):
    return {'type': 'quote', 'symbol': 'A', 'bid': 99., 'ask': 101.,
            'bid_size': 5, 'ask_size': 7, **changes}


def test_widening_spread_keeps_deeper_fills_more_expensive():
    original = copy.deepcopy(BASE)
    profiles, calibration = calibrated_profiles([quote()], BASE)
    row = profiles['observed_spread']['A']
    assert row['spread'] == pytest.approx(.02)
    assert row['spread'] / 2 < row['bands'][1] < row['bands'][2]
    assert row['bands'][1] - BASE['A']['bands'][1] == pytest.approx(.009)
    assert profiles['observed_touch']['A']['bid'] == [5]
    assert profiles['observed_touch']['A']['ask'] == [7]
    assert calibration['A']['usable_quotes'] == 1
    assert BASE == original


def test_invalid_or_one_sided_quotes_do_not_set_cost_assumptions():
    profiles, calibration = calibrated_profiles(
        [quote(), quote(bid=None), quote(ask=float('nan')), quote(bid_size=-1)], BASE)
    assert calibration['A']['usable_quotes'] == 1
    assert profiles['observed_spread']['A']['spread'] == pytest.approx(.02)


def test_missing_symbol_quote_coverage_is_rejected():
    with pytest.raises(ValueError, match='A'):
        calibrated_profiles([], BASE)
