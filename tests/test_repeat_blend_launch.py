"""Optional blend selection must reach the real model without account I/O."""
import asyncio
from types import SimpleNamespace
import sys

import pytest

from bot import live, practice
from test_live_startup import ColdExchange, arguments


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('launch selection tests must not access the network')
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    monkeypatch.setattr('socket.socket.connect', forbidden)


@pytest.mark.parametrize('launcher', ['practice', 'live'])
@pytest.mark.parametrize('enabled', [False, True])
def test_cli_switch_reaches_runner(tmp_path, monkeypatch, launcher, enabled):
    observed = {}

    async def capture(args, *unused):
        observed['enabled'] = args.repeat_prefix_blend

    if launcher == 'practice':
        module = practice
        argv = ['practice', '--out', str(tmp_path / 'out'), '--feed-log', 'unused']
        monkeypatch.setattr(module, 'practice', capture)
        monkeypatch.setattr(module, 'Journal', lambda *a: SimpleNamespace(stop=lambda reason: None))
        monkeypatch.setattr(module, 'finish', lambda journal: None)
    else:
        module = live
        argv = ['live', '--key', 'test-only']
        monkeypatch.setattr(module, 'run', capture)
    if enabled:
        argv.append('--repeat-prefix-blend')
    monkeypatch.setattr(sys, 'argv', argv)
    module.main()
    assert observed == {'enabled': enabled}


@pytest.mark.parametrize('launcher', ['practice', 'live'])
@pytest.mark.parametrize('selection', ['absent', False, True])
def test_launcher_constructs_fixed_blend(tmp_path, monkeypatch, launcher, selection):
    exchange = ColdExchange()
    exchange.responses['/positions'] = {'positions': []}
    exchange.responses['/system/bot-trading'] = {'mode': 'full'}
    args = arguments(tmp_path)
    if selection != 'absent':
        args.repeat_prefix_blend = selection
    observed = {}

    class HandoffComplete(Exception):
        pass

    def inspect_model(ex, trader, *unused, **kwargs):
        model = trader.model.ensemble
        observed.update(enabled=model.repeat_prefix, weight=model.repeat_weight,
                        strategy_identity=trader.competition_id,
                        account_identity=ex.competition_id)
        raise HandoffComplete

    monkeypatch.setattr(live, 'replay_feed_log', lambda *a: ('', 0, 0))
    if launcher == 'practice':
        key = tmp_path / 'test-key'
        key.write_text('test-only')
        args.key_file, args.url = str(key), 'http://example.invalid'
        journal = SimpleNamespace(event=lambda *a, **k: None)
        monkeypatch.setattr(practice, 'PracticeExchange', lambda *a, **k: exchange)
        monkeypatch.setattr(practice, 'PracticeSession', inspect_model)
        run = practice.practice(args, journal)
    else:
        monkeypatch.setattr(live, 'LiveSession', inspect_model)
        run = live.run_exchange(args, exchange)
    with pytest.raises(HandoffComplete):
        asyncio.run(run)
    enabled = selection is True
    assert observed == {'enabled': enabled, 'weight': .5 if enabled else 1.,
                        'strategy_identity': 'season-1', 'account_identity': 'season-1'}


@pytest.mark.parametrize('launcher', ['practice', 'live', 'live_run'])
@pytest.mark.parametrize('invalid', ['yes', 1, None])
def test_invalid_programmatic_selection_precedes_io(monkeypatch, launcher, invalid):
    args = SimpleNamespace(repeat_prefix_blend=invalid, nowcast=False)
    run = (practice.practice(args, object()) if launcher == 'practice' else
           live.run_exchange(args, object()) if launcher == 'live' else live.run(args))
    with pytest.raises(ValueError, match='repeat_prefix_blend must be a bool'):
        asyncio.run(run)


@pytest.mark.parametrize('direct', [False, True])
def test_nowcast_conflict_precedes_account_io(direct):
    args = SimpleNamespace(repeat_prefix_blend=True, nowcast=True)
    with pytest.raises(ValueError, match='requires the analog model'):
        asyncio.run(live.run(args) if direct else live.run_exchange(args, object()))


def test_cli_nowcast_conflict_precedes_runner(monkeypatch):
    def forbidden(*args):
        raise AssertionError('conflicting options must be rejected before run')
    monkeypatch.setattr(live, 'run', forbidden)
    monkeypatch.setattr(sys, 'argv', ['live', '--key', 'test-only', '--nowcast', '--repeat-prefix-blend'])
    with pytest.raises(SystemExit) as failure:
        live.main()
    assert failure.value.code == 2
