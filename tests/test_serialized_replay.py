import copy
import json
from pathlib import Path

import pytest

from bot.live import LiveSession
from ctc.strategies import FairValueTrader
from scripts.replay_serialized_client import OfflineExchange, ReplayServer

CASE = json.loads((Path(__file__).resolve().parents[1] / 'data/case.json').read_text())


def quote(at, bid=99., ask=100., size=1000, symbol='PORT'):
    return {'received_at': at, 'type': 'quote', 'symbol': symbol,
            'bid': bid, 'ask': ask, 'bid_size': size, 'ask_size': size}


def setup(frames=None):
    server = ReplayServer(copy.deepcopy(CASE), frames or [quote(0)], '1786', 'closed',
                          fraction=.1, depth_scale=1, rtt=0)
    exchange = OfflineExchange(server)
    server.advance(0)
    exchange.refresh()
    exchange.quotes = copy.deepcopy(server.market.quotes)
    exchange.mid = copy.deepcopy(server.market.mid)
    exchange.quote_times = copy.deepcopy(server.market.quote_times)
    server.inbox.drain()
    return server, exchange


def test_quotes_during_request_change_server_book_without_client_lookahead():
    server, exchange = setup([quote(0), quote(.2, 109., 110.)])
    server.rtt = .5
    exchange.get('/competitions/time')
    assert server.market.quotes['PORT'] == (109., 110.)
    assert exchange.quotes['PORT'] == (99., 100.)
    events = server.inbox.drain()
    assert events == [(quote(.2, 109., 110.), .2)]


def test_news_arriving_during_request_remains_pending_until_drain():
    message = {'received_at': .2, 'type': 'news', 'message': {
        'type': 'advisory', 'time': '1786-05-31T10:00:00', 'round': 1}}
    server, exchange = setup([quote(0), message])
    server.rtt = .5
    exchange.get('/competitions/time')
    assert server.inbox.pending_news.is_set()
    assert server.inbox.drain() == [(message, .2)]
    assert not server.inbox.pending_news.is_set()


def test_status_only_fill_reconciles_holdings_before_reusing_capacity():
    server, exchange = setup()
    first = exchange.place('PORT', 'buy', 10, 101.)
    assert first is not None
    assert exchange.position['PORT'] == 10
    assert not exchange.open_orders
    exchange.place('PORT', 'buy', 20, 101.)
    assert exchange.position['PORT'] == server.market.position['PORT'] == 20
    posts = [r for r in server.requests if r['method'] == 'POST']
    assert [r['body']['quantity'] for r in posts] == [10, 10]
    assert all(r['response']['status'] == 'filled' for r in posts)
    assert all('filled_quantity' not in r['response'] for r in posts)


def test_fill_after_pending_ack_snapshot_keeps_conservative_reservation():
    server, exchange = setup([quote(0), quote(.75, 79., 80.)])
    server.rtt = 1.
    exchange.place('PORT', 'buy', 10, 90.)
    assert server.market.position['PORT'] == 10
    assert exchange.position['PORT'] == 0
    assert exchange.resting('PORT', 'buy') == 10
    server.rtt = 0
    exchange.refresh()
    assert exchange.position['PORT'] == 10
    assert exchange.resting('PORT', 'buy') == 0


def test_fill_before_cancellation_is_in_reconciled_positions():
    server, exchange = setup([quote(0), quote(.2, 79., 80.)])
    exchange.place('PORT', 'buy', 10, 90.)
    server.rtt = .5
    assert exchange.cancel_all('PORT')
    assert exchange.position['PORT'] == 10
    assert not exchange.open_orders
    assert server.market.fills[0].price == 90.


def test_order_and_position_gets_observe_their_own_server_times():
    server, exchange = setup([quote(0), quote(.2, 79., 80.)])
    exchange.place('PORT', 'buy', 10, 90.)
    server.rtt = .2
    orders = exchange.get('/orders/open')['orders']
    positions = exchange.get('/positions?include_zero=true')['positions']
    assert orders[0]['quantity'] - orders[0]['filled_quantity'] == 10
    assert next(p['quantity'] for p in positions if p['symbol'] == 'PORT') == 10
    assert orders[0]['filled_quantity'] == 0  # Returned snapshot cannot mutate later.


def test_conversion_requires_reconciliation_and_preserves_basket_quantities():
    server, exchange = setup()
    assert exchange.create('ARCH', 1)
    assert not exchange.state_ready
    assert exchange.position['ARCH'] == 0
    exchange.refresh()
    assert exchange.position['ARCH'] == 1
    for symbol, quantity in CASE['etfs']['ARCH']['basket'].items():
        assert exchange.position[symbol] == -quantity


def test_adapter_never_falls_back_to_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('network access attempted')

    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    _, exchange = setup()
    exchange.place('PORT', 'buy', 1, 101.)
    assert exchange.cancel_all('PORT')
    with pytest.raises(NotImplementedError):
        exchange.get('/unsupported')


