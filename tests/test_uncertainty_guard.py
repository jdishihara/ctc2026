import json
from pathlib import Path

import pytest

from ctc.sim import Sim
from scripts.experiment_uncertainty_guard import UncertaintyGuardTrader

CASE = json.loads((Path(__file__).resolve().parents[1] / 'data/case.json').read_text())


@pytest.fixture
def setup(tmp_path):
    (tmp_path / 'settlement.json').write_text(json.dumps({'PORT': 100}))
    (tmp_path / 'market.csv').write_text('time,round,PORT\n')
    (tmp_path / 'feed.jsonl').write_text('')

    def make(position=0, fair=102.3, entropy_cut=1.2, uncertain=True):
        sim = Sim(tmp_path, CASE)
        sim.market_open = True
        sim.mid = {'PORT': 100.}
        sim.quotes = {'PORT': (99.9, 100.1)}
        sim.position['PORT'] = position
        trader = UncertaintyGuardTrader(min_edge=.025, edge_full=.03, symbols=['PORT'],
                                 passive=.75, ent_cut=entropy_cut)
        trader.on_start(sim)
        trader.model.round = sim.round = 1
        trader.model.storm_active = True
        trader.model.posterior = ({str(i): .25 for i in range(4)} if uncertain else {'one': 1.})
        trader.fair = {'PORT': fair}
        trader.compute_fair = lambda: trader.fair
        trader.confidence = lambda _: 1.
        trader.min_edge_for = lambda *_: .025
        sim.t = 120.
        return trader, sim
    return make


@pytest.mark.parametrize('fair', [102.3, 97.7])
def test_uncertainty_blocks_new_passive_exposure(setup, fair):
    trader, sim = setup(fair=fair)
    trader.on_quotes(sim)
    assert not sim.pending


@pytest.mark.parametrize('position,fair,side', [(-50, 110., 'buy'), (50, 90., 'sell')])
def test_uncertain_reversal_can_close_but_not_cross_flat(setup, position, fair, side):
    trader, sim = setup(position=position, fair=fair)
    trader.on_quotes(sim)
    assert [(o.side, o.qty) for o in sim.pending] == [(side, abs(position))]


@pytest.mark.parametrize('position,fair,side', [(-50, 102.3, 'buy'), (50, 97.7, 'sell')])
def test_uncertain_small_edge_reversal_is_capped_at_flat(setup, position, fair, side):
    trader, sim = setup(position=position, fair=fair)
    trader.on_quotes(sim)
    assert [(o.side, o.qty) for o in sim.pending] == [(side, abs(position))]


@pytest.mark.parametrize('uncertain,cut', [(False, 1.2), (True, 0.)])
def test_low_uncertainty_or_disabled_rule_preserves_passive_orders(setup, uncertain, cut):
    trader, sim = setup(uncertain=uncertain, entropy_cut=cut)
    trader.on_quotes(sim)
    assert sim.pending and sim.pending[0].side == 'buy'


def test_uncertainty_cancels_safe_priced_additions_on_both_sides(setup):
    trader, sim = setup(fair=100.)
    sim.place('PORT', 'buy', 50, 90.)
    sim.place('PORT', 'sell', 50, 120.)
    trader.on_quotes(sim)
    assert not sim.pending


@pytest.mark.parametrize('filled,expected_quantity', [(30, 50), (50, 100)])
def test_partial_orders_use_remaining_quantity_for_reduction_capacity(setup, filled, expected_quantity):
    trader, sim = setup(position=-50, fair=110.)
    sim.place('PORT', 'buy', 100, 90.)
    sim.pending[0].filled = filled
    trader.on_quotes(sim)
    assert len(sim.pending) == 1
    assert sim.pending[0].qty == expected_quantity
    assert sim.pending[0].qty - sim.pending[0].filled == 50


@pytest.mark.parametrize('position,fair,side,sign', [(-50, 110., 'buy', 1), (50, 90., 'sell', -1)])
def test_fill_during_cancellation_recomputes_reduction_capacity(setup, monkeypatch, position, fair, side, sign):
    trader, sim = setup(position=position, fair=fair)
    sim.place('PORT', side, 100, 90. if side == 'buy' else 120.)
    cancel = sim.cancel_all

    def racing_cancel(symbol):
        sim.position[symbol] += sign * 20
        return cancel(symbol)

    monkeypatch.setattr(sim, 'cancel_all', racing_cancel)
    trader.on_quotes(sim)
    assert [(o.side, o.qty) for o in sim.pending] == [(side, 30)]


def test_failed_cancellation_does_not_send_replacement(setup, monkeypatch):
    trader, sim = setup(position=-50, fair=110.)
    sim.place('PORT', 'buy', 100, 90.)
    before = sim.next_id
    monkeypatch.setattr(sim, 'cancel_all', lambda symbol: False)
    trader.on_quotes(sim)
    assert sim.next_id == before
    assert len(sim.pending) == 1 and sim.pending[0].qty == 100
