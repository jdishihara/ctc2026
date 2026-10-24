"""Direct launcher must establish account identity before initializing/replaying."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from bot import live
from scripts.experiment_execution_costs import PARAMETERS
from test_execution import ScriptedExchange
from test_live_safety import complete_season


class ColdExchange(ScriptedExchange):
    def __init__(self):
        self.now = 0.
        super().__init__()
        self.dry_run = True
        self.responses['/competitions/time']['fictional_time'] = '1786-05-31T10:00:00'
        self.competition_id = None
        self.season_year = ''
        self.state_ready = self.market_open = self.reopened = False

    @property
    def t(self):
        return self.now


def arguments(tmp_path, feed_log=None, nowcast=False):
    return SimpleNamespace(**PARAMETERS, nowcast=nowcast, feed_log=feed_log,
                           ws=None, sync=3, control=str(tmp_path / 'commands'))


@pytest.mark.parametrize('nowcast', [False, True])
@pytest.mark.parametrize('replay', [False, True])
def test_direct_launcher_preserves_history_through_first_quotes(tmp_path, monkeypatch, nowcast, replay):
    exchange = ColdExchange()
    messages = [{**m, 'time': '1786-05-31T10:00:00'} for m in complete_season()]
    feed = tmp_path / 'feed.jsonl'
    feed.write_text(''.join(json.dumps({'type': 'news', 'message': m}) + '\n' for m in messages))
    original_session = live.LiveSession
    observed = {}

    class HandoffComplete(Exception):
        pass

    def inspect_handoff(ex, trader, *args, **kwargs):
        session = original_session(ex, trader, *args, **kwargs)
        if not replay:
            session.step([({'type': 'news', 'message': m}, ex.now) for m in messages])
        observed['reports_before'] = sorted(trader.model.reported_rounds)
        observed['strategy_id'] = trader.competition_id
        observed['account_id'] = ex.competition_id
        session._news(messages[-1])  # Repeated latest news establishes a live checkpoint.
        ex.now = 30.
        session.step([({'type': 'quote', 'symbol': s, 'bid': 99., 'ask': 100.}, ex.now)
                      for s in ex.symbols])
        observed['reports_after'] = sorted(trader.model.reported_rounds)
        observed['history_ready'] = trader.model.live_history_ready
        observed['history_reason'] = session.history_block_reason()
        raise HandoffComplete

    def no_network(*args, **kwargs):
        raise AssertionError('test must not access the network')

    monkeypatch.setattr(live, 'LiveSession', inspect_handoff)
    monkeypatch.setattr('urllib.request.urlopen', no_network)
    monkeypatch.setattr('socket.socket.connect', no_network)
    with pytest.raises(HandoffComplete):
        asyncio.run(live.run_exchange(arguments(tmp_path, str(feed) if replay else None, nowcast), exchange))
    assert observed['reports_before'] == [1, 2, 3]
    assert observed['reports_after'] == [1, 2, 3]
    assert observed['strategy_id'] == observed['account_id'] == 'season-1'
    assert observed['history_ready'] and observed['history_reason'] is None


@pytest.mark.parametrize('failure', ['unready', None, '', '   ', 42])
def test_direct_launcher_rejects_unusable_initial_account_before_replay(tmp_path, monkeypatch, failure):
    exchange = ColdExchange()
    if failure == 'unready':
        exchange.responses['/orders/open'] = TimeoutError('account unavailable')
    else:
        exchange.responses['/competitions/time']['competition_id'] = failure

    def forbidden_replay(*args, **kwargs):
        raise AssertionError('history must not replay against an uninitialized account')

    monkeypatch.setattr(live, 'replay_feed_log', forbidden_replay)
    with pytest.raises(RuntimeError, match='initial account snapshot'):
        asyncio.run(live.run_exchange(arguments(tmp_path, 'unused-feed'), exchange))
