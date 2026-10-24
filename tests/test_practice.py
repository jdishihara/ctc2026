import copy
import json
from unittest.mock import patch

import pytest

from bot import live
from bot.practice import Journal, PracticeExchange, PracticeSession, reconcile_stop, final_receipt
from ctc.strategies import FairValueTrader
from test_execution import CASE
from test_live_safety import complete_season, weather


@pytest.fixture
def setup(tmp_path):
    journal = Journal(tmp_path, seasons=1)
    responses = {
        '/cases/hurricane.json': copy.deepcopy(CASE),
        '/competitions/time': {'state': 'running', 'competition_id': 'test-1', 'fictional_time': '1788-05-26T10:00:00'},
        '/orders/open': {'orders': []}, '/positions?include_zero=true': {'positions': []}, '/trades': {'trades': []},
        '/symbols': {'symbols': [{'symbol': s, 'settlement_active': True, 'settlement_price': 101} for s in CASE['limits']]},
    }
    with patch.object(live.LiveExchange, 'get', side_effect=lambda path, api=True:
                      {**responses['/competitions/time'], 'name': 'Hurricane Season'}
                      if path == '/competitions/current' else responses[path]):
        ex = PracticeExchange('http://example.invalid', 'test-only', False, journal=journal)
        ex.refresh()
        strat = FairValueTrader(warmup=20)
        strat.on_start(ex)
        session = PracticeSession(ex, strat, sync=9999, journal=journal)
        yield journal, ex, session, responses


@pytest.mark.parametrize('kwargs', [{'fraction': 0}, {'fraction': 2}, {'loss_trigger': float('nan')},
                                  {'hours': float('inf')}, {'seasons': 0}])
def test_invalid_practice_bounds_rejected(tmp_path, kwargs):
    with pytest.raises(ValueError):
        Journal(tmp_path, **kwargs)


def test_practice_limits_do_not_change_valuation_case(setup):
    journal, ex, _, _ = setup
    assert ex.limits['PORT'] == 20
    assert ex.case['limits']['PORT'] == 200
    with patch.object(live.LiveExchange, 'send') as send:
        assert not ex.create('ARCH', 1000)
        send.assert_not_called()


def test_only_fresh_season_can_arm_practice(setup):
    journal, ex, session, _ = setup
    session._news({'type': 'storm_formed', 'round': 1, 'seq': 0})
    session._news(weather())
    ex.quotes['PORT'], ex.quote_times['PORT'] = (99, 100), ex.t
    assert not session.submission_allowed(('PORT',))  # Not armed yet.
    session.step([])
    assert 'test-1' in journal.trials
    assert session.submission_allowed(('PORT',))
    journal.trials.clear()
    session.strat.model.last_obs['age'] = 90
    session.step([])
    assert not journal.trials
    assert not session.submission_allowed(('PORT',))


def test_loss_trigger_blocks_requests_and_never_resets_after_recovery(setup):
    journal, ex, _, responses = setup
    journal.start_trial(ex)
    responses['/positions?include_zero=true'] = {'positions': [{'symbol': 'PORT', 'quantity': 0, 'realized_pnl': -251}]}
    ex.refresh()
    with patch.object(live.LiveExchange, 'send') as send:
        assert ex.send('POST', '/orders', {'quantity': 1}) is None
        send.assert_not_called()
    responses['/positions?include_zero=true'] = {'positions': []}
    ex.refresh()
    assert not journal.allowed()


def test_foreign_open_order_is_never_cancelled(setup):
    journal, ex, _, responses = setup
    responses['/orders/open'] = {'orders': [{'order_id': 'foreign', 'symbol': 'PORT', 'side': 'buy', 'quantity': 1}]}
    ex.refresh()
    with patch.object(live.LiveExchange, 'send') as send:
        assert not ex.cancel_all()
        send.assert_not_called()
    assert journal.stop_reason


def test_settlement_receipt_is_required_for_completed_trial(setup):
    journal, ex, session, responses = setup
    for message in complete_season():
        session._news(message)
    journal.start_trial(ex)
    ex.market_open = False
    responses['/competitions/time']['state'] = 'ready'
    ex.t0 -= 100
    responses['/positions?include_zero=true'] = {'positions': [{'symbol': 'PORT', 'quantity': 2,
        'average_price': 100, 'realized_pnl': 3, 'unrealized_pnl': -1}]}
    ex.raw_positions = responses['/positions?include_zero=true']
    responses['/symbols']['symbols'][0]['settlement_active'] = False
    session.step([])
    assert not journal.trials['test-1']['completed']
    responses['/symbols']['symbols'][0]['settlement_active'] = True
    ex.t0 -= 6
    session.step([])
    assert journal.trials['test-1']['settlement_pnl'] == 5
    assert journal.stop_reason == 'requested complete practice seasons recorded'


