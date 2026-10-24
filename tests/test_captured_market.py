import copy

from scripts.replay_captured_market import ReplayExchange
from test_execution import CASE


def exchange(latency=1):
    ex = ReplayExchange(copy.deepcopy(CASE), fraction=.1, latency=latency, depth_scale=1)
    ex.market_open = True
    return ex


def quote(ex, bid=99, ask=100, size=3):
    ex.update_quote({'type': 'quote', 'symbol': 'PORT', 'bid': bid, 'ask': ask,
                     'bid_size': size, 'ask_size': size})


def test_replay_orders_wait_for_latency_and_consume_displayed_quantity():
    ex = exchange()
    quote(ex)
    ex.place('PORT', 'buy', 7, 101)
    ex.advance(.5)
    assert ex.position['PORT'] == 0
    ex.advance(1)
    assert ex.position['PORT'] == 3
    assert ex.cash == -300
    ex.advance(2)
    assert ex.position['PORT'] == 3
    quote(ex, size=2)
    assert ex.position['PORT'] == 5


def test_replay_stale_touch_cannot_fill_a_delayed_order():
    ex = exchange(latency=6)
    quote(ex)
    ex.place('PORT', 'buy', 1, 101)
    ex.advance(6)
    assert ex.position['PORT'] == 0
    quote(ex, ask=102)
    assert ex.position['PORT'] == 0


def test_replay_has_no_fills_without_a_cross_and_respects_position_limits():
    ex = exchange(latency=0)
    quote(ex, size=1000)
    ex.place('PORT', 'buy', 1000, 98)
    ex.advance(1)
    assert ex.position['PORT'] == 0
    ex.cancel_all()
    ex.place('PORT', 'buy', 1000, 101)
    ex.advance(2)
    assert ex.position['PORT'] == 20


def test_replay_submission_guard_blocks_orders_and_conversions():
    ex = exchange()
    quote(ex)
    ex.submission_guard = lambda symbols: False
    assert ex.place('PORT', 'buy', 1, 100) is None
    assert not ex.create('ARCH', 1)
    assert not ex.pending and not any(ex.position.values())


def test_replay_close_cancels_pending_orders_without_erasing_inventory():
    ex = exchange(latency=1)
    quote(ex)
    ex.place('PORT', 'buy', 2, 101)
    ex.advance(1)
    ex.place('PORT', 'buy', 1, 101)
    ex.close_market()
    ex.advance(10)
    assert ex.position['PORT'] == 2
    assert not ex.open_orders
    assert not ex.market_open


def test_empty_market_close_quote_removes_old_executable_liquidity():
    ex = exchange(latency=1)
    quote(ex)
    ex.place('PORT', 'buy', 2, 101)
    ex.update_quote({'symbol': 'PORT', 'bid': None, 'ask': None, 'bid_size': 0, 'ask_size': 0})
    ex.advance(1)
    assert ex.position['PORT'] == 0
    assert 'PORT' not in ex.quotes


def test_order_activates_at_its_due_time_before_a_later_price_change():
    ex = exchange(latency=1)
    quote(ex, bid=199, ask=200)
    ex.place('PORT', 'buy', 1, 150)
    ex.advance(2, match=False)
    quote(ex, bid=99, ask=100)
    ex._activate_pending()
    assert ex.position['PORT'] == 1
    assert ex.cash == -150  # It was resting before the t=2 quote crossed 150.


def test_order_due_before_close_is_not_erased_as_still_pending():
    ex = exchange(latency=1)
    quote(ex)
    ex.place('PORT', 'buy', 1, 101)
    ex.advance(2, match=False)
    ex.close_market()
    assert ex.position['PORT'] == 1
    assert ex.cash == -100
