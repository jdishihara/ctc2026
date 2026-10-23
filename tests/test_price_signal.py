import json

import pytest

from ctc.price_signal import PriceSignal


@pytest.fixture
def signal(tmp_path):
    path = tmp_path / "model.json"
    path.write_text(json.dumps({"version": 1, "horizon": 120,
        "lags": [2, 10, 30, 60, 120], "phase_boundary": 540,
        "active_interval": [120, 650], "coefficients": {"PORT": {
            "storm": [0, 0, 0, 0, 0, 1], "aftermath": [.01, 0, 0, 0, 0, 1]}}}))
    return PriceSignal(path)


def fill_history(signal, start=0):
    for t in range(start, start + 121, 2):
        signal.observe(t, {"PORT": 100 + .1 * (t - start)})


def test_price_signal_uses_causal_lagged_returns(signal):
    fill_history(signal)
    assert signal.predict("PORT", 120, 120) == pytest.approx(12 / 112)


def test_price_signal_does_not_use_future_quote_for_current_or_lag(signal):
    fill_history(signal)
    signal.observe(122, {"PORT": 1000})
    assert signal.predict("PORT", 120, 120) == pytest.approx(12 / 112)


def test_signal_requires_full_history_and_supported_phase(signal):
    signal.observe(0, {"PORT": 100})
    assert signal.predict("PORT", 0, 120) is None
    fill_history(signal)
    assert signal.predict("PORT", 120, 700) is None
    assert signal.predict("UNKNOWN", 120, 120) is None
    assert signal.predict("PORT", 120, 119) is None


def test_signal_selects_aftermath_coefficients(signal):
    fill_history(signal, 420)
    assert signal.predict("PORT", 540, 540) == pytest.approx(.01 + 12 / 112)


def test_reset_discards_prior_round_prices(signal):
    fill_history(signal)
    signal.reset()
    signal.observe(120, {"PORT": 100})
    assert signal.predict("PORT", 120, 120) is None


@pytest.mark.parametrize("price", [0, -1, float("nan"), float("inf"), True])
def test_invalid_price_invalidates_symbol_history(signal, price):
    fill_history(signal)
    signal.observe(122, {"PORT": price})
    assert signal.predict("PORT", 122, 122) is None


@pytest.mark.parametrize("t", [100, 140])
def test_backward_clock_or_feed_gap_discards_history(signal, t):
    fill_history(signal)
    signal.observe(t, {"PORT": 112})
    assert signal.predict("PORT", t, 140) is None


def test_same_timestamp_symbol_updates_do_not_create_fake_momentum(signal):
    fill_history(signal)
    signal.observe(120, {"PORT": 112})
    assert signal.predict("PORT", 120, 120) == pytest.approx(12 / 112)


def test_lag_uses_quote_at_or_before_timestamp(signal):
    for t in range(0, 123, 2):
        signal.observe(t, {"PORT": 100 + .1 * t})
    # At t=121, 120s ago means t=1, so use the observed price at t=0.
    assert signal.predict("PORT", 121, 121) == pytest.approx(12 / 112)