@pytest.mark.parametrize('rtt', [-1, float('nan'), float('inf')])
def test_invalid_request_delays_are_rejected(rtt):
    with pytest.raises(ValueError):
        ReplayServer(CASE, [quote(0)], '1786', 'closed', rtt=rtt)


def test_pending_news_vetoes_next_order_without_undoing_inflight_order(monkeypatch):
    message = {'received_at': .15, 'type': 'news', 'message': {
        'type': 'advisory', 'time': '1786-05-31T10:00:00', 'round': 1}}
    server, exchange = setup([quote(0), message])
    server.round = server.market.round = 1
    trader = FairValueTrader()
    trader.on_start(exchange)
    session = LiveSession(exchange, trader, sync=3, season_year='1786')
    monkeypatch.setattr(session, 'history_block_reason', lambda: None)
    session.pending_news = server.inbox.pending_news
    server.rtt = .2
    assert exchange.place('PORT', 'buy', 1, 101.) is not None
    assert server.market.position['PORT'] == 1
    assert exchange.market_open and server.inbox.pending_news.is_set()
    assert exchange.place('PORT', 'buy', 1, 101.) is None
    assert len([r for r in server.requests if r['method'] == 'POST']) == 1


def test_quotes_cannot_reopen_an_observed_closed_round():
    closed = {'received_at': .1, 'type': 'news', 'message': {
        'type': 'snapshot', 'phase': 'closed', 'round': 1, 'time': '1786-05-31T16:00:00'}}
    opened = {'received_at': .3, 'type': 'news', 'message': {
        'type': 'snapshot', 'phase': 'pre_storm', 'round': 2, 'time': '1786-06-01T09:30:00'}}
    server, exchange = setup([quote(0), closed, quote(.2, 79., 80.), opened, quote(.4)])
    exchange.place('PORT', 'buy', 10, 90.)
    server.advance(.25)
    assert not server.market.market_open
    assert not server.market.open_orders and server.market.position['PORT'] == 0
    server.advance(.4)
    assert server.market.market_open


def test_observed_close_wins_quote_matching_at_same_timestamp():
    closed = {'received_at': .2, 'type': 'news', 'message': {
        'type': 'snapshot', 'phase': 'closed', 'round': 1, 'time': '1786-05-31T16:00:00'}}
    server, exchange = setup([quote(0), quote(.2, 79., 80.), closed])
    server.round = server.market.round = 1
    exchange.place('PORT', 'buy', 10, 90.)
    server.advance(.2)
    assert not server.market.fills


def test_terminal_fence_wins_ties_but_preserves_final_news():
    final = {'received_at': .2, 'type': 'news', 'message': {
        'type': 'damage_report', 'round': 3, 'time': '1786-06-02T16:00:00'}}
    server, exchange = setup([quote(0), quote(.2, 79., 80.), final])
    server.end_at = .2
    exchange.place('PORT', 'buy', 10, 90.)
    server.advance(.2)
    assert server.terminal and not server.market.market_open
    assert not server.market.fills and not server.market.open_orders
    assert (final, .2) in server.inbox.drain()
    assert exchange.place('PORT', 'buy', 10, 90.) is None
    assert server.market.position['PORT'] == 0


def test_order_executed_before_fence_survives_response_after_fence():
    server, exchange = setup([quote(0)])
    server.end_at, server.rtt = .75, 1.
    assert exchange.place('PORT', 'buy', 10, 101.) is not None
    assert server.terminal and server.market.position['PORT'] == 10
    assert exchange.position['PORT'] == 10 and not exchange.market_open


def test_fill_between_orders_and_positions_reads_is_conservatively_reserved():
    server, exchange = setup([quote(0), quote(.2, 79., 80.)])
    exchange.place('PORT', 'buy', 10, 90.)
    server.rtt = .1
    exchange.refresh()
    assert exchange.position['PORT'] == 10 and exchange.resting('PORT', 'buy') == 10
    assert exchange.place('PORT', 'buy', 1, 90.) is None
    exchange.refresh()
    assert exchange.position['PORT'] == 10 and exchange.resting('PORT', 'buy') == 0


def test_orderbook_includes_own_orders_before_client_subtraction():
    server, exchange = setup()
    exchange.place('PORT', 'sell', 10, 100.)
    book = exchange.get('/orderbook/PORT')
    assert book['asks'] == [{'price': 100., 'quantity': 1010}]
    assert exchange.liquidity('PORT', 'buy', 100.) == 1000


def test_swallowed_adapter_error_is_fatal_for_final_validation(monkeypatch):
    server, exchange = setup()
    operation = server._operation

    def broken(method, path, body):
        if path == '/trades':
            raise ValueError('invalid adapter response construction')
        return operation(method, path, body)

    monkeypatch.setattr(server, '_operation', broken)
    exchange.poll_trades()  # Production catches the exception.
    assert server.fatal_errors


