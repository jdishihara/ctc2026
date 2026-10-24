"""Bounded cleanup behavior using the production adapter and virtual exchange."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bot import practice
from scripts.replay_practice_supervisor import OfflineCleanupExchange, ServerTransport, VirtualTime
from test_practice_replay import deny_external, quote, setup


def finish(server, journal):
    journal.stop('fixture')
    with patch.object(practice, 'CleanupExchange', OfflineCleanupExchange):
        practice.finish(journal)


@pytest.mark.parametrize('arrival', [6., 60.5, 61.])
def test_waits_for_fresh_quote_after_original_five_passes(tmp_path, arrival):
    server, journal, ex = setup(tmp_path, [quote(0), quote(arrival)])
    with patch.object(practice, 'time', VirtualTime(server)):
        assert ex.place('PORT', 'buy', 10, 101)
        server.market.available[('PORT', 'sell')] = 0
        finish(server, journal)
    assert journal.latest['cleanup']['state'] == 'flat'
    assert not any(server.market.position.values())
    assert len(server.market.fills) == 2
    assert arrival <= server.market.fills[-1].t <= 61
    assert server.now <= 62


def test_quote_after_admission_horizon_does_not_trigger_new_order(tmp_path):
    server, journal, ex = setup(tmp_path, [quote(0), quote(62)])
    with patch.object(practice, 'time', VirtualTime(server)):
        assert ex.place('PORT', 'buy', 10, 101)
        server.market.available[('PORT', 'sell')] = 0
        finish(server, journal)
    assert server.now == 62
    assert journal.latest['cleanup']['state'] == 'attention'
    assert server.market.position['PORT'] == 10
    assert len(server.market.fills) == 1


def test_partial_fills_cancel_owned_remainder_and_continue_reducing(tmp_path):
    server, journal, ex = setup(tmp_path, [quote(0), *[quote(t, size=3) for t in (6, 8, 10, 12)]])
    with patch.object(practice, 'time', VirtualTime(server)):
        assert ex.place('PORT', 'buy', 10, 101)
        server.market.available[('PORT', 'sell')] = 0
        finish(server, journal)
    assert journal.latest['cleanup']['state'] == 'flat'
    assert not any(server.market.position.values())
    assert sum(f.qty for f in server.market.fills if f.side == 'sell') == 10
    assert not journal.ownership_blocks


def test_slow_first_five_passes_are_preserved_beyond_horizon(tmp_path):
    server, journal, ex = setup(tmp_path, end_at=10000, available_at=10001)
    with patch.object(practice, 'time', VirtualTime(server)):
        assert ex.place('PORT', 'buy', 10, 101)
        server.market.available[('PORT', 'sell')] = 0
        server.rtt = 2
        finish(server, journal)
    books = [r for r in server.requests if r['path'].startswith('/orderbook/PORT')]
    assert len(books) == 5
    assert server.now > 61
    assert len(server.market.fills) == 1


def test_extra_orders_wait_past_strict_sixty_second_budget_boundary(tmp_path):
    server, journal, ex = setup(tmp_path, [quote(0), quote(6), quote(61)])
    with patch.object(practice, 'time', VirtualTime(server)):
        assert ex.place('PORT', 'buy', 10, 101)
        for _ in range(89):
            journal.event('request', method='DELETE', response=None)
        server.market.available[('PORT', 'sell')] = 0
        finish(server, journal)
    assert journal.latest['cleanup']['state'] == 'flat'
    assert server.market.fills[-1].t == 61
    assert not journal.ownership_blocks


def test_extra_cancellations_defer_without_a_fake_missing_ack(tmp_path):
    server, journal, ex = setup(tmp_path, [quote(0), quote(61)])
    original = OfflineCleanupExchange.send
    cancellations = []

    def delayed(self, method, path, body=None):
        if method == 'DELETE':
            cancellations.append(server.now)
            if server.now < 61:
                return {'status': 'pending'}
        return original(self, method, path, body)

    with patch.object(practice, 'time', VirtualTime(server)):
        assert ex.place('PORT', 'buy', 10, 101)
        assert ex.place('PORT', 'sell', 5, 150)
        for _ in range(83):
            journal.event('request', method='POST', path='/etfs/create', response=None)
        with patch.object(OfflineCleanupExchange, 'send', delayed):
            finish(server, journal)
    assert cancellations == [0, 1, 2, 3, 4, 61]
    assert not journal.ownership_blocks
    assert journal.latest['cleanup']['state'] == 'flat'


def test_lost_ack_during_extra_pass_blocks_further_cleanup(tmp_path):
    server, journal, ex = setup(tmp_path, [quote(0), quote(6), quote(7)])
    original = ServerTransport.send

    def missing(self, method, path, body=None):
        response = original(self, method, path, body)
        return None if method == 'POST' and server.now >= 6 else response

    with patch.object(practice, 'time', VirtualTime(server)):
        assert ex.place('PORT', 'buy', 10, 101)
        server.market.available[('PORT', 'sell')] = 0
        with patch.object(ServerTransport, 'send', missing):
            finish(server, journal)
    assert journal.ownership_blocks
    assert journal.latest['cleanup']['state'] == 'attention'
    assert sum(r['method'] == 'POST' for r in server.requests) == 2


def test_rollover_during_extra_pass_does_not_trade_new_account(tmp_path):
    server, journal, ex = setup(tmp_path, [quote(0), quote(6)])
    original = server.request

    def rollover(method, path, body=None):
        if server.now >= 6:
            server.competition_id = 'another-season'
        return original(method, path, body)

    with patch.object(practice, 'time', VirtualTime(server)):
        assert ex.place('PORT', 'buy', 10, 101)
        server.market.available[('PORT', 'sell')] = 0
        with patch.object(server, 'request', rollover):
            finish(server, journal)
    assert journal.latest['cleanup']['state'] == 'attention'
    assert len(server.market.fills) == 1


def test_foreign_filled_order_during_extra_pass_stops_without_adopting_it(tmp_path):
    server, journal, ex = setup(tmp_path, [quote(0), quote(6)])
    original = server.request
    injected = []

    def foreign(method, path, body=None):
        if server.now >= 6 and not injected:
            injected.append(server.market.place('PORT', 'sell', 1, 98))
            server.market._activate_pending()
        return original(method, path, body)

    with patch.object(practice, 'time', VirtualTime(server)):
        assert ex.place('PORT', 'buy', 10, 101)
        server.market.available[('PORT', 'sell')] = 0
        with patch.object(server, 'request', foreign):
            finish(server, journal)
    assert journal.ownership_blocks
    assert journal.latest['cleanup']['state'] == 'attention'
    assert sum(r['method'] == 'POST' for r in server.requests) == 1


def test_admitted_extra_pass_may_overrun_but_cannot_admit_another(tmp_path):
    server, journal, ex = setup(tmp_path, end_at=10000, available_at=10001)
    original = server.request

    def slow(method, path, body=None):
        if server.now >= 5:
            server.rtt = 10
        return original(method, path, body)

    with patch.object(practice, 'time', VirtualTime(server)):
        assert ex.place('PORT', 'buy', 10, 101)
        server.market.available[('PORT', 'sell')] = 0
        with patch.object(server, 'request', slow):
            finish(server, journal)
    books = [r for r in server.requests if r['path'].startswith('/orderbook/PORT')]
    assert len(books) == 6
    assert server.now > 61
    assert len(server.market.fills) == 1


def test_shadow_budget_counts_mutations_once_and_ignores_wall_clock(tmp_path):
    clock = SimpleNamespace(now=0., wall=1000.)
    virtual = SimpleNamespace(monotonic=lambda: clock.now, time=lambda: clock.wall)
    with patch.object(practice, 'time', virtual):
        journal = practice.Journal(tmp_path)
        for _ in range(30):
            journal.event('request_attempt', method='POST')
            journal.event('request', method='POST', response=None)
            journal.event('cleanup_order', order_id=None)
            journal.event('cleanup_cancel', response=None)
        journal.event('request', method='GET')
        assert not journal.extra_cleanup_mutation_allowed()
        clock.wall = -90000
        clock.now = 60
        assert not journal.extra_cleanup_mutation_allowed()
        clock.now = 60.001
        assert journal.extra_cleanup_mutation_allowed()
    rows = [json.loads(line) for line in (tmp_path / 'actions.jsonl').read_text().splitlines()]
    assert len(rows) == 121
    assert all('monotonic' not in row for row in rows)


@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), -1.])
def test_invalid_or_backward_mutation_clock_fails_closed(tmp_path, invalid):
    clock = SimpleNamespace(now=0.)
    virtual = SimpleNamespace(monotonic=lambda: clock.now, time=lambda: 1000.)
    with patch.object(practice, 'time', virtual):
        journal = practice.Journal(tmp_path)
        journal.event('request', method='POST')
        clock.now = invalid
        journal.event('cleanup_cancel', response=None)
        clock.now = 100
        assert not journal.extra_cleanup_mutation_allowed()


def test_missing_mutation_accounting_fails_closed(tmp_path):
    journal = practice.Journal.__new__(practice.Journal)
    assert not journal.extra_cleanup_mutation_allowed()
