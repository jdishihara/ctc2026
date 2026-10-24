import copy
import json

import pytest

from scripts.evaluate_observed_season import evaluate, observed_capture
from scripts.observe_market_seasons import FeedCoverage, official_receipt


def capture(tmp_path):
    frames = []
    def add(kind, **values):
        frames.append({'type': kind, 'received_at': len(frames) + 1., **values})
    def news(**message):
        add('news', message={'time': '1785-05-30T09:30:00', **message})
    for rnd in (1, 2, 3):
        news(type='snapshot', round=rnd, phase='pre_storm', last_seq=rnd - 2)
        add('quote', symbol='A', bid=10, ask=11, bid_size=5, ask_size=5)
        news(type='damage_report', round=rnd, stage='final', seq=rnd - 1)
        news(type='snapshot', round=rnd, phase='closed', last_seq=rnd - 1)
    feed = tmp_path / 'feed.jsonl'
    feed.write_text(''.join(json.dumps(f) + '\n' for f in frames))
    coverage = FeedCoverage(feed)
    coverage.poll()
    clock = {'competition_id': 'one', 'state': 'ready',
             'fictional_time': '1785-05-30T16:00:00'}
    receipt = official_receipt(clock, [{'symbol': 'A', 'settlement_active': True,
                                      'settlement_price': 12}], clock,
                               coverage.summary('1785'), ['A'])
    receipt['at'] = 13.
    observations = tmp_path / 'observations.jsonl'
    observations.write_text(json.dumps(receipt) + '\n')
    return observations, feed, receipt, frames


def save(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


def test_complete_observed_capture_has_no_live_profit_claim(tmp_path):
    observations, feed, expected, _ = capture(tmp_path)
    receipt, frames, coverage = observed_capture(observations, feed, 'one', ['A'])
    assert receipt == expected
    assert len(frames) == 12
    assert coverage['news_count'] == 3
    assert coverage['quote_count_by_round'] == {'1': {'A': 1}, '2': {'A': 1}, '3': {'A': 1}}
    assert 'pnl' not in receipt


def test_missing_disconnect_markers_do_not_prove_uninterrupted_capture(tmp_path):
    observations, feed, _, _ = capture(tmp_path)
    _, _, coverage = observed_capture(observations, feed, 'one', ['A'])
    assert coverage['recorded_disconnect_frames'] == 0
    assert coverage['disconnect_count_known'] is False
    assert 'disconnect_events' not in coverage


def test_subscription_after_season_start_is_disclosed_without_inventing_disconnect_time(tmp_path):
    observations, feed, _, frames = capture(tmp_path)
    acknowledgement = {'type': 'subscription_ack', 'received_at': 2.5}
    frames.insert(2, acknowledgement)
    save(feed, frames)
    _, selected, coverage = observed_capture(observations, feed, 'one', ['A'])
    assert coverage['subscription_acknowledgements'] == [
        {'at': 2.5, 'round': 1, 'seconds_since_previous_frame': .5}]
    assert coverage['recorded_disconnect_frames'] == 0
    assert coverage['disconnect_count_known'] is False
    assert acknowledgement not in selected


def test_explicit_disconnect_marker_is_counted_and_replayed(tmp_path):
    observations, feed, _, frames = capture(tmp_path)
    disconnect = {'type': 'disconnected', 'received_at': 2.5}
    frames.insert(2, disconnect)
    save(feed, frames)
    _, selected, coverage = observed_capture(observations, feed, 'one', ['A'])
    assert coverage['recorded_disconnect_frames'] == 1
    assert disconnect in selected


@pytest.mark.parametrize('change', ['running', 'different_id', 'different_year', 'missing_prices'])
def test_invalid_receipt_is_rejected_before_feed_is_read(tmp_path, change):
    observations, feed, receipt, _ = capture(tmp_path)
    if change == 'running':
        receipt['end_clock']['state'] = 'running'
    elif change == 'different_id':
        receipt['end_clock']['competition_id'] = 'two'
    elif change == 'different_year':
        receipt['year'] = '1784'
    else:
        receipt['prices'] = {}
    save(observations, [receipt])
    feed.unlink()
    with pytest.raises(ValueError):
        observed_capture(observations, feed, 'one', ['A'])


@pytest.mark.parametrize('change', ['missing_seq', 'advertised_gap', 'conflicting_seq', 'midseason_start'])
def test_capture_coverage_is_recomputed_instead_of_trusting_receipt(tmp_path, change):
    observations, feed, _, frames = capture(tmp_path)
    if change == 'missing_seq':
        frames.pop(6)
    elif change == 'advertised_gap':
        frames[-1]['message']['last_seq'] = 3
    elif change == 'conflicting_seq':
        duplicate = copy.deepcopy(frames[2])
        duplicate['received_at'] = 3.5
        duplicate['message']['changed'] = True
        frames.insert(3, duplicate)
    else:
        frames[0]['message']['phase'] = 'storm'
    save(feed, frames)
    with pytest.raises(ValueError):
        observed_capture(observations, feed, 'one', ['A'])


def test_round_without_quotes_cannot_be_claimed_as_complete_capture(tmp_path):
    observations, feed, _, frames = capture(tmp_path)
    frames.pop(5)
    save(feed, frames)
    with pytest.raises(ValueError, match='quotes'):
        observed_capture(observations, feed, 'one', ['A'])


def test_future_frames_and_partial_tail_are_not_used(tmp_path):
    observations, feed, _, frames = capture(tmp_path)
    later = copy.deepcopy(frames[2])
    later['received_at'] = 14.
    later['message']['seq'] = 99
    with feed.open('a') as output:
        output.write(json.dumps(later) + '\n{"partial":')
    _, selected, _ = observed_capture(observations, feed, 'one', ['A'])
    assert selected == frames


def test_duplicate_receipts_are_rejected(tmp_path):
    observations, feed, receipt, _ = capture(tmp_path)
    save(observations, [receipt, receipt])
    with pytest.raises(ValueError, match='one'):
        observed_capture(observations, feed, 'one', ['A'])


def test_fixed_grid_keeps_every_losing_result(tmp_path, monkeypatch):
    from scripts import evaluate_observed_season as module
    observations, feed, _, _ = capture(tmp_path)
    receipt, frames, coverage = observed_capture(observations, feed, 'one', ['A'])
    calls = []
    def losing_replay(case, frames, year, prices, fraction, latency, depth, basket, reset):
        calls.append((fraction, latency, depth, basket, reset))
        return {'simulated_settlement_pnl': -1.}
    monkeypatch.setattr(module, 'replay', losing_replay)
    result = evaluate({'limits': {'A': 20}}, receipt, frames, coverage)
    assert len(set(calls)) == 24
    assert {call[0] for call in calls} == {.1}
    assert len(result['results']) == 24
    assert all(row['simulated_settlement_pnl'] == -1 for row in result['results'])
    assert 'live_settlement_pnl' not in result
