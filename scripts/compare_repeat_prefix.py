"""Guarded offline comparison for optional recognition of repeated weather prefixes.

Each phase uses a separate process. Baseline must reproduce all 96 archived
supervised results and journals before the candidate phase can start.
"""
from __future__ import annotations

import argparse
import copy
from collections.abc import Mapping
from dataclasses import asdict
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FROZEN = 'cd3eb239bd7bad97b34f10a8f2bb0b2e1c0f5026'
GRID = list(itertools.product(range(241, 247), [0., .05, .25, 1.], [1., .5], [False, True]))
JOURNALS = ['observations.json', 'actions.jsonl', 'status.json', 'final-receipt.json',
            'startup-feed.jsonl', 'result.json', 'run.lock']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def value_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def runtime_files(root):
    names = ['data/case.json', 'bot/live.py', 'bot/http_transport.py', 'bot/control.py',
             'bot/practice.py', 'scripts/replay_practice_supervisor.py',
             'scripts/replay_serialized_client.py', 'scripts/replay_captured_market.py',
             'scripts/evaluate_observed_season.py', 'scripts/observe_market_seasons.py',
             'scripts/experiment_execution_costs.py']
    return sorted([*root.glob('ctc/*.py'), *root.glob('ctc/*.json'), *root.glob('ctc/*.npz'),
                   *(root / name for name in names)])


def row_key(row):
    return row['capture'], row['rtt_seconds'], row['displayed_depth_fraction'], row['basket_enabled']


