"""A normal between-storm wait must not be confused with lost history."""
from unittest.mock import patch

import pytest

from bot import live
from ctc.valuation import SeasonModel
from test_live_safety import complete_season, weather
from test_practice import setup


def timed(message):
    return {**message, 'time': '1788-05-26T10:00:00'}


def step(session, *messages):
    session.step([({'type': 'news', 'message': timed(m)}, session.ex.t) for m in messages])


def attempted_prior_round(fixture, next_round):
    journal, ex, session, responses = fixture
    messages = complete_season()
    for message in messages:
        if message['round'] < next_round:
            session._news(timed(message))
    assert session.strat.model.live_history_ready
    assert session.strat.model.storm_reported
    assert session.news_complete
    journal.start_trial(ex)
    journal.trials[ex.competition_id]['attempt_count'] = 1
    ex.reopened = False
    upcoming = [m for m in messages if m['round'] == next_round]
    return journal, ex, session, upcoming


@pytest.mark.parametrize('next_round', [2, 3])
@pytest.mark.parametrize('combined', [False, True])
def test_valid_round_transition_waits_and_resumes_without_stopping(setup, next_round, combined):
    journal, ex, session, messages = attempted_prior_round(setup, next_round)
    formed, first = messages[:2]
    if combined:
        step(session, formed, first)
    else:
        step(session, formed)
        assert not session.strat.model.live_history_ready
        for _ in range(3):
            session.step([])
            assert journal.stop_reason is None
            assert not session.submission_allowed(('PORT',))
        step(session, first)
    assert journal.stop_reason is None
    assert session.strat.model.live_history_ready
    assert session.news_complete
    ex.quotes['PORT'], ex.quote_times['PORT'] = (99., 100.), ex.t
    assert session.submission_allowed(('PORT',))


def test_wait_keeps_resting_order_cancellation_and_order_conversion_vetoes(setup):
    journal, ex, session, messages = attempted_prior_round(setup, 2)
    ex.open_orders = [dict(order_id=1, symbol='PORT', side='buy', quantity=1, filled_quantity=0)]
    journal.owned[ex.competition_id] = {1}
    def cancel(symbol=None):
        ex.open_orders = []
        return True
    with patch.object(ex, 'cancel_all', side_effect=cancel) as cancel_all, \
            patch.object(live.LiveExchange, 'send') as send:
        step(session, messages[0])
        assert journal.stop_reason is None
        cancel_all.assert_called_once()
        assert ex.place('PORT', 'buy', 1, 100.) is None
        assert not ex.create('ARCH', 1)
        assert not ex.redeem('ARCH', 1)
        send.assert_not_called()


@pytest.mark.parametrize('retransmission', ['same_formation', 'old_round', 'retired_year'])
def test_ignored_retransmissions_preserve_a_valid_wait(setup, retransmission):
    journal, ex, session, messages = attempted_prior_round(setup, 2)
    formed, first = messages[:2]
    step(session, formed)
    assert journal.stop_reason is None
    if retransmission == 'same_formation':
        step(session, formed)
    elif retransmission == 'old_round':
        step(session, complete_season()[0])
    else:
        session.retired_years.add('1787')
        session._news({**formed, 'seq': session.latest_seq + 1, 'time': '1787-01-01T00:00:00'})
    session.step([])
    assert journal.stop_reason is None
    step(session, first)
    assert journal.stop_reason is None and session.strat.model.live_history_ready


@pytest.mark.parametrize('kind', ['duplicate', 'restart', 'skip'])
@pytest.mark.parametrize('same_batch_weather', [False, True])
def test_invalid_new_formation_cannot_be_hidden_by_later_weather(setup, kind, same_batch_weather):
    journal, ex, session, messages = attempted_prior_round(setup, 2)
    step(session, *messages[:2])  # Initially valid, even in the old implementation.
    assert journal.stop_reason is None
    rnd = {'duplicate': 2, 'restart': 1, 'skip': 3}[kind]
    seq = session.latest_seq + 1
    bad = dict(type='storm_formed', round=rnd, seq=seq)
    first = weather(age=0, round=rnd, seq=seq + 1)
    step(session, *([bad, first] if same_batch_weather else [bad]))
    assert journal.stop_reason is not None
    reason = journal.stop_reason
    if not same_batch_weather:
        step(session, first)
    assert journal.stop_reason == reason
    assert not session.submission_allowed(('PORT',))


