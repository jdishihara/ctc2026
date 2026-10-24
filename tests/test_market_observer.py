import copy
import io
import json

import pytest

from scripts.observe_market_seasons import FeedCoverage, MarketReader, official_receipt


def inputs():
    clock = {'competition_id': 'one', 'state': 'ready', 'fictional_time': '1785-05-30T16:00:00'}
    rows = [{'symbol': 'A', 'settlement_active': True, 'settlement_price': 42.0}]
    coverage = {'contiguous': True, 'conflicting_sequences': False, 'final_rounds': [1, 2, 3],
                'first_at': 10, 'last_at': 30, 'seq_count': 3, 'last_seq': 2}
    return clock, rows, copy.deepcopy(clock), coverage, ['A']


def test_observer_records_only_a_complete_closed_matching_season():
    args = inputs()
    receipt = official_receipt(*args)
    assert receipt['competition_id'] == 'one'
    assert receipt['prices'] == {'A': 42.0}
    assert receipt['source'] == 'read_only_market_observer'
    assert 'pnl' not in receipt


def test_observer_refuses_rollover_or_running_clock():
    args = inputs()
    args[2]['competition_id'] = 'two'
    assert official_receipt(*args) is None
    args = inputs()
    args[2]['state'] = 'running'
    assert official_receipt(*args) is None
    args[2].pop('state')
    assert official_receipt(*args) is None


def test_observer_refuses_incomplete_news_or_inactive_settlement():
    args = inputs()
    args[3]['contiguous'] = False
    assert official_receipt(*args) is None
    args = inputs()
    args[1][0]['settlement_active'] = False
    assert official_receipt(*args) is None


def test_advertised_missing_sequence_blocks_until_it_arrives(tmp_path):
    feed = tmp_path / 'feed.jsonl'
    def frame(message):
        return json.dumps({'type': 'news', 'received_at': 10, 'message':
                          {'time': '1785-05-30T16:00:00', **message}}) + '\n'
    feed.write_text(''.join(frame({'type': 'damage_report', 'stage': 'final', 'round': r,
                                  'seq': r - 1}) for r in (1, 2, 3))
                    + frame({'type': 'snapshot', 'last_seq': 3}))
    coverage = FeedCoverage(feed)
    coverage.poll()
    args = inputs()
    args = (*args[:3], coverage.summary('1785'), args[4])
    assert not args[3]['contiguous']
    assert official_receipt(*args) is None
    with feed.open('a') as output:
        output.write(frame({'type': 'track', 'seq': 3}))
    coverage.poll()
    assert coverage.summary('1785')['contiguous']


def test_deadline_is_rechecked_after_a_slow_request(tmp_path, monkeypatch):
    from scripts import observe_market_seasons as module
    key = tmp_path / 'fake-key'
    key.write_text('test-only')
    reader = MarketReader('https://example.invalid', key, deadline=101)
    now, calls = [100.], []
    monkeypatch.setattr(module.time, 'time', lambda: now[0])
    def response(request, timeout):
        calls.append((request.full_url, timeout))
        now[0] = 102
        return io.StringIO('{}')
    monkeypatch.setattr(module.urllib.request, 'urlopen', response)
    reader.get('/competitions/time')
    with pytest.raises(TimeoutError):
        reader.get('/competitions/current')
    assert len(calls) == 1
    assert calls[0][1] <= 1
