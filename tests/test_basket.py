import json

import pytest

from ctc.basket import BasketOverlay
from ctc.sim import Sim


@pytest.fixture
def setup(tmp_path):
    case = {'limits': {'A': 100, 'B': 100, 'ETF': 100},
            'etfs': {'ETF': {'basket': {'A': 1, 'B': 2}}}, 'timing': {'pre_storm': 60}}
    (tmp_path / 'settlement.json').write_text(json.dumps({'A': 10, 'B': 20, 'ETF': 50}))
    (tmp_path / 'market.csv').write_text('time,round,A,B,ETF\n')
    (tmp_path / 'feed.jsonl').write_text('')
    def make(etf=60):
        sim = Sim(tmp_path, case, rate_limit=120)
        sim.market_open = sim.state_ready = True
        sim.mid = {'A': 10, 'B': 20, 'ETF': etf}
        sim.quotes = {s: (p - .1, p + .1) for s, p in sim.mid.items()}
        overlay = BasketOverlay(.005)
        overlay.on_round(sim)
        sim.t = 60
        overlay.on_news(sim, {'type': 'storm', 'age': 0})
        sim.t = 120
        return overlay, sim
    return make


@pytest.mark.parametrize('etf,side', [(60, 'sell'), (40, 'buy')])
def test_profitable_basket_restores_existing_positions_and_earns_spread(setup, etf, side):
    overlay, sim = setup(etf)
    sim.position.update(A=7, B=-9, ETF=3)
    starting = sim.position.copy()
    pnl = sim.pnl()
    assert overlay.on_quotes(sim)
    assert overlay.targets == starting
    assert [(o.side, o.qty) for o in sim.pending if o.symbol == 'ETF'] == [(side, 10)]
    sim.t += 2
    sim._activate_pending()
    assert not overlay.on_quotes(sim)
    assert sim.position == starting
    assert sim.pnl() - pnl == pytest.approx(96)


def test_no_midpoint_only_arbitrage_after_spreads(setup):
    overlay, sim = setup(50.2)
    assert not overlay.on_quotes(sim)
    assert not sim.pending and not sim.actions


def test_conversion_size_respects_temporary_inventory_capacity(setup):
    overlay, sim = setup()
    sim.position['B'] = -94
    assert overlay.on_quotes(sim)
    assert sim.position['B'] == -100
    assert [o.qty for o in sim.pending if o.symbol == 'ETF'] == [3]


def test_stale_quote_or_unknown_round_clock_blocks_cycle(setup):
    overlay, sim = setup()
    sim.quote_times = {'A': 120, 'B': 100, 'ETF': 120}
    assert not overlay.on_quotes(sim)
    sim.quote_times['B'] = 120
    overlay.on_round(sim)
    assert not overlay.on_quotes(sim)
    assert not sim.actions


def test_reserves_action_headroom_before_starting(setup):
    overlay, sim = setup()
    sim.actions.extend([120] * 110)
    assert not overlay.on_quotes(sim)
    assert len(sim.actions) == 110
    sim.t = 200
    assert overlay.on_quotes(sim)  # Expired actions do not lock it forever.


def test_failed_cancel_cannot_start_a_conversion(setup, monkeypatch):
    overlay, sim = setup()
    sim.place('A', 'buy', 5, 8)
    monkeypatch.setattr(sim, 'cancel_all', lambda symbol: False)
    assert not overlay.on_quotes(sim)
    assert all(q == 0 for q in sim.position.values())


def test_starting_target_is_captured_after_cancel_racing_fill(setup, monkeypatch):
    overlay, sim = setup()
    sim.place('A', 'buy', 5, 8)
    cancel = sim.cancel_all
    def racing_cancel(symbol):
        sim.position[symbol] += 4
        return cancel(symbol)
    monkeypatch.setattr(sim, 'cancel_all', racing_cancel)
    assert overlay.on_quotes(sim)
    assert overlay.targets['A'] == 4


def test_uncertain_conversion_waits_for_account_then_restores_actual_inventory(setup, monkeypatch):
    overlay, sim = setup()
    convert = sim.create
    def uncertain(etf, qty):
        convert(etf, qty)
        sim.state_ready = False
        return False
    monkeypatch.setattr(sim, 'create', uncertain)
    assert overlay.on_quotes(sim)
    assert overlay.targets is not None
    assert not sim.pending
    sim.t += 2
    assert overlay.on_quotes(sim) and not sim.pending
    sim.state_ready = True
    assert overlay.on_quotes(sim)
    assert len(sim.pending) == 3


