import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bot import practice
from scripts.replay_practice_supervisor import (
    AccountingReplayExchange, AverageCostBook, AuditedJournal,
    OfflineCleanupExchange, OfflinePracticeExchange, PracticeReplayServer,
    VirtualMonitor, VirtualTime, replay_supervised,
)

CASE = json.loads((Path(__file__).resolve().parents[1] / 'data/case.json').read_text())


def quote(at, bid=99., ask=100., symbol='PORT', size=1000):
    return dict(received_at=at, type='quote', symbol=symbol, bid=bid, ask=ask,
                bid_size=size, ask_size=size)


@pytest.fixture(autouse=True)
def deny_external(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('offline replay attempted external access')
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    monkeypatch.setattr('socket.socket.connect', forbidden)
    original = Path.open

    def guarded(path, *args, **kwargs):
        if '.botkey' in str(path) or '/data/history/' in str(path):
            forbidden()
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)


def setup(tmp_path, frames=None, end_at=100, available_at=101):
    server = PracticeReplayServer(CASE, frames or [quote(0)], '1786', 'test',
                                  rtt=0, end_at=end_at,
                                  settlement={s: 100. for s in CASE['limits']},
                                  settlement_available_at=available_at)
    journal = AuditedJournal(tmp_path / 'journal', server=server, seasons=1)
    exchange = OfflinePracticeExchange(server, journal)
    journal.exchange = exchange
    server.advance(0)
    exchange.refresh()
    exchange.quotes = copy.deepcopy(server.market.quotes)
    exchange.mid = copy.deepcopy(server.market.mid)
    exchange.quote_times = copy.deepcopy(server.market.quote_times)
    server.inbox.drain()
    return server, journal, exchange


def test_average_cost_handles_add_partial_close_reversal_and_flat():
    book = AverageCostBook(['X'])
    for quantity, price in [(10, 100), (10, 120), (-5, 140)]:
        book.trade('X', quantity, price)
    row = book.rows({'X': 120})[0]
    assert row == dict(symbol='X', quantity=15, average_price=110.,
                       realized_pnl=150., unrealized_pnl=150.)
    assert book.cash == -1500
    book.trade('X', -20, 90)
    assert book.rows({'X': 80})[0] == dict(symbol='X', quantity=-5,
        average_price=90., realized_pnl=-150., unrealized_pnl=50.)
    assert book.cash == 300
    book.trade('X', 5, 70)
    assert book.cash == -50
    assert book.rows({'X': 999})[0] == dict(symbol='X', quantity=0,
        average_price=None, realized_pnl=-50., unrealized_pnl=0.)


@pytest.mark.parametrize('quantity,price', [(True, 1), (0, 1), (1.5, 1), (1, float('nan')), (1, 0)])
def test_invalid_accounting_inputs_rejected(quantity, price):
    with pytest.raises(ValueError):
        AverageCostBook(['X']).trade('X', quantity, price)


def test_cash_neutral_conversion_crosses_long_short_and_reconciles_settlement():
    market = AccountingReplayExchange(CASE, 1, latency=0)
    for symbol in CASE['limits']:
        market.update_quote(quote(0, 99, 101, symbol))
    market.place('PORT', 'buy', 2, 101)
    market._activate_pending()
    cash = market.cash
    assert market.create('ARCH', 1)
    assert market.redeem('ARCH', 2)
    assert market.create('ARCH', 1)
    assert market.cash == cash
    market.assert_accounting()
    prices = {s: 123 + i for i, s in enumerate(market.symbols)}
    score = practice.settlement_score(market.book.rows(prices), prices, market.position)
    assert score == pytest.approx(market.cash + sum(q * prices[s] for s, q in market.position.items()))


def test_owned_ids_recorded_before_filled_ack_refresh_and_retained_after_cancel(tmp_path):
    server, journal, ex = setup(tmp_path)
    filled = ex.place('PORT', 'buy', 10, 101)
    pending = ex.place('PORT', 'buy', 5, 80)
    assert filled in journal.owned['test'] and pending in journal.owned['test']
    assert ex.cancel_all()
    rows = ex.get('/orders?limit=500')['orders']
    assert {r['order_id']: r['filled_quantity'] for r in rows} == {filled: 10, pending: 0}
    assert not journal.ownership_blocks and ex.state_ready
    assert ex.limits['PORT'] == max(1, int(CASE['limits']['PORT'] * .1))
    assert server.market.limits == CASE['limits']


