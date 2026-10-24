"""Offline regressions for the late-start loss and delayed execution batch."""
import asyncio
import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from bot.live import LiveSession, MarketInbox, drive_market_data, replay_feed_log
from ctc.strategies import FairValueTrader
from ctc.valuation import SeasonModel
from test_execution import ScriptedExchange

ROOT = Path(__file__).resolve().parents[1]
CASE = json.loads((ROOT / 'data/case.json').read_text())


def weather(age=0, round=1, seq=1):
    return dict(type='storm', round=round, seq=seq, age=age,
                x=age, y=500, radius=100, intensity=1, vx=1, vy=0)


def complete_season():
    """Complete causal history, independent of downloaded research files."""
    messages = []
    for rnd in (1, 2, 3):
        messages.append({'type': 'storm_formed', 'round': rnd})
        messages.extend(weather(age, rnd) for age in
                        range(0, CASE['timing']['storm'] + 1, CASE['timing']['obs_every']))
        messages.append({'type': 'storm_dissipated', 'round': rnd})
        messages.append({'type': 'damage_report', 'stage': 'final', 'round': rnd,
                         'damage_pct': {s: 0 for s in ('PORT', 'ISLE', 'AQUA', 'GRID', 'FERRY')},
                         'industry_loss_musd': 0})
    return [{**m, 'seq': seq} for seq, m in enumerate(messages)]


def prepared():
    ex = ScriptedExchange()
    ex.responses['/competitions/time']['fictional_time'] = '1788-05-26T10:00:00'
    ex.refresh()
    strat = FairValueTrader(warmup=0)
    strat.on_start(ex)
    session = LiveSession(ex, strat, sync=9999)
    session._news({'type': 'storm_formed', 'round': 1, 'seq': 0})
    session._news(weather())
    for symbol in ex.symbols:
        ex.quotes[symbol] = (99., 100.)
        ex.quote_times[symbol] = ex.t
        ex.mid[symbol] = 99.5
    return ex, session


def test_continuous_snapshot_keeps_completed_warmup_and_allows_signal():
    with patch('bot.live.time.monotonic', return_value=100.):
        ex, session = prepared()
        ex.t0 = 0.
        strat = session.strat
        strat.warmup = 20.
        strat.round_open_t = 50.
        fair = {symbol: 120. if symbol == 'PORT' else 99.5 for symbol in ex.symbols}
        snapshot = dict(type='snapshot', round=1, last_seq=1,
                        time='1788-05-26T10:00:00', phase='storm',
                        obs={'age': 0}, track=[], damage=[])
        with patch.object(strat, 'compute_fair', return_value=fair), \
                patch.object(strat, 'confidence', return_value=1.), \
                patch.object(strat, 'min_edge_for', return_value=.01), \
                patch.object(ex, 'place') as place:
            session._news(snapshot)
            strat.on_quotes(ex)
        assert session.history_block_reason() is None
        assert any(call.args[:2] == ('PORT', 'buy') for call in place.call_args_list)
        assert strat.round_open_t == 50.


@pytest.mark.parametrize('interruption', ['disconnect', 'missing_news'])
def test_snapshot_after_interruption_still_requires_warmup(interruption):
    with patch('bot.live.time.monotonic', return_value=100.):
        ex, session = prepared()
        ex.t0 = 0.
        strat = session.strat
        strat.warmup = 20.
        strat.round_open_t = 50.
        if interruption == 'disconnect':
            session.feed_current = False
        snapshot = dict(type='snapshot', round=1,
                        last_seq=10 if interruption == 'missing_news' else 1,
                        time='1788-05-26T10:00:00', phase='storm',
                        obs={'age': 0}, track=[], damage=[])
        session._news(snapshot)
        with patch.object(ex, 'place') as place:
            strat.on_quotes(ex)
        place.assert_not_called()
        assert strat.round_open_t == 100.
        if interruption == 'missing_news':
            assert 'missing news history' in session.history_block_reason()