def test_lowest_mark_and_drawdown_are_distinct_server_metrics():
    server, exchange = setup([quote(0), quote(.1, 90., 92.), quote(.2, 110., 112.), quote(.3, 100., 102.)])
    exchange.place('PORT', 'buy', 10, 100.)
    server.advance(.3)
    assert server.lowest_mark == -90.
    assert server.max_drawdown == 100.


def synthetic_frames():
    from test_live_safety import complete_season
    return [{'received_at': i * .02, 'type': 'news',
             'message': {**message, 'time': '1786-05-31T10:00:00'}}
            for i, message in enumerate(complete_season())]


def test_complete_client_replay_is_offline_and_keeps_all_news(monkeypatch):
    import scripts.replay_serialized_client as replay

    def forbidden(*args, **kwargs):
        raise AssertionError('network access attempted')

    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    monkeypatch.setattr('socket.socket.connect', forbidden)
    row = replay.replay_client(CASE, synthetic_frames(), '1786', 'synthetic',
                               {s: 100. for s in CASE['limits']}, rtt=.05)
    assert row['final_report_rounds'] == [1, 2, 3]
    assert row['simulated_settlement_pnl'] == 0.
    assert row['orders'] == 0 and not any(row['final_positions'].values())
    assert row['request_counts']['GET /positions?include_zero=true'] > 0
    assert row['terminal_closed']


@pytest.mark.parametrize('rtt', [0., .25])
def test_complete_history_survives_first_quote_callback(monkeypatch, rtt):
    import scripts.replay_serialized_client as replay
    observed = []

    class AuditedTrader(FairValueTrader):
        def on_quotes(self, exchange):
            before = sorted(self.model.reported_rounds)
            super().on_quotes(exchange)
            observed.append((before, sorted(self.model.reported_rounds),
                             self.competition_id, exchange.competition_id))

    frames = synthetic_frames()
    frames += [quote(30., symbol=s) for s in CASE['limits']]
    frames += [{**frames[-1], 'received_at': 60.}]
    monkeypatch.setattr(replay, 'FairValueTrader', AuditedTrader)
    row = replay.replay_client(CASE, frames, '1786', 'synthetic',
                               {s: 100. for s in CASE['limits']}, rtt=rtt)
    assert observed
    assert all(before == after == [1, 2, 3] and strategy == account == 'synthetic'
               for before, after, strategy, account in observed)
    assert row['final_report_rounds'] == [1, 2, 3]


def test_settlement_values_are_not_accessed_until_irrevocable_close(monkeypatch):
    import scripts.replay_serialized_client as replay
    created = []

    class RecordingServer(ReplayServer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    class GuardedSettlement(dict):
        def __getitem__(self, symbol):
            assert created and created[0].terminal and not created[0].market.market_open
            return super().__getitem__(symbol)

    monkeypatch.setattr(replay, 'ReplayServer', RecordingServer)
    replay.replay_client(CASE, synthetic_frames(), '1786', 'synthetic',
                         GuardedSettlement({s: 100. for s in CASE['limits']}), rtt=0)


def test_full_replay_rejects_swallowed_contract_error(monkeypatch):
    import scripts.replay_serialized_client as replay
    operation = ReplayServer._operation

    def broken(self, method, path, body):
        if path == '/trades':
            raise NotImplementedError('deliberate contract failure')
        return operation(self, method, path, body)

    monkeypatch.setattr(ReplayServer, '_operation', broken)
    with pytest.raises(ValueError, match='contract'):
        replay.replay_client(CASE, synthetic_frames(), '1786', 'synthetic',
                             {s: 100. for s in CASE['limits']}, rtt=0)


@pytest.mark.parametrize('state', ['paused', None, 'running', 'ready'])
def test_completed_loader_checks_ready_before_touching_feed(tmp_path, monkeypatch, state):
    import scripts.replay_serialized_client as replay
    cid = 'closed'
    (tmp_path / 'status.json').write_text(json.dumps({'trials': {cid: {
        'completed': True, 'year': '1786', 'started_at': 0, 'completed_at': 1}}}))
    clock = {'competition_id': cid, 'fictional_time': '1786-05-31T16:00:00'}
    if state is not None:
        clock['state'] = state
    (tmp_path / 'actions.jsonl').write_text(json.dumps({'kind': 'settlement',
        'competition_id': cid, 'clock': clock, 'prices': {'PORT': 100.}}) + '\n')

    class FeedReached(Exception):
        pass

    def loader(*_):
        raise FeedReached

    monkeypatch.setattr(replay, 'completed_capture', loader)
    if state == 'ready':
        with pytest.raises(FeedReached):
            replay.confirmed_completed_capture(tmp_path, tmp_path / 'missing-feed', cid, {'PORT'})
    else:
        with pytest.raises(ValueError, match='ready'):
            replay.confirmed_completed_capture(tmp_path, tmp_path / 'missing-feed', cid, {'PORT'})
