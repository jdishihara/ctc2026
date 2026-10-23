import asyncio
import json
import threading
from types import SimpleNamespace

from bot import live


def session_fixture():
    ex = SimpleNamespace(t=100., competition_id='season-1', symbols=['A', 'B'],
        quotes={}, mid={}, quote_times={}, quotes_valid_after=-float('inf'),
        position={'A': 0, 'B': 0}, reopened=False, state_ready=True,
        market_open=True, round=1, pnl_now=0, refresh=lambda: None)
    calls, resets = [], []
    strat = SimpleNamespace(basket=None, paused=set(), fair={},
        model=SimpleNamespace(round=1, reported_rounds=set()),
        on_quotes=lambda ex: calls.append(ex.quote_times.copy()),
        on_start=lambda ex: resets.append(ex.competition_id), on_round=lambda ex: None)
    return live.LiveSession(ex, strat, sync=3), calls, resets


def quote(symbol='A', price=10):
    return {'type': 'quote', 'symbol': symbol, 'bid': price, 'ask': price + 1}


def test_quote_coalescing_preserves_every_news_message_in_arrival_order():
    inbox = live.MarketInbox()
    first = {'type': 'news', 'message': {'seq': 1}}
    second = {'type': 'news', 'message': {'seq': 2}}
    inbox.put(quote(), 100)
    inbox.put(first, 101)
    inbox.put(quote(price=12), 102)
    inbox.put(second, 103)
    assert inbox.drain() == [(first, 101), (quote(price=12), 102), (second, 103)]


def test_processing_delay_does_not_refresh_arrival_timestamp():
    session, calls, _ = session_fixture()
    session.ex.t = 103
    session.step([(quote(), 100)])
    assert session.ex.quote_times == {'A': 100}
    assert calls == [{'A': 100}]
    session.ex.t = 110
    session.step([(quote(price=20), 101)])
    assert not session.ex.quotes and not session.ex.quote_times
    assert len(calls) == 1


def test_heartbeat_drives_active_recovery_without_any_quote_frames():
    session, calls, _ = session_fixture()
    recovery = []
    session.strat.basket = SimpleNamespace(targets={'A': 0},
        on_quotes=lambda ex, paused: recovery.append(ex.t))
    session.ex.t = 120
    session.step([])
    assert recovery == [120]
    assert not calls


def test_internal_account_rollover_resets_model_before_next_cycle():
    session, _, resets = session_fixture()
    def roll_over(ex):
        ex.competition_id = 'season-2'
        ex.quotes.clear()
        ex.quote_times.clear()
        ex.quotes_valid_after = ex.t
    session.strat.on_quotes = roll_over
    session.step([(quote(), 100)])
    assert resets == ['season-2']
    session.ex.t = 102
    session.step([(quote(), 99)])  # A frame buffered before the account reset.
    assert not session.ex.quotes
    assert resets == ['season-2']


def test_receiver_coalesces_frames_while_http_work_blocks_the_trading_worker():
    async def scenario():
        session, calls, _ = session_fixture()
        started, release = threading.Event(), threading.Event()
        on_quotes = session.strat.on_quotes
        def blocking_http(ex):
            on_quotes(ex)
            started.set()
            assert release.wait(2), 'test did not release the HTTP worker'
        session.strat.on_quotes = blocking_http
        batches = []
        step = session.step
        def record_step(events):
            step(events)
            batches.append(events)
        session.step = record_step

        class Socket:
            def __init__(self):
                self.queue, self.received = asyncio.Queue(), 0
            def __aiter__(self):
                return self
            async def __anext__(self):
                frame = await self.queue.get()
                if frame is None:
                    raise StopAsyncIteration
                self.received += 1
                return json.dumps(frame)

        async def until(predicate):
            async with asyncio.timeout(2):
                while not predicate():
                    await asyncio.sleep(.001)

        socket = Socket()
        inbox = live.MarketInbox()
        receiver = asyncio.create_task(live.receive_market_data(socket, inbox, lambda: session.ex.t))
        driver = asyncio.create_task(live.drive_market_data(session, inbox, receiver, interval=.005))
        try:
            await socket.queue.put(quote())
            assert await asyncio.to_thread(started.wait, 1)
            session.ex.t = 101
            await socket.queue.put(quote('B'))
            await socket.queue.put(quote('A', 11))
            await until(lambda: socket.received == 3)
            session.ex.t = 102
            await socket.queue.put(quote('A', 12))
            await until(lambda: socket.received == 4)
            session.ex.t = 110
            release.set()
            await until(lambda: len(batches) >= 2)
            # Reception continued during HTTP. Only the newest A frame survives;
            # neither frame gains freshness when the trading thread catches up.
            arrivals = {d['symbol']: (d['bid'], t) for d, t in batches[1]}
            assert arrivals == {'A': (12, 102), 'B': (10, 101)}
            assert not session.ex.quotes
            assert len(calls) == 1
            await socket.queue.put(None)
            await asyncio.wait_for(driver, 2)
        finally:
            release.set()
            receiver.cancel()
            driver.cancel()
            await asyncio.gather(receiver, driver, return_exceptions=True)
    asyncio.run(scenario())