def test_observed_stale_mark_triggers_loss_at_observe_not_request_midpoint(tmp_path):
    frames = [quote(0), quote(1, 79, 80), quote(1.3, 109, 110)]
    server, journal, ex = setup(tmp_path, frames)
    assert ex.place('PORT', 'buy', 20, 101)
    server.advance(1)
    server.rtt = .1
    ex.refresh()
    assert journal.stop_reason.startswith('cumulative simulated P&L')
    assert journal.stop_at == pytest.approx(1.7)
    observation = journal.observations[-1]
    assert observation['positions_executed_at'] == pytest.approx(1.25)
    assert observation['observed_at'] == pytest.approx(1.7)
    assert observation['pnl'] == -410
    assert observation['server_pnl'] == 190
    before = server.market.next_id
    assert ex.send('POST', '/orders', {'symbol': 'PORT', 'side': 'buy', 'quantity': 1, 'price': 110}) is None
    assert server.market.next_id == before


@pytest.mark.parametrize('prior,mark,stopped', [(0, -249.99, False), (0, -250, True), (100, -300, False), (-100, -150, True)])
def test_cumulative_loss_boundary_uses_prior_trials(tmp_path, prior, mark, stopped):
    server, journal, ex = setup(tmp_path)
    journal.trials['prior'] = {'completed': True, 'settlement_pnl': prior}
    journal.start_trial(ex)
    journal.trials['test']['last_pnl'] = mark
    journal.check_loss()
    assert (journal.stop_reason is not None) == stopped


@pytest.mark.parametrize('worker_end,expected_cleanup', [(.2, .5), (.8, .8)])
def test_monitor_latches_on_anchored_tick_and_cleanup_joins_worker(tmp_path, worker_end, expected_cleanup):
    server, journal, ex = setup(tmp_path)
    stopped = []
    monitor = VirtualMonitor(server, journal, SimpleNamespace(stop=lambda: stopped.append(server.now)))
    server.monitor = monitor
    with patch.object(practice, 'time', VirtualTime(server)):
        server.advance(.1)
        journal.stop('fixture')
        server.advance(worker_end)
        if not monitor.cancelled:
            server.advance(monitor.next_tick)
    assert monitor.detected_at == .5
    assert server.now == expected_cleanup
    assert stopped == [.5]


def test_inflight_order_executes_after_monitor_cancels_but_before_worker_returns(tmp_path):
    server, journal, ex = setup(tmp_path)
    monitor = VirtualMonitor(server, journal, SimpleNamespace(stop=lambda: None))
    server.monitor = monitor
    with patch.object(practice, 'time', VirtualTime(server)):
        server.advance(.1)
        journal.stop('fixture')
        server.rtt = 1
        response = server.request('POST', '/orders', dict(symbol='PORT', side='buy', quantity=1, price=101))
    assert monitor.detected_at == .5
    assert response['status'] == 'filled'
    assert server.requests[-1]['executed_at'] == pytest.approx(.6)
    assert server.now == pytest.approx(1.1)


def test_production_cleanup_can_reduce_after_loss_stop_and_verifies_flat_receipt(tmp_path):
    server, journal, ex = setup(tmp_path)
    assert ex.place('PORT', 'buy', 10, 101)
    journal.stop('fixture loss stop')
    with patch.object(practice, 'time', VirtualTime(server)), patch.object(practice, 'CleanupExchange', OfflineCleanupExchange):
        practice.finish(journal)
    assert journal.latest['cleanup']['state'] == 'flat'
    assert journal.latest['final_receipt']['verified']
    assert journal.latest['final_receipt']['flat']
    assert not any(server.market.position.values())
    assert len(server.market.fills) == 2
    assert not server.fatal_errors