def test_rollover_without_settlement_is_flagged_not_counted_as_success(setup):
    journal, ex, _, responses = setup
    journal.start_trial(ex)
    responses['/competitions/time']['competition_id'] = 'test-2'
    ex.refresh()
    assert journal.stop_reason == 'season changed without verified settlement receipt'
    assert not journal.trials['test-1']['completed']


def test_cleanup_cannot_flatten_preexisting_exposure_on_failed_start(setup):
    journal, ex, _, _ = setup
    ex.position['PORT'] = 10
    with patch.object(live, 'LiveExchange') as exchange:
        reconcile_stop(journal, ex)
        exchange.assert_not_called()


def test_final_receipt_includes_cleanup_losses(setup):
    journal, ex, _, responses = setup
    journal.start_trial(ex)
    journal.trials['test-1']['last_pnl'] = -251
    responses['/positions?include_zero=true'] = {'positions': [{'symbol': 'PORT', 'quantity': 0,
        'realized_pnl': -260, 'unrealized_pnl': None}]}
    final_receipt(journal, ex)
    assert journal.trials['test-1']['last_pnl'] == -260
    assert journal.latest['final_receipt']['nonzero_positions'] == 0


def test_output_directory_cannot_reset_a_prior_loss_stop(tmp_path):
    old = Journal(tmp_path)
    old.stop('loss trigger')
    old.write(force=True)
    with pytest.raises((ValueError, FileExistsError)):
        Journal(tmp_path)
    assert json.loads((tmp_path / 'status.json').read_text())['stop_reason'] == 'loss trigger'


def test_completed_settlement_loss_is_latched_and_cannot_be_overwritten(setup):
    journal, ex, session, responses = setup
    journal.seasons = 3
    for message in complete_season():
        session._news(message)
    journal.start_trial(ex)
    responses['/competitions/time']['state'] = 'ready'
    responses['/positions?include_zero=true'] = {'positions': [
        {'symbol': 'PORT', 'quantity': 1, 'average_price': 401, 'realized_pnl': 0, 'unrealized_pnl': 0}]}
    ex.refresh()
    ex.t0 -= 100
    session.step([])
    assert journal.trials['test-1']['settlement_pnl'] == -300
    assert not journal.allowed()
    responses['/positions?include_zero=true'] = {'positions': []}
    ex.refresh()
    assert journal.trials['test-1']['last_pnl'] == -300


@pytest.mark.parametrize('basis', [None, float('nan')])
def test_settlement_without_finite_cost_basis_stays_unverified(setup, basis):
    journal, ex, session, responses = setup
    for message in complete_season():
        session._news(message)
    journal.start_trial(ex)
    responses['/competitions/time']['state'] = 'ready'
    responses['/positions?include_zero=true'] = {'positions': [
        {'symbol': 'PORT', 'quantity': 10, 'average_price': basis, 'realized_pnl': 0, 'unrealized_pnl': 0}]}
    ex.refresh()
    ex.t0 -= 100
    session.step([])
    assert not journal.trials['test-1']['completed']


def test_cancellation_only_targets_acknowledged_ids(setup):
    journal, ex, _, responses = setup
    owned = {'order_id': 'mine', 'symbol': 'PORT', 'side': 'sell', 'quantity': 1}
    foreign = {**owned, 'order_id': 'foreign'}
    ex.open_orders = [owned]
    journal.owned['test-1'] = {'mine'}
    responses['/orders/open'] = {'orders': [foreign]}
    with patch.object(live.LiveExchange, 'send', return_value={}) as send:
        assert not ex.cancel_all()
    assert all(c.args[1] == '/orders/mine' for c in send.call_args_list)
    assert journal.stop_reason


@pytest.mark.parametrize('path,response', [('/etf/ARCH/create', {}), ('/orders', None)])
def test_cleanup_reconciles_conversion_and_lost_ack_exposure(setup, path, response):
    journal, ex, _, responses = setup
    journal.start_trial(ex)
    with patch.object(live.LiveExchange, 'send', return_value=response):
        ex.send('POST', path, {'quantity': 1})
    responses['/positions?include_zero=true'] = {'positions': [
        {'symbol': 'PORT', 'quantity': 1, 'average_price': 100, 'realized_pnl': 0}]}
    responses['/competitions/time']['state'] = 'ready'
    reconcile_stop(journal, ex)
    events = [json.loads(line) for line in (journal.out / 'actions.jsonl').read_text().splitlines()]
    assert any(e['kind'] == 'cleanup_closed' for e in events)


