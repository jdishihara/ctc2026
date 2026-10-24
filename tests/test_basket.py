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
    assert not overlay.on_quotes(sim, paused={'A'})
    assert not sim.pending
    assert overlay.targets is None


def test_completed_basket_releases_core_strategy_even_if_a_symbol_is_paused(setup):
    overlay, sim = setup()
    assert overlay.on_quotes(sim)
    sim.t += 2
    sim._activate_pending()
    assert not overlay.on_quotes(sim, paused={'A'})
    assert overlay.targets is None


def test_paused_partial_basket_cancels_orders_but_retains_inventory_targets(setup):
    overlay, sim = setup()
    assert overlay.on_quotes(sim)
    targets = overlay.targets.copy()
    assert overlay.on_quotes(sim, paused={'A'})
    assert not sim.pending
    assert overlay.targets == targets
    assert sim.position != targets


def test_expired_legs_cancel_without_fresh_quotes_or_replacement_budget(setup):
    overlay, sim = setup()
    sim.quote_times = {s: sim.t for s in sim.quotes}
    assert overlay.on_quotes(sim)
    targets = overlay.targets.copy()
    sim.t += 11
    sim.rate_limit = len(sim.actions) + 3  # Enough to cancel, not cancel AND replace.
    assert overlay.on_quotes(sim)
    assert not sim.pending
    assert overlay.targets == targets
    sim.rate_limit = 120
    sim.quote_times = {s: sim.t for s in sim.quotes}
    assert overlay.on_quotes(sim)
    assert len(sim.pending) == 3


def test_slow_cancel_requires_new_quotes_before_replacement(setup, monkeypatch):
    overlay, sim = setup()
    assert overlay.on_quotes(sim)
    sim.t += 10
    sim.quote_times = {s: sim.t for s in sim.quotes}
    cancel = sim.cancel_all
    def slow_cancel(symbol):
        sim.t += 6
        return cancel(symbol)
    monkeypatch.setattr(sim, 'cancel_all', slow_cancel)
    assert overlay.on_quotes(sim)
    assert not sim.pending
    assert overlay.targets is not None
    sim.quote_times = {s: sim.t for s in sim.quotes}
    assert overlay.on_quotes(sim)
    assert len(sim.pending) == 3


def test_slow_order_ack_cannot_price_later_legs_from_expired_quotes(setup, monkeypatch):
    overlay, sim = setup()
    sim.quote_times = {s: sim.t for s in sim.quotes}
    place = sim.place
    def slow_place(*args):
        result = place(*args)
        sim.t += 6
        return result
    monkeypatch.setattr(sim, 'place', slow_place)
    assert overlay.on_quotes(sim)
    assert len(sim.pending) == 1
    assert overlay.targets is not None


def test_fresh_quotes_resume_unsent_legs_without_waiting_for_other_leg_retry(setup, monkeypatch):
    overlay, sim = setup()
    sim.quote_times = {s: sim.t for s in sim.quotes}
    place = sim.place
    def first_slow_ack(*args):
        result = place(*args)
        sim.t += 6
        return result
    monkeypatch.setattr(sim, 'place', first_slow_ack)
    assert overlay.on_quotes(sim)
    assert [order.symbol for order in sim.pending] == ['ETF']
    first_order = sim.pending[0]
    monkeypatch.setattr(sim, 'place', place)
    sim.quote_times = {s: sim.t for s in sim.quotes}
    assert overlay.on_quotes(sim)
    assert sorted(order.symbol for order in sim.pending) == ['A', 'B', 'ETF']
    assert first_order in sim.pending  # No early cancel or duplicate ETF order.
    component_orders = [order for order in sim.pending if order.symbol != 'ETF']
    sim.t = 130
    sim.quote_times = {s: sim.t for s in sim.quotes}
    assert overlay.on_quotes(sim)
    assert first_order not in sim.pending  # ETF has had its full ten seconds.
    assert all(order in sim.pending for order in component_orders)  # Components have not.
    assert len(sim.pending) == 3


def test_guard_blocked_leg_is_eligible_as_soon_as_guard_recovers(setup, monkeypatch):
    overlay, sim = setup()
    place = sim.place
    calls = 0
    def news_interrupts(*args):
        nonlocal calls
        calls += 1
        return place(*args) if calls == 1 else None
    monkeypatch.setattr(sim, 'place', news_interrupts)
    assert overlay.on_quotes(sim)
    assert [order.symbol for order in sim.pending] == ['ETF']
    monkeypatch.setattr(sim, 'place', place)
    sim.t += 1
    assert overlay.on_quotes(sim)
    assert sorted(order.symbol for order in sim.pending) == ['A', 'B', 'ETF']


def change_competition(sim):
    sim.competition_id = 'next-season'
    sim.quotes.clear()
    sim.mid.clear()
    sim.position = {s: 0 for s in sim.symbols}
    sim.pending.clear()
    sim.orders.clear()


@pytest.mark.parametrize('phase', ['entry', 'recovery'])
@pytest.mark.parametrize('cancel_success', [True, False])
def test_competition_change_during_cancel_discards_old_targets(setup, monkeypatch, phase, cancel_success):
    overlay, sim = setup()
    sim.competition_id = 'first-season'
    if phase == 'recovery':
        sim.position['A'] = 7
        assert overlay.on_quotes(sim)
        sim.t += 10
    else:
        overlay.participation = .5
        sim.place('A', 'buy', 5, 8)
    def rollover_cancel(symbol):
        change_competition(sim)
        return cancel_success
    monkeypatch.setattr(sim, 'cancel_all', rollover_cancel)
    assert not overlay.on_quotes(sim)
    assert overlay.targets is None
    assert overlay.round_start is None
    assert not sim.pending and not any(sim.position.values())


def test_competition_change_during_depth_reads_cannot_convert(setup, monkeypatch):
    overlay, sim = setup()
    sim.competition_id = 'first-season'
    overlay.participation = .5
    def rollover_book(*args):
        change_competition(sim)
        return 100
    monkeypatch.setattr(sim, 'liquidity', rollover_book)
    assert not overlay.on_quotes(sim)
    assert overlay.targets is None and overlay.round_start is None
    assert not sim.actions


def test_competition_change_during_conversion_refresh_discards_old_targets(setup, monkeypatch):
    overlay, sim = setup()
    sim.competition_id = 'first-season'
    sim.position['A'] = 7
    convert = sim.create
    def uncertain(etf, qty):
        convert(etf, qty)
        sim.state_ready = False
        return False
    def rollover_refresh():
        change_competition(sim)
        sim.state_ready = True
    monkeypatch.setattr(sim, 'create', uncertain)
    monkeypatch.setattr(sim, 'refresh', rollover_refresh, raising=False)
    assert not overlay.on_quotes(sim)
    assert overlay.targets is None and overlay.round_start is None
    assert not sim.pending and not any(sim.position.values())


def test_round_change_keeps_partial_recovery_in_the_same_competition(setup):
    overlay, sim = setup()
    sim.competition_id = 'same-season'
    assert overlay.on_quotes(sim)
    targets = overlay.targets.copy()
    overlay.on_round(sim)
    assert overlay.targets == targets


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