@pytest.mark.parametrize('include_snapshot', [False, True])
def test_contiguous_news_after_disconnect_cannot_skip_reconnect_warmup(include_snapshot):
    with patch('bot.live.time.monotonic', return_value=100.) as clock:
        ex, session = prepared()
        ex.t0 = 0.
        ex.reopened = False
        strat = session.strat
        strat.warmup = 20.
        strat.round_open_t = 50.
        fair = {symbol: 120. if symbol == 'PORT' else 99.5 for symbol in ex.symbols}
        session.step([({'type': 'disconnected'}, 100.)])
        events = [({'type': 'news', 'message': weather(age=2, seq=2)}, 100.)]
        if include_snapshot:
            events.append(({'type': 'news', 'message': dict(
                type='snapshot', round=1, last_seq=2, phase='storm',
                time='1788-05-26T10:00:00', obs={'age': 2}, track=[], damage=[])}, 100.))
        quotes = [({'type': 'quote', 'symbol': symbol, 'bid': 99., 'ask': 100.}, 100.)
                  for symbol in ex.symbols]
        with patch.object(strat, 'compute_fair', return_value=fair), \
                patch.object(strat, 'confidence', return_value=1.), \
                patch.object(strat, 'min_edge_for', return_value=.01), \
                patch.object(ex, 'place') as place:
            session.step(events + quotes)
            assert session.history_block_reason() is None
            place.assert_not_called()
            assert strat.round_open_t == 100.
            clock.return_value = 121.
            session.step([(frame, 121.) for frame, _ in quotes])
            assert any(call.args[:2] == ('PORT', 'buy') for call in place.call_args_list)


def test_captured_late_start_cannot_submit_even_after_snapshot_recovery():
    ex, session = prepared()
    session.strat.on_start(ex)
    session.seen_seq.clear()
    captured = json.loads((ROOT / 'tests/fixtures/live_midstorm_snapshot.json').read_text())
    for message in captured['observed']:
        session._news(message)
    session._news(captured['snapshot'])
    with patch.object(ex, 'send') as send:
        assert ex.place('HAVEN', 'sell', 250, 57.9) is None
        assert ex.create('ARCH', 1) is False
        assert ex.redeem('ARCH', 1) is False
        send.assert_not_called()


def test_complete_history_allows_orders_and_missing_news_blocks_them():
    ex, session = prepared()
    with patch.object(ex, 'send', return_value={'order_id': 'ok', 'filled_quantity': 1}) as send:
        assert ex.place('PORT', 'buy', 1, 100) == 'ok'
        # Weather is continuous, but more than MAX_MISSING_NEWS lost advisories/announcements block too.
        session._news(weather(age=2, seq=10))
        assert ex.place('PORT', 'buy', 1, 100) is None
        assert send.call_count == 1


@pytest.mark.parametrize('change', ['aged_quote', 'pending_news', 'stopped', 'rollover'])
def test_each_submission_rechecks_state_after_a_slow_request(change):
    ex, session = prepared()
    inbox = MarketInbox()
    session.pending_news = inbox.pending_news
    def ack(*args):
        if change == 'aged_quote':
            ex.t0 -= 6
        elif change == 'pending_news':
            inbox.put({'type': 'news', 'message': weather(2, seq=2)}, ex.t)
        elif change == 'stopped':
            session.stop()
            ex.refresh()  # Reconciliation must not clear the stop latch.
        else:
            ex.competition_id = 'season-2'
        return {'order_id': 'first', 'filled_quantity': 1}
    with patch.object(ex, 'send', side_effect=ack) as send:
        assert ex.place('PORT', 'buy', 1, 100) == 'first'
        assert ex.place('GRID', 'buy', 1, 100) is None
        assert ex.create('ARCH', 1) is False
        assert send.call_count == 1


def test_missing_history_cancels_resting_orders_without_flattening_positions():
    ex, session = prepared()
    ex.open_orders = [{'symbol': 'PORT', 'side': 'buy', 'quantity': 5,
                       'filled_quantity': 0, 'order_id': 'resting'}]
    session.strat.model.outage_history_complete = False
    before = dict(ex.position)
    with patch.object(ex, 'send', return_value={}) as send:
        session.step([])
        assert send.call_args.args[:2] == ('DELETE', '/orders/all')
        assert send.call_count == 1
    assert not ex.open_orders
    assert ex.position == before