@pytest.mark.parametrize('scenario', ['cancel_failed', 'rollover', 'foreign_after_cancel'])
def test_cleanup_never_replaces_unconfirmed_cancel_or_trades_changed_account(setup, scenario):
    journal, ex, _, _ = setup
    journal.start_trial(ex)
    with patch.object(live.LiveExchange, 'send', return_value={'order_id': 'mine'}):
        ex.send('POST', '/orders', {'quantity': 10})
    calls = 0
    def refresh(adapter):
        nonlocal calls
        calls += 1
        adapter.state_ready = adapter.market_open = True
        adapter.competition_id = 'test-2' if scenario == 'rollover' and calls >= 2 else 'test-1'
        adapter.position = {s: (10 if s == 'PORT' else 0) for s in adapter.symbols}
        order = {'order_id': 'mine', 'symbol': 'PORT', 'side': 'sell', 'quantity': 10}
        adapter.open_orders = [order] if scenario == 'cancel_failed' or calls == 1 else []
        if scenario == 'foreign_after_cancel' and calls >= 2:
            adapter.open_orders = [{**order, 'order_id': 'foreign'}]
    with patch.object(live.LiveExchange, 'refresh', refresh), \
         patch.object(live.LiveExchange, 'send', return_value=None) as send, \
         patch.object(live.LiveExchange, 'get', side_effect=lambda p, api=True:
                      copy.deepcopy(CASE) if p == '/cases/hurricane.json' else
                      {'competition_id': 'test-1', 'state': 'running'} if p == '/competitions/time' else
                      {'bids': [{'price': 100}], 'asks': [{'price': 101}]}), \
         patch('bot.practice.time.sleep'):
        reconcile_stop(journal, ex)
    assert not any(c.args[0] == 'POST' for c in send.call_args_list)


def test_cleanup_error_still_attempts_final_receipt(setup):
    from bot import practice as module
    journal, ex, _, _ = setup
    journal.exchange = ex
    with patch.object(module, 'reconcile_stop', side_effect=OSError('book unavailable')), \
         patch.object(module, 'final_receipt') as receipt:
        module.finish(journal)
    receipt.assert_called_once_with(journal, ex)
    assert journal.latest['cleanup']['state'] == 'attention'


def test_cleanup_stops_after_fill_refresh_moves_to_new_season(setup):
    journal, ex, _, _ = setup
    journal.start_trial(ex)
    with patch.object(live.LiveExchange, 'send', return_value={'order_id': 'mine'}):
        ex.send('POST', '/orders', {'quantity': 1})
    calls = 0
    def refresh(adapter):
        nonlocal calls
        calls += 1
        adapter.state_ready = adapter.market_open = True
        adapter.competition_id = 'test-2' if calls >= 4 else 'test-1'
        adapter.position = {s: (5 if s in ('PORT', 'ISLE') else 0) for s in adapter.symbols}
        adapter.open_orders = []
    with patch.object(live.LiveExchange, 'refresh', refresh), \
         patch.object(live.LiveExchange, 'send', return_value={'order_id': 'close-1', 'status': 'filled'}) as send, \
         patch.object(live.LiveExchange, 'get', side_effect=lambda p, api=True:
                      copy.deepcopy(CASE) if p == '/cases/hurricane.json' else
                      {'competition_id': 'test-1', 'state': 'running'} if p == '/competitions/time' else
                      {'bids': [{'price': 100}], 'asks': [{'price': 101}]}), \
         patch('bot.practice.time.sleep'):
        reconcile_stop(journal, ex)
    assert len([c for c in send.call_args_list if c.args[0] == 'POST']) == 1
    assert journal.latest['cleanup']['state'] == 'attention'


def test_failed_rollover_confirmation_cannot_forget_unsettled_trial(setup):
    journal, ex, _, responses = setup
    journal.start_trial(ex)
    responses['/competitions/time']['competition_id'] = 'test-2'
    clock_calls = 0
    def get(path, api=True):
        nonlocal clock_calls
        if path == '/competitions/time':
            clock_calls += 1
            if clock_calls == 2:
                raise OSError('confirmation unavailable')
        if path == '/competitions/current':
            return {**responses['/competitions/time'], 'name': 'Hurricane Season'}
        return responses[path]
    with patch.object(live.LiveExchange, 'get', side_effect=get):
        ex.refresh()
        assert not ex.state_ready
        ex.refresh()
    assert journal.trials['test-1'].get('invalid') == 'season changed without verified settlement receipt'
    assert not journal.allowed()