def test_production_cleanup_refuses_foreign_order_and_exposure_increase(tmp_path):
    server, journal, ex = setup(tmp_path)
    assert ex.place('PORT', 'buy', 10, 101)
    cleanup = OfflineCleanupExchange(ex, journal)
    cleanup.refresh()
    assert cleanup.send('POST', '/orders', dict(symbol='PORT', side='buy', quantity=1, price=101)) is None
    server.market.place('PORT', 'sell', 1, 120)
    server.market._activate_pending()
    cleanup.refresh()
    assert not cleanup.scope_ok()
    assert 'test' in journal.ownership_blocks
    assert server.market.position['PORT'] == 10


def test_settlement_is_unavailable_until_official_receipt_even_after_close(tmp_path):
    server, journal, ex = setup(tmp_path, end_at=2, available_at=4)
    server.advance(2)
    assert server.terminal
    assert not any(row['settlement_active'] for row in ex.get('/symbols')['symbols'])
    server.advance(4)
    assert all(row['settlement_active'] for row in ex.get('/symbols')['symbols'])


def test_full_supervised_replay_retains_no_trial_instead_of_inventing_completion(tmp_path):
    from test_serialized_replay import synthetic_frames
    frames = synthetic_frames()
    row = replay_supervised(CASE, frames, '1786', 'synthetic',
                            {s: 100. for s in CASE['limits']},
                            receipt_at=frames[-1]['received_at'] + 2,
                            out=tmp_path / 'run', rtt=.05)
    assert row['trial_state'] == 'no_trial'
    assert row['terminal_settlement_pnl'] == 0
    assert row['final_receipt']['verified'] and row['final_receipt']['flat']
    assert row['cleanup']['state'] == 'skipped'
    assert row['stop_reason'] == 'offline closed-market drain exhausted'


def test_healthy_monitor_tick_does_not_wake_idle_driver_early(tmp_path):
    from scripts.replay_practice_supervisor import wait_for_driver
    server, journal, ex = setup(tmp_path)
    server.monitor = VirtualMonitor(server, journal, SimpleNamespace(stop=lambda: None))
    server.advance(.4)
    wait_for_driver(server)
    assert server.now == pytest.approx(.65)
    assert server.monitor.next_tick == 1.


def test_cancelled_monitor_wakes_idle_driver_for_immediate_cleanup(tmp_path):
    from scripts.replay_practice_supervisor import wait_for_driver
    server, journal, ex = setup(tmp_path)
    server.monitor = VirtualMonitor(server, journal, SimpleNamespace(stop=lambda: None))
    server.advance(.4)
    journal.stop('fixture')
    with patch.object(practice, 'time', VirtualTime(server)):
        wait_for_driver(server)
    assert server.now == .5


def test_independent_practice_bound_detects_position_and_reserved_exposure(tmp_path):
    server, journal, ex = setup(tmp_path)
    server.market.diagnostic_limits = ex.limits.copy()
    with pytest.raises(ValueError, match='practice exposure'):
        server.request('POST', '/orders', dict(symbol='PORT', side='buy', quantity=21, price=80))
    assert server.fatal_errors


def test_bounded_startup_reuses_production_loader_without_future_news(tmp_path):
    from ctc.strategies import FairValueTrader
    from scripts.replay_practice_supervisor import startup_prefix
    from test_live_safety import weather
    frames = [dict(received_at=0, type='news', message=dict(type='storm_formed', round=1, seq=0, time='1786-01-01T00:00:00')),
              dict(received_at=.3, type='news', message={**weather(seq=1), 'time': '1786-01-01T00:00:00'}),
              dict(received_at=2, type='news', message={**weather(seq=2), 'time': '1786-01-01T00:00:00'})]
    server, journal, ex = setup(tmp_path, frames)
    trader = FairValueTrader()
    trader.on_start(ex)
    server.rtt = .4
    before = len(server.requests)
    year, rnd, count, seen = startup_prefix(ex, trader, server, tmp_path)
    assert (year, rnd, count, seen) == ('1786', 1, 2, {0, 1})
    assert len(server.requests) == before + 1
    assert server.now == .4
    assert all(f['received_at'] <= .4 for f in map(json.loads, (tmp_path / 'startup-feed.jsonl').read_text().splitlines()))