def test_disconnection_needs_news_checkpoint_before_resuming():
    ex, session = prepared()
    session.step([({'type': 'disconnected'}, ex.t)])
    for symbol in ex.symbols:
        ex.quotes[symbol] = (99., 100.)
        ex.quote_times[symbol] = ex.t
    with patch.object(ex, 'send', return_value={'order_id': 'ok', 'filled_quantity': 1}) as send:
        assert ex.place('PORT', 'buy', 1, 100) is None
        session._news(weather(age=2, seq=2))
        assert ex.place('PORT', 'buy', 1, 100) == 'ok'
        assert send.call_count == 1


@pytest.mark.parametrize('old_checkpoint', [weather(seq=0),
    {'type': 'snapshot', 'round': 1, 'phase': 'storm', 'last_seq': 0}])
def test_old_checkpoint_cannot_clear_disconnection(old_checkpoint):
    ex, session = prepared()
    session.feed_current = False
    session._news(old_checkpoint)
    with patch.object(ex, 'send') as send:
        assert ex.place('PORT', 'buy', 1, 100) is None
        send.assert_not_called()


def test_news_rollover_fences_old_account_and_preserves_new_history_on_sync():
    ex, session = prepared()
    session.season_year = '1788'
    session._news({'type': 'storm_formed', 'round': 1, 'seq': 0,
                   'time': '1789-05-26T10:00:00'})
    session._news({**weather(), 'time': '1789-05-26T10:00:00'})
    # New quotes cannot license an order against old-season positions/limits.
    for symbol in ex.symbols:
        ex.quotes[symbol] = (99., 100.)
        ex.quote_times[symbol] = ex.t
    with patch.object(ex, 'send', return_value={'order_id': 'ok', 'filled_quantity': 1}) as send:
        ex.refresh()  # Even a successful old-ID refresh is insufficient.
        session._competition_changed()
        assert ex.place('PORT', 'buy', 1, 100) is None
        send.assert_not_called()
        ex.responses['/competitions/time']['competition_id'] = 'season-2'
        ex.responses['/competitions/time']['fictional_time'] = '1789-05-26T10:00:00'
        ex.refresh()
        session._competition_changed()
        assert session.seen_seq == {0, 1}
        assert session.history_block_reason() is None
        session.strat.warmup = 9999
        session.step([({'type': 'quote', 'symbol': s, 'bid': 99, 'ask': 100}, ex.t)
                      for s in ex.symbols])
        assert session.strat.model.round == 1
        session._news({**weather(age=2, seq=2), 'time': '1789-05-26T10:01:00'})
        assert session.strat.model.live_history_ready
        ex.quotes['PORT'] = (99., 100.)
        ex.quote_times['PORT'] = ex.t
        assert ex.place('PORT', 'buy', 1, 100) == 'ok'


def test_account_rollover_before_buffered_news_keeps_new_season_eligible():
    ex, session = prepared()
    session.season_year = '1788'
    ex.responses['/competitions/time'].update(competition_id='season-2', fictional_time='1789-05-26T10:00:00')
    ex.refresh()
    messages = [{**weather(age=2, seq=2), 'time': '1788-05-26T10:01:00'},
                {'type': 'storm_formed', 'round': 1, 'seq': 0, 'time': '1789-05-26T10:00:00'},
                {**weather(), 'time': '1789-05-26T10:00:00'}]
    session.step([({'type': 'news', 'message': m}, ex.t) for m in messages])
    assert session.history_block_reason() is None
    assert session.seen_seq == {0, 1}
    assert session.strat.model.round == 1
    # A delayed prior-year snapshot cannot rewind the restored new season.
    session._news({'type': 'snapshot', 'round': 3, 'last_seq': 600,
                   'time': '1788-05-28T11:00:00'})
    assert session.history_block_reason() is None
    assert session.strat.model.round == 1
    assert session.seen_seq == {0, 1}


