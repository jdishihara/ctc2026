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


@pytest.mark.parametrize('field,value', [('price_gate',-.01),('price_drift',float('nan'))])
def test_invalid_price_settings_rejected(field,value):
    with pytest.raises(ValueError, match=field):
        FairValueTrader(**{field:value})