def test_timeout_restores_remaining_inventory_with_bounded_limits(setup):
    overlay, sim = setup()
    assert overlay.on_quotes(sim)
    # Only the ETF leg fills before the two component quotes move away.
    etf_order = next(o for o in sim.pending if o.symbol == 'ETF')
    sim._try_match(etf_order, passive=False)
    sim.pending.remove(etf_order)
    sim.quotes['A'] = (10.9, 11.1)
    sim.quotes['B'] = (20.9, 21.1)
    sim.t += 10
    assert overlay.on_quotes(sim)
    assert sorted((o.symbol, o.qty) for o in sim.pending) == [('A', 10), ('B', 20)]
    for order in sim.pending:
        assert order.price <= sim.quotes[order.symbol][1] * 1.02
    sim.t += 2
    sim._activate_pending()
    assert not overlay.on_quotes(sim)
    assert all(q == 0 for q in sim.position.values())


def test_completion_requires_no_outstanding_orders_and_pauses_cancel_legs(setup):
    overlay, sim = setup()
    assert overlay.on_quotes(sim)
    sim.position.update(overlay.targets)
    assert overlay.on_quotes(sim, paused={'A'})
    assert not sim.pending
    assert overlay.targets is not None


@pytest.mark.parametrize('edge', [-.1, float('nan')])
def test_invalid_threshold_rejected(edge):
    with pytest.raises(ValueError):
        BasketOverlay(edge)


def test_strategy_drives_basket_before_fundamental_rebalance(tmp_path):
    from pathlib import Path
    from ctc.strategies import FairValueTrader
    case = json.loads((Path(__file__).resolve().parents[1] / 'data/case.json').read_text())
    prices = {s: 10 for s in case['limits']}
    prices.update(ARCH=100, REBLD=50)
    (tmp_path / 'settlement.json').write_text(json.dumps(prices))
    (tmp_path / 'market.csv').write_text('time,round,PORT\n')
    (tmp_path / 'feed.jsonl').write_text('')
    sim = Sim(tmp_path, case)
    sim.market_open = True
    sim.mid = prices
    sim.quotes = {s: (p - .01, p + .01) for s, p in prices.items()}
    trader = FairValueTrader(basket_edge=.005)
    trader.on_start(sim)
    trader.on_round(sim)
    sim.t = 60
    trader.on_news(sim, {'type': 'storm_formed', 'round': 1})
    sim.t = 120
    trader.on_quotes(sim)
    basket = case['etfs']['ARCH']['basket']
    assert trader.basket.targets is not None
    assert len(sim.pending) == len(basket) + 1
    assert [(o.symbol, o.side, o.qty) for o in sim.pending if o.symbol == 'ARCH'] == [('ARCH', 'sell', 10)]
    # A second frame while those legs are pending cannot add fundamental orders.
    sim.t = 121
    trader.on_quotes(sim)
    assert len(sim.pending) == len(basket) + 1


def test_displayed_depth_limits_each_component_ratio(setup, monkeypatch):
    overlay, sim = setup()
    overlay.participation = .5
    monkeypatch.setattr(sim, 'liquidity', lambda symbol, side, limit: {'A': 100, 'B': 14, 'ETF': 100}[symbol], raising=False)
    assert overlay.on_quotes(sim)
    assert [o.qty for o in sim.pending if o.symbol == 'ETF'] == [3]
    assert [o.qty for o in sim.pending if o.symbol == 'B'] == [6]


def test_unknown_or_stale_depth_skips_conversion(setup, monkeypatch):
    overlay, sim = setup()
    overlay.participation = .5
    monkeypatch.setattr(sim, 'liquidity', lambda *args: None, raising=False)
    assert not overlay.on_quotes(sim)
    assert not any(sim.position.values())
    overlay.last_attempt = -1e9
    sim.quote_times = {s: sim.t for s in sim.quotes}
    def slow_book(*args):
        sim.t += 3
        return 100
    monkeypatch.setattr(sim, 'liquidity', slow_book)
    assert not overlay.on_quotes(sim)
    assert not any(sim.position.values())


def test_simulator_depth_read_is_non_consuming_and_excludes_consumed_depth(setup):
    from ctc.ladder import Ladder
    _, sim = setup()
    sim.ladder = Ladder(refill_secs=10, table={s: {'spread': .02, 'bands': [.01, .03],
                                                'bid': [20, 40], 'ask': [20, 40]} for s in sim.symbols})
    assert sim.liquidity('A', 'buy', 10.11) == 20
    assert sim.liquidity('A', 'buy', 10.11) == 20
    assert not sim.actions
    sim.ladder.fill('A', 'buy', 7, 10, sim.t, 10.11)
    assert sim.liquidity('A', 'buy', 10.11) == 13
    sim.t += 2
    assert sim.liquidity('A', 'buy', 10.11) == 17