def test_replay_clock_rollover_cannot_use_previous_account_snapshot():
    ex, previous = prepared()
    # Replay's separate time request selected the new year after account refresh.
    session = LiveSession(ex, previous.strat, sync=9999,
                          season_year='1789', seen_seq={0, 1})
    session.feed_current = True
    with patch.object(ex, 'send') as send:
        assert ex.place('PORT', 'buy', 1, 100) is None
        send.assert_not_called()
    ex.responses['/competitions/time'].update(competition_id='season-2', fictional_time='1789-05-26T10:00:00')
    ex.refresh()
    session._competition_changed()
    assert session.history_block_reason() is None
    assert session.strat.competition_id == 'season-2'
    assert session.strat.model.round == 1


def test_unknown_foreign_year_snapshot_cannot_replace_current_history():
    ex, session = prepared()
    before = list(session.strat.model.obs)
    session._news({'type': 'snapshot', 'round': 3, 'last_seq': 600,
                   'time': '1787-05-28T11:00:00'})
    assert session.strat.model.obs == before
    assert session.season_year == '1788'
    assert not session.feed_current
    session._news({'type': 'snapshot', 'round': 1, 'phase': 'storm', 'last_seq': 1,
                   'time': '1788-05-26T10:00:00'})
    assert session.history_block_reason() is None
    assert session.strat.model.round == 1


def test_cancelling_driver_stops_worker_before_its_next_order():
    async def scenario():
        ex, session = prepared()
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        results = []
        def step(events):
            started.set()
            assert release.wait(2)
            results.append(ex.place('PORT', 'buy', 1, 100))
            finished.set()
        session.step = step
        inbox = MarketInbox()
        inbox.put({'type': 'quote'}, ex.t)
        receiver = asyncio.create_task(asyncio.Event().wait())
        driver = asyncio.create_task(drive_market_data(session, inbox, receiver))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            driver.cancel()
            with pytest.raises(asyncio.CancelledError):
                await driver
            with patch.object(ex, 'send') as send:
                release.set()
                assert await asyncio.to_thread(finished.wait, 1)
                send.assert_not_called()
            assert results == [None]
        finally:
            release.set()
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)
    asyncio.run(scenario())


def test_feed_replay_restores_announcement_pause_before_allowing_orders(tmp_path):
    ex, previous = prepared()
    strat = previous.strat
    strat.on_start(ex)
    ex.responses['/competitions/time']['fictional_time'] = '1788-05-26T10:01:00'
    messages = [{'type': 'storm_formed', 'round': 1, 'seq': 0}, weather(),
                {'type': 'announcement', 'seq': 2, 'symbols': ['PORT'], 'headline': 'Port closure'}]
    path = tmp_path / 'feed.jsonl'
    path.write_text('\n'.join(json.dumps({'type': 'news', 'message':
        {**m, 'time': '1788-05-26T10:00:00'}}) for m in messages))
    seen = set()
    year, rnd, count = replay_feed_log(str(path), ex, strat, seen)
    assert (year, rnd, count) == ('1788', 1, 3)
    assert strat.paused == {'PORT'}
    session = LiveSession(ex, strat, sync=9999, season_year=year, last_round=rnd, seen_seq=seen)
    session._news({'type': 'snapshot', 'last_seq': 2, 'round': 1, 'phase': 'storm'})
    with patch.object(ex, 'send', return_value={'order_id': 'ok', 'filled_quantity': 1}) as send:
        assert ex.place('PORT', 'buy', 1, 100) is None
        assert ex.place('ARCH', 'buy', 1, 100) is None
        assert ex.create('ARCH', 1) is False
        assert ex.place('GRID', 'buy', 1, 100) == 'ok'
        assert send.call_count == 1


def test_constituent_pause_cancels_resting_etf_orders():
    ex, session = prepared()
    session.strat.pause(['PORT'])
    ex.open_orders = [{'symbol': 'ARCH', 'side': 'buy', 'quantity': 5,
                       'filled_quantity': 0, 'order_id': 'resting'}]
    with patch.object(ex, 'send', return_value={}) as send:
        session.step([])
        assert send.call_args.args[:2] == ('DELETE', '/orders/all?symbol=ARCH')
        assert send.call_count == 1


