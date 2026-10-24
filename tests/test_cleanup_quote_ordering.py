"""Closing prices must reflect changes during account reconciliation."""
import copy
from unittest.mock import patch

import pytest

from bot import live
from bot.practice import reconcile_stop
from test_execution import CASE
from test_practice import owned_history, setup


def run_cleanup(setup, *, quantity=5, fault=None):
    journal, original, _, _ = setup
    journal.start_trial(original)
    journal.activity['test-1'] = True
    journal.owned['test-1'] = {'mine'}
    state = {'quantity': quantity, 'position_reads': 0, 'price': 100,
             'book_reads': 0, 'after_book': False}
    posts = []

    def get(path, api=True):
        if path == '/cases/hurricane.json':
            return copy.deepcopy(CASE)
        if path == '/competitions/time':
            return {'competition_id': 'test-2' if fault == 'rollover' and state['after_book'] else 'test-1',
                    'state': 'ready' if fault == 'closed' and state['after_book'] else 'running',
                    'fictional_time': '1788-05-26T10:00:00'}
        if path == '/orders?limit=500':
            rows = owned_history(journal, 'test-1')
            if fault == 'foreign' and state['after_book']:
                rows['orders'].append({'order_id': 'foreign', 'symbol': 'PORT',
                                       'side': 'buy', 'quantity': 1, 'filled_quantity': 1})
            return rows
        if path == '/orders/open':
            return {'orders': []}
        if path == '/positions?include_zero=true':
            if state['after_book'] and fault == 'position_timeout':
                raise OSError('position check unavailable')
            if state['after_book'] and fault == 'position_envelope':
                return []
            state['position_reads'] += 1
            if state['position_reads'] == 3:
                # Prices move during the per-symbol reconciliation. A book
                # fetched before that reconciliation is no longer current.
                state['price'] = 110
                if fault == 'already_flat':
                    state['quantity'] = 0
            rows = [{'symbol': 'PORT', 'quantity': state['quantity'],
                     'realized_pnl': 0, 'unrealized_pnl': 0}]
            if fault == 'other_position_during_book' and state['after_book']:
                rows.append({'symbol': 'ISLE', 'quantity': 1, 'realized_pnl': 0, 'unrealized_pnl': 0})
            if fault == 'fractional_position' and state['after_book']:
                rows[0]['quantity'] = 5.5
            return {'positions': rows}
        if path == '/trades':
            return {'trades': []}
        if path == '/symbols':
            return {'symbols': [{'symbol': s, 'settlement_active': True,
                                 'settlement_price': 110} for s in CASE['limits']]}
        if path == '/orderbook/PORT?depth=1':
            state['book_reads'] += 1
            state['after_book'] = True
            if fault == 'flat_during_book':
                state['quantity'] = 0
            elif fault == 'reverse_during_book':
                state['quantity'] = -5
            elif fault == 'partial_during_book':
                state['quantity'] = 3
            price = 0 if fault == 'zero' else float('nan') if fault == 'nan' else state['price']
            levels = [] if fault == 'empty' else [{'price': price}]
            return {'bids': levels, 'asks': levels}
        raise AssertionError(path)

    def send(method, path, body=None):
        assert method == 'POST' and path == '/orders'
        posts.append(copy.deepcopy(body))
        assert body['side'] == ('sell' if state['quantity'] > 0 else 'buy')
        assert 0 < body['quantity'] <= abs(state['quantity'])
        state['quantity'] = 0
        return {'order_id': 'close-1', 'status': 'filled',
                'quantity': body['quantity'], 'filled_quantity': body['quantity']}

    with patch.object(live.LiveExchange, 'get', side_effect=get), \
         patch.object(live.LiveExchange, 'send', side_effect=send), \
         patch('bot.practice.time.sleep'):
        reconcile_stop(journal, original)
    return journal, state, posts


@pytest.mark.parametrize('quantity,expected_price', [(5, 108.9), (-5, 111.1)])
def test_cleanup_price_includes_move_during_account_reconciliation(setup, quantity, expected_price):
    journal, _, posts = run_cleanup(setup, quantity=quantity)
    assert len(posts) == 1
    assert posts[0]['price'] == expected_price
    assert journal.latest['cleanup']['state'] == 'flat'


@pytest.mark.parametrize('fault', ['rollover', 'foreign', 'closed', 'zero', 'nan', 'empty'])
def test_cleanup_rechecks_scope_after_new_book_and_rejects_invalid_prices(setup, fault):
    journal, state, posts = run_cleanup(setup, fault=fault)
    assert state['book_reads'] >= 1
    assert not posts
    assert state['quantity'] == 5
    assert journal.latest['cleanup']['state'] in ('attention', 'settled')


def test_position_closed_during_reconciliation_needs_no_new_quote_or_order(setup):
    journal, state, posts = run_cleanup(setup, fault='already_flat')
    assert not posts
    assert state['book_reads'] == 0
    assert journal.latest['cleanup']['state'] == 'flat'


@pytest.mark.parametrize('fault', ['flat_during_book', 'reverse_during_book',
                                 'partial_during_book', 'other_position_during_book'])
def test_cleanup_rejects_position_change_during_book_read(setup, fault):
    journal, _, posts = run_cleanup(setup, fault=fault)
    assert not posts
    assert journal.latest['cleanup']['state'] == 'attention'


@pytest.mark.parametrize('fault', ['position_timeout', 'position_envelope', 'fractional_position'])
def test_cleanup_requires_valid_post_quote_position_response(setup, fault):
    journal, _, posts = run_cleanup(setup, fault=fault)
    assert not posts
    assert journal.latest['cleanup']['state'] == 'attention'
