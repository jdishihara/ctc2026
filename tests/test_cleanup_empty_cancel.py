"""Cleanup can reuse its first snapshot only when there was nothing to cancel."""
import copy
from unittest.mock import patch

import pytest

from bot import live
from bot.practice import reconcile_stop
from test_execution import CASE
from test_practice import owned_history, setup


def run_cleanup(setup, *, quantity=5, initial_open=False, initially_closed=False, fault=None):
    journal, original, _, _ = setup
    journal.start_trial(original)
    journal.activity['test-1'] = True
    journal.owned['test-1'] = {'mine'}
    state = dict(quantity=quantity, open=initial_open, book=False, history_after_book=0,
                 closed=initially_closed, rollover=False, reads_before_book=None)
    calls, posts = [], []

    def get(path, api=True):
        calls.append(('GET', path))
        if path == '/cases/hurricane.json':
            return copy.deepcopy(CASE)
        if path == '/competitions/time':
            return {'competition_id': 'test-2' if state['rollover'] else 'test-1',
                    'state': 'ready' if state['closed'] else 'running',
                    'fictional_time': '1788-05-26T10:00:00'}
        if path == '/orders?limit=500':
            rows = owned_history(journal, 'test-1')
            if state['book']:
                state['history_after_book'] += 1
            if state['book'] and (fault == 'foreign' or
                    fault == 'foreign_before_send' and state['history_after_book'] >= 2):
                rows['orders'].append({'order_id': 'foreign', 'symbol': 'PORT',
                                      'side': 'buy', 'quantity': 1, 'filled_quantity': 1})
            return rows
        if path == '/orders/open':
            return {'orders': [{'order_id': 'mine', 'symbol': 'PORT', 'side': 'sell',
                                'quantity': 5, 'filled_quantity': 0}] if state['open'] else []}
        if path == '/positions?include_zero=true':
            if state['book'] and fault == 'position_timeout':
                raise OSError('positions unavailable')
            return {'positions': [{'symbol': 'PORT', 'quantity': state['quantity'],
                                   'realized_pnl': 0, 'unrealized_pnl': 0}]}
        if path == '/trades':
            return {'trades': []}
        if path == '/symbols':
            return {'symbols': [{'symbol': s, 'settlement_active': True,
                                 'settlement_price': 100} for s in CASE['limits']]}
        if path == '/orderbook/PORT?depth=1':
            if not state['book']:
                state['reads_before_book'] = sum(p == '/positions?include_zero=true' for _, p in calls)
            state['book'] = True
            if fault == 'flat':
                state['quantity'] = 0
            elif fault == 'reverse':
                state['quantity'] = -5
            elif fault == 'partial':
                state['quantity'] = 3
            elif fault == 'working':
                state['open'] = True
            elif fault == 'rollover':
                state['rollover'] = True
            elif fault == 'closed':
                state['closed'] = True
            return {'bids': [{'price': 99}], 'asks': [{'price': 101}]}
        raise AssertionError(path)

    def send(method, path, body=None):
        calls.append((method, path))
        if method == 'DELETE':
            if fault in ('cancel_failed', 'working'):
                return None
            state['open'] = False
            return {}
        assert method == 'POST' and path == '/orders'
        assert not state['open'] and not state['closed'] and not state['rollover']
        assert body['side'] == ('sell' if state['quantity'] > 0 else 'buy')
        assert 0 < body['quantity'] <= abs(state['quantity'])
        posts.append(copy.deepcopy(body))
        state['quantity'] = 0
        return {'order_id': 'close-1', 'status': 'filled',
                'quantity': body['quantity'], 'filled_quantity': body['quantity']}

    with patch.object(live.LiveExchange, 'get', side_effect=get), \
         patch.object(live.LiveExchange, 'send', side_effect=send), \
         patch('bot.practice.time.sleep'):
        reconcile_stop(journal, original)
    return journal, state, calls, posts


@pytest.mark.parametrize('quantity', [5, -5])
def test_empty_cancel_pass_does_not_delay_the_first_close_with_an_extra_refresh(setup, quantity):
    journal, state, calls, posts = run_cleanup(setup, quantity=quantity)
    assert state['reads_before_book'] == 1
    assert len(posts) == 1
    first_post = next(i for i, call in enumerate(calls) if call[0] == 'POST')
    before = calls[:first_post]
    # Initial reconciliation and a fresh position snapshot after the book.
    assert sum(p == '/positions?include_zero=true' for _, p in before) == 2
    assert before[-2:] == [('GET', '/orders?limit=500'), ('GET', '/competitions/time')]
    assert journal.latest['cleanup']['state'] == 'flat'


def test_cancellation_attempt_still_requires_another_refresh_before_the_book(setup):
    journal, state, calls, posts = run_cleanup(setup, initial_open=True)
    assert state['reads_before_book'] == 2
    deleted = calls.index(('DELETE', '/orders/mine'))
    book = calls.index(('GET', '/orderbook/PORT?depth=1'))
    assert ('GET', '/positions?include_zero=true') in calls[deleted + 1:book]
    assert len(posts) == 1
    assert journal.latest['cleanup']['state'] == 'flat'


@pytest.mark.parametrize('quantity,closed,expected', [(0, False, 'flat'), (5, True, 'settled')])
def test_flat_and_closed_accounts_keep_both_initial_refreshes(setup, quantity, closed, expected):
    journal, _, calls, posts = run_cleanup(setup, quantity=quantity, initially_closed=closed)
    assert sum(p == '/positions?include_zero=true' for _, p in calls) == 2
    assert not posts
    assert journal.latest['cleanup']['state'] == expected


@pytest.mark.parametrize('fault,expected', [('flat', None), ('reverse', ('buy', 5)), ('partial', ('sell', 3))])
def test_position_changes_during_book_are_reconciled_before_closing(setup, fault, expected):
    journal, _, _, posts = run_cleanup(setup, fault=fault)
    assert [(p['side'], p['quantity']) for p in posts] == ([] if expected is None else [expected])
    assert journal.latest['cleanup']['state'] == 'flat'


@pytest.mark.parametrize('fault', ['working', 'rollover', 'closed', 'foreign',
                                  'foreign_before_send', 'position_timeout', 'cancel_failed'])
def test_cleanup_submission_guards_survive_skipping_empty_cancel_refresh(setup, fault):
    journal, _, _, posts = run_cleanup(setup, fault=fault, initial_open=fault == 'cancel_failed')
    assert not posts
    assert journal.latest['cleanup']['state'] in ('attention', 'settled')