def test_history_readiness_requires_complete_current_and_prior_storms():
    model = SeasonModel(CASE)
    assert not model.live_history_ready
    model.on_message(weather())
    assert model.live_history_ready
    model.on_message(weather(age=4, seq=3))      # one lost observation: interpolated
    assert model.live_history_ready
    model.on_message(weather(age=14, seq=8))     # four lost observations: too many
    assert not model.live_history_ready
    model = SeasonModel(CASE)
    model.on_message(weather(round=3))
    assert not model.live_history_ready


def test_short_weather_hole_is_interpolated_between_neighbours():
    model = SeasonModel(CASE)
    model.on_message(weather(age=0, seq=1))
    model.on_message({**weather(age=6, seq=4), 'x': 30, 'radius': 130})
    ages = [o['age'] for o in model.obs]
    assert ages == [0, 2, 4, 6]
    assert [o['x'] for o in model.obs] == [0, 10, 20, 30]
    assert [o['radius'] for o in model.obs] == [100, 110, 120, 130]
    assert all(o.get('_filled') for o in model.obs[1:3]) and 'seq' not in model.obs[1]
    assert model.outage_history_complete and model.live_history_ready


def test_a_reconnect_losing_two_messages_keeps_trading_eligible():
    ex, session = prepared()
    session._news(weather(age=2, seq=2))
    session._news(weather(age=8, seq=5))          # seqs 3 and 4 (ages 4 and 6) lost in a reconnect
    assert session.missing_seq == {3, 4}
    assert session.history_block_reason() is None
    assert [o['age'] for o in session.strat.model.obs] == [0, 2, 4, 6, 8]
    session._news(weather(age=10, seq=6))
    assert session.history_block_reason() is None


def test_more_than_six_lost_messages_block_until_a_new_season():
    ex, session = prepared()
    session._news(weather(age=2, seq=2))
    session._news({'type': 'advisory', 'round': 1, 'seq': 11, 'age': 2, 'source': 'wire', 'outlook': 'direct'})
    assert session.missing_seq == {3, 4, 5, 6, 7, 8, 9, 10}
    assert 'missing news history' in session.history_block_reason()
    session._news(weather(age=4, seq=3))          # a late message fills one hole: still too many
    assert session.missing_seq == {4, 5, 6, 7, 8, 9, 10}
    assert 'missing news history' in session.history_block_reason()
    session._news_season_changed('1789')          # only a new season clears the holes
    assert session.missing_seq == set() and session.news_complete


def test_a_lost_final_report_still_blocks_through_the_weather_gate():
    ex, session = prepared()
    model = session.strat.model
    for message in complete_season()[2:]:
        if message['type'] == 'damage_report' and message['round'] == 1:
            continue                               # the round-1 final report is the one lost message
        session._news(message)
    assert len(session.missing_seq) == 1 and session.news_complete
    assert 1 not in model.reported_rounds
    assert 'incomplete weather history' in session.history_block_reason()


def test_complete_recorded_season_remains_eligible():
    model = SeasonModel(CASE)
    for message in complete_season():
        model.on_message(message)
        if model.last_obs:
            assert model.live_history_ready
    assert model.live_history_ready


def test_full_season_session_accepts_checkpoints_in_every_round():
    ex = ScriptedExchange()
    strat = FairValueTrader()
    strat.on_start(ex)
    session = LiveSession(ex, strat, sync=9999)
    rounds = set()
    for message in complete_season():
        session._news(message)
        if strat.model.last_obs:
            rounds.add(strat.model.round)
            assert session.history_block_reason() is None
    assert rounds == {1, 2, 3}
    # A redundant checkpoint must keep a complete history eligible.
    session._news({'type': 'snapshot', 'round': 3, 'phase': 'done',
                   'last_seq': session.latest_seq})
    assert session.history_block_reason() is None


