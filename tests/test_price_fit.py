import numpy as np
import pytest

from scripts.fit_price_signal import fit, samples


def test_training_sample_uses_past_features_and_same_round_future():
    times = np.arange(0, 780, 2)
    prices = (100 + .1 * times)[:, None]
    x, y, elapsed = samples(prices, times)
    assert elapsed[0] == 120
    assert elapsed[-1] == 650
    assert x[0, 0, -1] == pytest.approx(12 / 112)
    assert y[0, 0] == pytest.approx(12 / 112)
    changed = prices.copy()
    changed[120] += 100  # Future price at t=240 is a label, never an input at t=120.
    x2, y2, _ = samples(changed, times)
    np.testing.assert_array_equal(x[0], x2[0])
    assert y2[0, 0] != y[0, 0]


def test_short_round_has_no_cross_boundary_training_labels():
    x, y, elapsed = samples(np.ones((100, 1)) * 100, np.arange(0, 200, 2))
    assert len(elapsed) == len(x) == len(y) == 0


def test_training_rejects_missing_price_samples():
    times = np.arange(0, 780, 2)
    with pytest.raises(ValueError, match="grid"):
        samples(np.ones((389, 1)) * 100, np.delete(times, 50))


@pytest.mark.parametrize("train_end,eval_end", [(451, 451), (300, 451), (0, 450), (400, 300)])
def test_fitting_cannot_read_tune_or_verification_seasons(tmp_path, train_end, eval_end):
    with pytest.raises(ValueError, match="1.*450"):
        fit(tmp_path, train_end, eval_end)
