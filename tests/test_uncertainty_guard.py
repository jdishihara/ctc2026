import json
from pathlib import Path

import pytest

from ctc.sim import Sim
from ctc.basket import BasketOverlay
import scripts.experiment_uncertainty_guard as experiment
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


def active_basket(trader, sim):
    basket = trader.basket = BasketOverlay(edge=.01)
    symbols = ['REBLD', *CASE['etfs']['REBLD']['basket']]
    for symbol in symbols:
        sim.mid[symbol] = 100.
        sim.quotes[symbol] = (99.9, 100.1)
    basket.targets = {symbol: sim.position[symbol] for symbol in symbols}
    basket.targets['MAT'] += 10
    basket.competition_id = getattr(sim, 'competition_id', None)
    basket.leg_submit['MAT'] = sim.t
    sim.place('MAT', 'buy', 10, 90.)
    return basket


def test_active_basket_does_not_hide_unrelated_fundamental_risk(setup):
    trader, sim = setup(fair=100.)
    basket = active_basket(trader, sim)
    sim.place('PORT', 'buy', 50, 90.)
    trader.on_quotes(sim)
    assert sim.resting('PORT', 'buy') == 0
    assert sim.resting('MAT', 'buy') == 10
    assert basket.targets is not None


@pytest.mark.parametrize('early_return', ['throttle', 'warmup', 'no_confidence', 'no_quote'])
def test_uncertain_orders_are_cancelled_before_fundamental_early_returns(setup, early_return):
    trader, sim = setup(fair=100.)
    sim.place('PORT', 'buy', 50, 90.)
    if early_return == 'throttle':
        trader.last_trade_t = sim.t
    elif early_return == 'warmup':
        trader.warmup, trader.round_open_t = 20, sim.t
    elif early_return == 'no_confidence':
        trader.confidence = lambda _: 0.
    else:
        sim.quotes.clear()
    trader.on_quotes(sim)
    assert not sim.pending


def test_cancel_failure_during_basket_keeps_hedge_and_limits_retries(setup, monkeypatch):
    trader, sim = setup()
    active_basket(trader, sim)
    sim.place('PORT', 'buy', 50, 90.)
    calls = []
    monkeypatch.setattr(sim, 'cancel_all', lambda symbol: calls.append(symbol) or False)
    trader.on_quotes(sim)
    trader.on_quotes(sim)
    assert calls == ['PORT']
    assert sim.resting('MAT', 'buy') == 10
    sim.t += 1
    trader.on_quotes(sim)
    assert calls == ['PORT', 'PORT']


def test_preflight_stops_after_competition_changes_during_cancel(setup, monkeypatch):
    trader, sim = setup(fair=110.)
    sim.place('PORT', 'buy', 50, 90.)
    cancel = sim.cancel_all

    def rollover(symbol):
        result = cancel(symbol)
        sim.competition_id = 'next-season'
        return result

    monkeypatch.setattr(sim, 'cancel_all', rollover)
    trader.on_quotes(sim)
    assert not sim.pending
    assert trader.competition_id == 'next-season'


def test_preflight_stops_if_cancellation_leaves_state_unready(setup, monkeypatch):
    trader, sim = setup(position=-50, fair=110.)
    sim.place('PORT', 'buy', 100, 90.)
    cancel = sim.cancel_all

    def unready(symbol):
        result = cancel(symbol)
        sim.state_ready = False
        return result

    monkeypatch.setattr(sim, 'cancel_all', unready)
    trader.on_quotes(sim)
    assert not sim.pending


@pytest.mark.parametrize('state', ['paused', None, 'running', 'ready'])
def test_completed_input_requires_confirmed_ready_receipt(tmp_path, monkeypatch, state):
    cid = 'closed-season'
    (tmp_path / 'status.json').write_text(json.dumps({'trials': {cid: {
        'completed': True, 'started_at': 0, 'completed_at': 10, 'year': '1786'}}}))
    clock = {'competition_id': cid, 'fictional_time': '1786-05-31T16:00:00'}
    if state is not None:
        clock['state'] = state
    (tmp_path / 'actions.jsonl').write_text(json.dumps({
        'kind': 'settlement', 'competition_id': cid, 'clock': clock, 'prices': {'PORT': 100}}) + '\n')
    feed = tmp_path / 'feed.jsonl'
    feed.write_text(json.dumps({'received_at': 1, 'type': 'news',
        'message': {'time': '1786-05-31T16:00:00', 'seq': 0}}) + '\n')
    monkeypatch.setattr(experiment, 'ROOT', tmp_path)
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/case.json').write_text(json.dumps({'limits': {'PORT': 100}}))
    monkeypatch.setattr(experiment.sys, 'argv', ['experiment', '--mode', 'completed',
        '--batch', str(tmp_path), '--feed', str(feed), '--competition-id', cid,
        '--baseline', str(tmp_path / 'reference.json'), '--out', str(tmp_path / 'out')])

    class AcceptedInput(Exception):
        pass

    def baseline(*_):
        raise AcceptedInput

    monkeypatch.setattr(experiment, 'reference_capture', baseline)
    if state == 'ready':
        with pytest.raises(AcceptedInput):
            experiment.main()
    else:
        with pytest.raises(ValueError, match='closed|ready'):
            experiment.main()