def main():
    if not __debug__:
        raise RuntimeError('comparison requires Python assertions enabled; remove -O/PYTHONOPTIMIZE')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['baseline', 'candidate'], required=True)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    assert [item['capture'] for item in spec['captures']] == list(range(241, 247))
    frozen_root = Path(spec['baseline_root'])
    runtime_root = frozen_root if args.phase == 'baseline' else ROOT
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=frozen_root, text=True).strip() == FROZEN
    candidate_revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT)

    sources = [Path(__file__), ROOT / 'docs/repeat-prefix-plan.md', args.spec]
    runtime_changes = []
    for base in runtime_files(frozen_root):
        relative = base.relative_to(frozen_root).as_posix()
        original = subprocess.check_output(['git', 'show', f'{FROZEN}:{relative}'], cwd=frozen_root)
        assert hashlib.sha256(original).hexdigest() == digest(base), relative
        candidate = ROOT / relative
        committed = subprocess.check_output(['git', 'show', f'{candidate_revision}:{relative}'], cwd=ROOT)
        assert committed == candidate.read_bytes(), relative
        if original != committed:
            runtime_changes.append(relative)
        sources.extend([base, candidate])
    assert runtime_changes == ['ctc/analog.py'], runtime_changes

    forbidden = []
    def audit(event, event_args):
        if event in ('socket.connect', 'socket.getaddrinfo', 'socket.bind'):
            forbidden.append(event)
            raise RuntimeError('offline comparison forbids external network')
        if event == 'open' and isinstance(event_args[0], (str, bytes, os.PathLike)):
            name = os.fsdecode(event_args[0]).lower()
            if '.botkey' in name or '/.env' in name or '/data/history/' in name or 'credentials' in name:
                forbidden.append(name)
                raise RuntimeError('offline comparison forbids credentials and downloaded history')
    sys.addaudithook(audit)
    sys.path.insert(0, str(runtime_root))
    from scripts import replay_practice_supervisor as replay
    from bot import practice
    from ctc.strategies import FairValueTrader
    from ctc.analog import AnalogEnsemble
    assert Path(replay.__file__).resolve().parents[1] == runtime_root.resolve()

    inputs, archives, archive_directories = {}, {}, {}
    for item in spec['captures']:
        capture = item['capture']
        cached, archive = Path(item['input']), Path(item['archive'])
        assert digest(cached) == item['input_sha256']
        for name in ('metadata.json', 'results.jsonl', 'summary.json'):
            assert digest(archive / name) == item['archive_sha256'][name]
            sources.append(archive / name)
        sources.append(cached)
        data = json.loads(cached.read_text())
        metadata = json.loads((archive / 'metadata.json').read_text())
        summary = json.loads((archive / 'summary.json').read_text())
        assert summary['errors'] == summary['mismatches'] == 0 and summary['changed_sources'] == []
        assert summary['results_sha256'] == digest(archive / 'results.jsonl')
        selected = next(x for x in metadata['captures'] if x['capture'] == capture)
        assert value_hash(data['frames']) == selected['frames_sha256']
        assert value_hash(data['receipt']) == selected['receipt_sha256']
        assert data['receipt']['competition_id'] == selected['competition_id']
        inputs[capture] = data
        archive_directories[capture] = archive
        rows = [json.loads(line) for line in (archive / 'results.jsonl').read_text().splitlines()]
        for row in rows:
            if row['capture'] == capture:
                assert row_key(row) not in archives
                archives[row_key(row)] = row
    assert set(archives) == set(GRID)
    for (capture, rtt, depth, basket) in archives:
        directory = archive_directories[capture] / f'capture-{capture}-{rtt}-{depth}-{int(basket)}'
        sources.extend(directory / name for name in JOURNALS)
    sources = sorted(set(sources))
    source_hashes = {str(p): digest(p) for p in sources}
    metadata = dict(phase=args.phase, repeat_prefix_enabled=args.phase == 'candidate',
                    started_at=time.time(), candidate_revision=candidate_revision,
                    baseline_revision=FROZEN, runtime_changes=runtime_changes, spec=spec,
                    source_sha256=source_hashes, grid=GRID)
    baseline_rows = {}
    baseline_hashes = {}
    if args.phase == 'candidate':
        assert args.baseline is not None
        prior = json.loads((args.baseline / 'metadata.json').read_text())
        summary = json.loads((args.baseline / 'summary.json').read_text())
        assert prior['phase'] == 'baseline' and prior['source_sha256'] == source_hashes and prior['spec'] == spec
        assert prior['candidate_revision'] == candidate_revision
        assert summary['runs'] == len(GRID) and summary['errors'] == 0 and summary['changed_sources'] == []
        assert summary['forbidden_attempts'] == []
        assert type(summary.get('finished_at')) in (int, float) and math.isfinite(summary['finished_at'])
        assert summary['finished_at'] >= prior['started_at']
        assert summary['results_sha256'] == digest(args.baseline / 'results.jsonl')
        rows = [json.loads(line) for line in (args.baseline / 'results.jsonl').read_text().splitlines()]
        assert len(rows) == len(GRID)
        baseline_rows = {row_key(row): row for row in rows}
        assert len(baseline_rows) == len(GRID) and set(baseline_rows) == set(GRID)
        assert all(row['status'] == 'ok' and not row.get('errors')
                   and row['comparison_status'] == 'exact_archive' for row in baseline_rows.values())
        for (capture, rtt, depth, basket), row in baseline_rows.items():
            directory = args.baseline / f'capture-{capture}-{rtt}-{depth}-{int(basket)}'
            assert set(row['journal_sha256']) == set(JOURNALS + ['cleanup-profile.json', 'repeat-profile.json'])
            for name, expected in row['journal_sha256'].items():
                path = directory / name
                assert digest(path) == expected
                baseline_hashes[str(path)] = expected
        for name in ('metadata.json', 'results.jsonl', 'summary.json'):
            path = args.baseline / name
            baseline_hashes[str(path)] = digest(path)
        metadata['baseline_results_sha256'] = summary['results_sha256']
        metadata['baseline_artifact_sha256'] = baseline_hashes

    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    case = json.loads((runtime_root / 'data/case.json').read_text())
    active = {}
    OriginalServer = replay.PracticeReplayServer
    OriginalSession = practice.PracticeSession
    original_finish = practice.finish
    original_quotes = FairValueTrader.on_quotes
    original_weights = AnalogEnsemble.weights
    original_send = replay.ServerTransport.send

    def enforce(condition, message):
        if not condition:
            # Production code catches cleanup and refresh errors. A guard
            # violation must also latch on the replay server so it cannot be
            # mistaken for an ordinary attention outcome by that catch path.
            exc = AssertionError(message)
            active['server'].latch(exc)
            raise exc

    class RecordingServer(OriginalServer):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            active['server'] = self
            self.cleanup_profile = []

        def request(self, *a, **kw):
            stack = []
            if 'cleanup_request_index' in active:
                frame = sys._getframe(1)
                while frame:
                    if frame.f_code.co_filename.endswith(('/bot/practice.py', '/bot/live.py')):
                        stack.append(dict(file=Path(frame.f_code.co_filename).name,
                                          function=frame.f_code.co_name, line=frame.f_lineno))
                    frame = frame.f_back
            response = super().request(*a, **kw)
            if 'cleanup_request_index' in active:
                self.cleanup_profile.append(dict(request=copy.deepcopy(self.requests[-1]), stack=stack))
            return response

    class RecordingSession(OriginalSession):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            active['session'] = self

    class GuardedSettlement(Mapping):
        def __init__(self, values):
            self._prices = dict(values)

        def _check(self):
            server = active['server']
            enforce(server.terminal and not server.market.market_open and server.now >= server.settlement_available_at,
                    'settlement accessed before terminal receipt availability')
        def __getitem__(self, key):
            self._check(); return self._prices[key]
        def __iter__(self):
            return iter(self._prices)
        def __len__(self):
            return len(self._prices)
        def copy(self):
            self._check(); return dict(self)
        def __copy__(self):
            return self.copy()
        def __deepcopy__(self, memo):
            self._check(); return GuardedSettlement(dict(self))

    def checked_finish(journal):
        server = active['server']
        active['cleanup_request_index'] = len(server.requests)
        active['cleanup_fill_index'] = len(server.market.fills)
        return original_finish(journal)

    def checked_quotes(strategy, exchange):
        enforce(strategy.competition_id == exchange.competition_id and strategy.competition_id,
                'quote callback identity mismatch')
        model = strategy.model
        reports, ready = set(model.reported_rounds), model.live_history_ready
        result = original_quotes(strategy, exchange)
        enforce(strategy.model is model and model.reported_rounds == reports and model.live_history_ready == ready,
                'quote callback changed news history')
        return result

    def recorded_weights(ensemble, obs, official, wire, adv=None):
        result = original_weights(ensemble, obs, official, wire, adv)
        profile = active.setdefault('recognition', dict(calls=0, recognized=0, rows={}))
        profile['calls'] += 1
        match = getattr(ensemble, 'repeat_match', None)
        if match is not None:
            profile['recognized'] += 1
            item = profile['rows'].setdefault(str(match), dict(calls=0, first_age=obs[-1]['age'], last_age=obs[-1]['age']))
            item['calls'] += 1
            item['last_age'] = obs[-1]['age']
        return result

    def checked_send(exchange, method, path, body=None):
        if method == 'POST' and isinstance(exchange, replay.OfflinePracticeExchange):
            session = active['session']
            enforce(not session._valid_weather_wait() and session.strat.model.live_history_ready,
                    'strategy submission without ready history')
            enforce(session.competition_id == exchange.competition_id == session.strat.competition_id,
                    'strategy submission identity mismatch')
        if method == 'POST' and isinstance(exchange, replay.OfflineCleanupExchange):
            quantity = exchange.position[body['symbol']]
            enforce(exchange.state_ready and exchange.market_open and not exchange.open_orders,
                    'cleanup submission with unreconciled, closed or working-order account')
            enforce(exchange.expected_id == exchange.competition_id, 'cleanup submission identity mismatch')
            enforce(body['side'] == ('sell' if quantity > 0 else 'buy')
                    and 0 < body['quantity'] <= abs(quantity), 'cleanup submission is not reduction-only')
        return original_send(exchange, method, path, body)

    results = []
    with patch.object(replay, 'PracticeReplayServer', RecordingServer), \
         patch.object(practice, 'PracticeSession', RecordingSession), \
         patch.object(practice, 'finish', checked_finish), \
         patch.object(FairValueTrader, 'on_quotes', checked_quotes), \
         patch.object(AnalogEnsemble, 'weights', recorded_weights), \
         patch.dict(replay.PARAMETERS, {'repeat_prefix': True} if args.phase == 'candidate' else {}), \
         patch.object(replay.ServerTransport, 'send', checked_send):
        for capture, rtt, depth, basket in GRID:
            active.clear()
            data = inputs[capture]
            receipt = data['receipt']
            directory = args.out / f'capture-{capture}-{rtt}-{depth}-{int(basket)}'
            setting = capture, rtt, depth, basket
            row = dict(capture=capture, rtt_seconds=rtt, displayed_depth_fraction=depth, basket_enabled=basket)
            try:
                result = replay.replay_supervised(case, data['frames'], str(2027 - capture),
                    receipt['competition_id'], GuardedSettlement(receipt['prices']), receipt_at=receipt['at'],
                    out=directory, rtt=rtt, depth_scale=depth, basket=basket)
                assert result['status'] == 'ok' and not result['errors']
                server = active['server']
                assert not server.fatal_errors
                prefix = dict(requests_sha256=value_hash(server.requests[:active['cleanup_request_index']]),
                              fills_sha256=value_hash([asdict(f) for f in server.market.fills[:active['cleanup_fill_index']]]))
                (directory / 'cleanup-profile.json').write_text(json.dumps(server.cleanup_profile, indent=2) + '\n')
                profile = active.get('recognition', dict(calls=0, recognized=0, rows={}))
                (directory / 'repeat-profile.json').write_text(json.dumps(profile, indent=2) + '\n')
                original = archives[setting]
                if args.phase == 'baseline':
                    assert result == {k: v for k, v in original.items() if k not in ('capture', 'comparison_status')}
                    for name in JOURNALS:
                        archived = archive_directories[capture] / directory.name / name
                        assert (directory / name).read_bytes() == archived.read_bytes(), name
                    comparison = 'exact_archive'
                else:
                    comparison = 'candidate_evaluated'
                row.update(result, pre_cleanup_trace=prefix, comparison_status=comparison, repeat_profile=profile,
                           journal_sha256={name: digest(directory / name)
                                           for name in JOURNALS + ['cleanup-profile.json', 'repeat-profile.json']})
            except Exception as exc:
                row.update(status='error', comparison_status='failed', diagnostic_error=f'{type(exc).__name__}: {exc}')
            results.append(row)
            with (args.out / 'results.jsonl').open('a') as stream:
                stream.write(json.dumps(row, allow_nan=False) + '\n')
            print(json.dumps(dict(setting=setting, status=row['status'], comparison=row['comparison_status'],
                                  error=row.get('diagnostic_error'))), flush=True)
    changed = [path for path, expected in source_hashes.items() if digest(path) != expected]
    changed.extend(path for path, expected in baseline_hashes.items() if digest(path) != expected)
    summary = dict(runs=len(results), errors=sum(row['status'] != 'ok' for row in results),
                   changed_sources=changed, forbidden_attempts=forbidden, finished_at=time.time(),
                   results_sha256=digest(args.out / 'results.jsonl'))
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
    if summary['errors'] or changed or forbidden:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
