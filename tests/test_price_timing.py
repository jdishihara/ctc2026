import json
from pathlib import Path

import pytest

from ctc.price_signal import PriceSignal
from ctc.sim import Sim
from ctc.strategies import FairValueTrader

CASE = json.loads((Path(__file__).resolve().parents[1] / 'data/case.json').read_text())


@pytest.fixture
def setup(tmp_path):
    (tmp_path / 'settlement.json').write_text(json.dumps({'PORT': 100}))
    (tmp_path / 'market.csv').write_text('time,round,PORT\n')
    (tmp_path / 'feed.jsonl').write_text('')

    def make(prediction=-.02, gate=.005, drift=0, pos=0, fair=110, passive=0, exact=False):
        path = tmp_path / 'signal.json'
        coeff = [prediction, 0, 0, 0, 0, 0]
        path.write_text(json.dumps(dict(version=1, horizon=120, lags=[2,10,30,60,120],
            phase_boundary=540, active_interval=[120,650],
            coefficients={'PORT': {'storm': coeff, 'aftermath': coeff}})))
        sim = Sim(tmp_path, CASE)
        sim.market_open = True; sim.mid = {'PORT': 100}; sim.quotes = {'PORT': (99.9, 100.1)}
        sim.position['PORT'] = pos
        trader = FairValueTrader(min_edge=.025, edge_full=.03, symbols=['PORT'],
            price_gate=gate, price_drift=drift, passive=passive, final_exact=exact)
        trader.on_start(sim)
        trader.price_signal = PriceSignal(path)
        trader.on_round(sim)
        trader._price_round_start = 0  # This order fixture starts at a known round boundary.
        trader.model.round = 3; trader.model.storm_reported = True
        trader.fair = {'PORT': fair}
        for t in range(0,120,2):
            trader.price_signal.observe(t, sim.mid)
        sim.t = 120
        return trader, sim
    return make


@pytest.mark.parametrize('prediction,fair', [(-.02,110),(.02,90)])
def test_adverse_price_drift_blocks_new_exposure(setup, prediction, fair):
    trader, sim = setup(prediction=prediction, fair=fair)
    trader.on_quotes(sim)
    assert not sim.pending


def test_price_gate_permits_reducing_a_long_position(setup):
    trader, sim = setup(pos=150, fair=102.75)
    trader.on_quotes(sim)
    assert [(o.side,o.qty) for o in sim.pending] == [('sell',50)]


def test_blocked_flip_can_close_existing_short_but_not_open_long(setup):
    trader, sim = setup(pos=-50)
    trader.on_quotes(sim)
    assert [(o.side,o.qty) for o in sim.pending] == [('buy',50)]


def test_gate_cancels_a_resting_addition(setup):
    trader, sim = setup()
    sim.place('PORT','buy',100,105)
    trader.on_quotes(sim)
    assert not sim.pending


@pytest.mark.parametrize('side,pos,prediction,fair,price', [
    ('buy', -50, -.02, 103, 100.09), ('sell', 50, .02, 97, 99.91)])
@pytest.mark.parametrize('racing_fill', [0, 20])
def test_price_gate_replaces_oversized_passive_flip_even_at_same_price(
        setup, monkeypatch, side, pos, prediction, fair, price, racing_fill):
    trader, sim = setup(pos=pos, prediction=prediction, fair=fair, passive=.75)
    sim.place('PORT', side, 100, price)
    trader.passive_order['PORT'] = (side, price, sim.t)
    cancel = sim.cancel_all
    def racing_cancel(symbol):
        sim.position[symbol] += racing_fill * (1 if side == 'buy' else -1)
        return cancel(symbol)
    monkeypatch.setattr(sim, 'cancel_all', racing_cancel)
    trader.quote_passive(sim, 'PORT', fair, 99.9, 100.1, 1, .025, 200, pos)
    assert [(o.side, o.qty) for o in sim.pending] == [(side, 50 - racing_fill)]


def test_price_gate_also_blocks_new_passive_exposure(setup):
    trader, sim = setup(fair=101.9, passive=.75)
    trader.on_quotes(sim)
    assert not sim.pending


def test_no_price_history_preserves_base_strategy(setup):
    trader, sim = setup()
    trader.price_signal.reset()
    trader.on_quotes(sim)
    assert sim.pending[0].qty == CASE['limits']['PORT']


def test_exact_final_gate_bypasses_price_timing(setup):
    trader, sim = setup(exact=True)
    trader.model.reported_rounds = {1,2,3}
    trader.on_quotes(sim)
    assert sim.pending[0].qty == CASE['limits']['PORT']


def test_price_drift_adjustment_is_local_and_applied_once(setup):
    trader, sim = setup(gate=0, drift=1)
    trader.on_quotes(sim)
    first = sim.pending[0].price
    assert first == 105.36  # (110 - 100*.02) / 1.025, rounded down to cents
    assert trader.fair['PORT'] == 110
    sim.cancel_all('PORT')
    for t in range(122,138,2):
        sim.t = t
        trader.on_quotes(sim)
    assert sim.pending[0].price == first
    assert trader.fair['PORT'] == 110


def test_new_round_discards_price_history(setup):
    trader, sim = setup()
    trader.on_round(sim)
    assert trader.price_signal.predict('PORT',120,120) is None


def test_reconnect_without_storm_clock_does_not_assume_round_just_started(setup):
    trader, sim = setup()
    trader.on_round(sim)  # Live reconnect can happen in the aftermath.
    for t in range(120, 242, 2):
        trader.price_signal.observe(t, sim.mid)
    sim.t = 240
    assert trader.price_prediction(sim, 'PORT') is None


def test_live_storm_age_reanchors_clock_after_reconnect(setup):
    trader, sim = setup()
    trader.on_round(sim)
    sim.t = 200
    trader.on_news(sim, {'type': 'storm', 'round': 3, 'age': 420,
                        'x': 500, 'y': 500, 'radius': 100, 'intensity': 1})
    assert trader._price_round_start == 200 - 60 - 420
    for t in range(200, 322, 2):
        trader.price_signal.observe(t, sim.mid)
    sim.t = 320
    assert trader.price_prediction(sim, 'PORT') == pytest.approx(-.02)


def test_partial_quote_frames_do_not_refresh_a_missing_symbol(setup):
    trader, sim = setup()
    sim.quote_times = {'PORT': 120}
    for t in range(122, 138, 2):
        sim.t = t
        trader.on_quotes(sim)  # Other symbols are active; PORT's cached mid is stale.
    assert trader.price_prediction(sim, 'PORT') is None


@pytest.mark.parametrize('field,value', [('price_gate',-.01),('price_drift',float('nan'))])
def test_invalid_price_settings_rejected(field,value):
    with pytest.raises(ValueError, match=field):
        FairValueTrader(**{field:value})