@pytest.mark.parametrize('corruption', ['news_gap', 'missing_report', 'initial_age_gap', 'later_weather_gap'])
def test_real_history_corruption_still_stops_and_cannot_recover(setup, corruption):
    journal, ex, session, messages = attempted_prior_round(setup, 2)
    formed, first = messages[:2]
    if corruption == 'missing_report':
        session.strat.model.reported_rounds.discard(1)
        session.strat.model.storm_reported = False
        step(session, formed, first)
    elif corruption == 'news_gap':
        step(session, {**formed, 'seq': formed['seq'] + 1})
    elif corruption == 'initial_age_gap':
        step(session, formed, {**first, 'age': 2})
    else:
        step(session, formed, first)
        step(session, weather(age=4, round=2, seq=session.latest_seq + 1))
    assert journal.stop_reason is not None
    reason = journal.stop_reason
    step(session, weather(age=0, round=2, seq=session.latest_seq + 1))
    assert journal.stop_reason == reason
    assert not session.submission_allowed(('PORT',))


@pytest.mark.parametrize('identity', ['model', 'competition', 'account_year', 'news_year'])
def test_wait_cannot_transfer_to_different_model_or_account(setup, identity):
    journal, ex, session, messages = attempted_prior_round(setup, 2)
    step(session, messages[0])
    assert journal.stop_reason is None
    if identity == 'model':
        session.strat.model = SeasonModel(ex.case)
    elif identity == 'competition':
        ex.competition_id = 'different'
    elif identity == 'account_year':
        ex.season_year = '1787'
    else:
        session.season_year = '1787'
    session.step([])
    assert journal.stop_reason is not None
    assert not session.submission_allowed(('PORT',))


@pytest.mark.parametrize('identity', ['account_year', 'session_competition', 'missing_year'])
def test_disagreeing_or_unknown_identity_cannot_start_waiting(setup, identity):
    journal, ex, session, messages = attempted_prior_round(setup, 2)
    if identity == 'account_year':
        ex.season_year = '1787'
    elif identity == 'session_competition':
        session.competition_id = 'different'
    else:
        ex.season_year = ''
    session._news(timed(messages[0]))
    assert not session._valid_weather_wait()
    assert journal.stop_reason is not None
    assert not session.submission_allowed(('PORT',))


@pytest.mark.parametrize('combined', [False, True])
def test_future_final_report_cannot_qualify_for_next_round_wait(setup, combined):
    journal, ex, session, messages = attempted_prior_round(setup, 2)
    future_report = next(m for m in messages if m['type'] == 'damage_report' and m['stage'] == 'final')
    session._news(timed({**future_report, 'seq': session.latest_seq + 1}))
    assert session.strat.model.reported_rounds == {1, 2}
    formed = {**messages[0], 'seq': session.latest_seq + 1}
    first = {**messages[1], 'seq': session.latest_seq + 2}
    step(session, *([formed, first] if combined else [formed]))
    assert journal.stop_reason is not None
    reason = journal.stop_reason
    if not combined:
        step(session, first)
    assert journal.stop_reason == reason
    assert not session.submission_allowed(('PORT',))


def test_resuming_after_age_zero_preserves_pending_news_stale_quote_and_loss_guards(setup):
    journal, ex, session, messages = attempted_prior_round(setup, 2)
    step(session, messages[0])
    assert journal.stop_reason is None
    step(session, messages[1])
    ex.quotes['PORT'], ex.quote_times['PORT'] = (99., 100.), ex.t
    assert session.submission_allowed(('PORT',))
    session.pending_news.set()
    assert not session.submission_allowed(('PORT',))
    session.pending_news.clear()
    ex.quote_times['PORT'] = ex.t - 10
    assert not session.submission_allowed(('PORT',))
    ex.quote_times['PORT'] = ex.t
    journal.trials[ex.competition_id]['last_pnl'] = -250
    journal.check_loss()
    assert not session.submission_allowed(('PORT',))