def test_advance_invariant_failure_is_latched_even_when_refresh_swallows_it(tmp_path, monkeypatch):
    server, journal, ex = setup(tmp_path)
    def corrupt():
        raise ValueError('fixture accounting corruption')
    monkeypatch.setattr(server.market, 'assert_accounting', corrupt)
    ex.refresh()
    assert not ex.state_ready
    assert any('accounting corruption' in error for error in server.fatal_errors)


def test_cleanup_identity_change_refuses_to_trade_new_competition(tmp_path):
    server, journal, ex = setup(tmp_path)
    assert ex.place('PORT', 'buy', 10, 101)
    cleanup = OfflineCleanupExchange(ex, journal)
    server.competition_id = 'new-competition'
    cleanup.refresh()
    assert not cleanup.scope_ok()
    assert server.market.position['PORT'] == 10


def test_saturated_history_stops_production_supervisor(tmp_path):
    from ctc.sim import Order
    server, journal, ex = setup(tmp_path)
    server.market.order_history = {i: Order(i, 'PORT', 'buy', 1, 1., 0., 0.) for i in range(1, 501)}
    journal.owned['test'] = set(range(1, 501))
    ex.refresh()
    assert 'saturated' in journal.stop_reason
    assert not ex.state_ready


def test_full_supervised_trial_completes_only_after_official_receipt(tmp_path):
    from test_serialized_replay import synthetic_frames
    frames = [{**frame, 'received_at': i * .1} for i, frame in enumerate(synthetic_frames())]
    receipt_at = frames[-1]['received_at'] + 2
    row = replay_supervised(CASE, frames, '1786', 'synthetic',
                            {s: 100. for s in CASE['limits']}, receipt_at=receipt_at,
                            out=tmp_path / 'run', rtt=.05)
    assert row['trial_state'] == 'completed'
    assert row['trial']['completed_at'] >= receipt_at
    assert row['stop_reason'] == 'requested complete practice seasons recorded'
    assert row['final_report_rounds'] == [1, 2, 3]
    assert row['orders'] == 0 and row['terminal_settlement_pnl'] == 0
    assert row['final_receipt']['verified']
    assert row['observed_final_receipt']['verified']
    assert len(row['final_receipt_requests']) == 5


def test_attention_receipt_is_not_frozen_when_residual_order_fills_later(tmp_path):
    server, journal, ex = setup(tmp_path, [quote(0), quote(5, 79, 80)], end_at=6, available_at=7)
    assert ex.place('PORT', 'buy', 10, 90)
    journal.stop('fixture')
    with patch.object(practice, 'time', VirtualTime(server)):
        practice.cleanup_status(journal, 'attention', reason='fixture unresolved order')
        practice.final_receipt(journal, ex)
    receipt = json.loads((journal.out / 'final-receipt.json').read_text())
    assert not any(row['quantity'] for row in receipt['positions']['positions'])
    assert len(receipt['orders']['orders']) == 1
    server.advance(7)
    assert server.market.position['PORT'] == 10
    assert len(server.market.fills) == 1
    assert server.market.cash + 100 * server.market.position['PORT'] == 100


def test_cleanup_honors_retry_limit_with_no_executable_bid(tmp_path):
    server, journal, ex = setup(tmp_path)
    assert ex.place('PORT', 'buy', 10, 101)
    server.market.available[('PORT', 'sell')] = 0
    journal.stop('fixture')
    with patch.object(practice, 'time', VirtualTime(server)), patch.object(practice, 'CleanupExchange', OfflineCleanupExchange):
        practice.finish(journal)
    assert journal.latest['cleanup']['state'] == 'attention'
    assert journal.latest['cleanup']['reason'] == 'cleanup retry limit'
    assert server.now == 5
    assert server.market.position['PORT'] == 10
    assert len(server.market.fills) == 1
    assert journal.latest['final_receipt']['verified'] and not journal.latest['final_receipt']['flat']