def test_feed_replay_keeps_only_the_latest_same_year_season(tmp_path):
    # The live exchange can run a warm-up season and the real season on the same fictional year; the testnet never
    # did (one year per season). Only the season after the last seq restart may be replayed.
    ex, previous = prepared()
    strat = previous.strat
    strat.on_start(ex)
    ex.responses['/competitions/time']['fictional_time'] = '1788-05-26T10:01:00'
    stale = [{'type': 'storm_formed', 'round': 1, 'seq': 0}, weather(),
             {'type': 'announcement', 'seq': 2, 'symbols': ['PORT'], 'headline': 'Port closure'}]
    stale += [{'type': 'storm', 'round': 1, 'seq': s, 'age': 2 * s, 'x': 480.0, 'y': 700.0, 'vx': 0.0, 'vy': -1.8,
               'radius': 80.0, 'intensity': 1.0} for s in range(3, 300)]
    current = [{'type': 'storm_formed', 'round': 1, 'seq': 0}, weather(), {**weather(), 'seq': 2, 'age': 4}]
    path = tmp_path / 'feed.jsonl'
    lines = [json.dumps({'type': 'news', 'message': {**m, 'time': '1788-05-26T10:00:00'}}) for m in stale + current]
    path.write_text('\n'.join(lines))
    seen = set()
    year, rnd, count = replay_feed_log(str(path), ex, strat, seen)
    assert (year, rnd, count) == ('1788', 1, 3)
    assert seen == {0, 1, 2}
    assert strat.paused == set()          # the stale season's announcement pause is not restored
    # only the current season's observations (ages 0 and 4, plus the interpolated age 2): no stale x=480 point
    assert [o['age'] for o in strat.model.obs] == [0, 2, 4] and all(o['x'] != 480.0 for o in strat.model.obs)


def _feed_log_with(tmp_path, messages, year='1788'):
    path = tmp_path / 'competition.jsonl'
    path.write_text(''.join(json.dumps({'type': 'news', 'message': {**m, 'time': f'{year}-05-26T10:00:00'}}) + '\n'
                            for m in messages))
    return path


def test_long_hole_restarts_only_when_the_recorder_has_every_lost_message(tmp_path):
    season = complete_season()
    ex = ScriptedExchange()
    ex.responses['/competitions/time']['fictional_time'] = '1788-05-26T10:00:00'
    ex.refresh()
    strat = FairValueTrader(warmup=0)
    strat.on_start(ex)
    restarts = []
    session = LiveSession(ex, strat, sync=9999, feed_log=str(_feed_log_with(tmp_path, season[:6])))
    session.restart = lambda: restarts.append(ex.t)
    ex.t0 = 0.
    for m in season[:3]:
        session._news(m)
    session._news(season[12])                     # seqs 3-11 lost: beyond the in-line repair
    assert 'missing news history' in session.history_block_reason()
    with patch('bot.live.time.monotonic', return_value=5.):
        session.step([])
    assert restarts == []                          # ten seconds of grace for late messages
    with patch('bot.live.time.monotonic', return_value=16.):
        session.step([])
    assert restarts == []                          # the recorder's file lacks seqs 6-11: a restart cannot help
    _feed_log_with(tmp_path, season[:13])
    with patch('bot.live.time.monotonic', return_value=40.), patch.object(ex, 'send', return_value={}):
        session.step([])
    assert restarts == [40.] and session.stopped.is_set()


def test_short_hole_or_no_feed_log_never_restarts(tmp_path):
    ex, session = prepared()
    session.restart = lambda: pytest.fail('restart without a feed log')
    session._news(weather(age=18, seq=10))        # seqs 2-9 lost, no feed log configured
    session.step([])
    session.feed_log = _feed_log_with(tmp_path, complete_season()[:12])
    session.restart = lambda: pytest.fail('restart within the grace period')
    session.step([])
    ex2, session2 = prepared()
    session2.feed_log = session.feed_log
    session2.restart = lambda: pytest.fail('restart for a repairable hole')
    session2._news(weather(age=8, seq=5))         # three lost observations: repaired in line
    ex2.t0 = 0.
    with patch('bot.live.time.monotonic', return_value=100.):
        session2.step([])
    assert session2.history_block_reason() is None
