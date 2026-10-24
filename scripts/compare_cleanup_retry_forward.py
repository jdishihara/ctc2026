"""Guarded fixed retry comparison on one later officially closed capture.

Each phase uses a separate process. Baseline must reproduce all 16 archived
supervised results and journals before the candidate phase can start.
"""
from __future__ import annotations

import argparse
import ast
import copy
from collections.abc import Mapping
from dataclasses import asdict
import hashlib
import importlib.util
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
FORWARD_DRIVER = 'c5c35a30e0c5f521f12324eec854f405b681b8c0'
JOURNALS = ['observations.json', 'actions.jsonl', 'status.json', 'final-receipt.json',
            'startup-feed.jsonl', 'result.json', 'run.lock']


def forward_grid(capture):
    if type(capture) is not int or capture not in (248, 249):
        raise ValueError('only predeclared captures 248 and 249 are eligible')
    return list(itertools.product([capture], [0., .05, .25, 1.], [1., .5], [False, True]))


def validate_forward_receipt(receipt, *, capture, symbols, now=None):
    from scripts.observe_market_seasons import official_receipt
    forward_grid(capture)
    if not isinstance(receipt, dict) or receipt.get('kind') != 'settlement':
        raise ValueError('an official settlement receipt is required')
    at = receipt.get('at')
    if (type(at) not in (int, float) or not math.isfinite(at)
            or not 1792837693. <= at < 1792843200.
            or at > (time.time() if now is None else now)):
        raise ValueError('receipt is outside the declared closed-capture window')
    prices, info = receipt.get('prices'), receipt.get('coverage')
    if (receipt.get('source') != 'read_only_market_observer'
            or receipt.get('year') != str(2027 - capture)
            or not isinstance(prices, dict) or not isinstance(info, dict)
            or not isinstance(receipt.get('clock'), dict)
            or not isinstance(receipt.get('end_clock'), dict)):
        raise ValueError('invalid official receipt identity or structure')
    count, last, advertised = (info.get(k) for k in ('seq_count', 'last_seq', 'advertised_last_seq'))
    first_at, last_at = info.get('first_at'), info.get('last_at')
    if (info.get('contiguous') is not True or info.get('conflicting_sequences') is not False
            or any(type(n) is not int for n in (count, last, advertised))
            or count <= 0 or last != advertised or count != last + 1
            or any(type(n) not in (int, float) or not math.isfinite(n) for n in (first_at, last_at))
            or not 0 < first_at <= last_at <= at):
        raise ValueError('incomplete or invalid official receipt coverage')
    rows = [dict(symbol=s, settlement_price=p, settlement_active=True) for s, p in prices.items()]
    try:
        validated = official_receipt(receipt['clock'], rows, receipt['end_clock'], info, symbols)
    except (KeyError, TypeError, AttributeError):
        validated = None
    if (validated is None or validated['year'] != receipt['year']
            or validated['competition_id'] != receipt.get('competition_id')):
        raise ValueError('matching complete ready clocks and settlement prices required')


def validate_upstream_metadata(metadata, summary, rows, capture, expected):
    grid = forward_grid(capture)
    if any(metadata.get(k) != v for k, v in expected.items()):
        raise ValueError('upstream full-supervisor provenance differs from frozen source')
    started, finished = metadata.get('started_at'), summary.get('finished_at')
    if (summary.get('runs') != 16 or summary.get('errors') != 0
            or summary.get('mismatches') != 0 or summary.get('changed_sources') != []
            or summary.get('forbidden_attempts', []) != []
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in (started, finished))
            or not 0 < started <= finished <= time.time()
            or len(rows) != 16 or len({row_key(r) for r in rows}) != 16
            or {row_key(r) for r in rows} != set(grid)
            or any(r.get('status') != 'ok' or r.get('errors') != []
                   or r.get('comparison_status') != 'supervised_after_verified_baseline' for r in rows)):
        raise ValueError('upstream completed full-supervisor phase is required')


def verify_upstream(spec, item, data, metadata, summary, rows, case, sources):
    root = Path(spec['forward_root'])
    driver = root / 'scripts/compare_practice_supervisor.py'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() == FORWARD_DRIVER
    assert driver.read_bytes() == subprocess.check_output(
        ['git', 'show', f'{FORWARD_DRIVER}:scripts/compare_practice_supervisor.py'], cwd=root)
    loader = importlib.util.spec_from_file_location('_frozen_forward_provenance', driver)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    runtime = module.verify_forward_runtime(root)
    upstream_spec_path = Path(item['forward_spec'])
    upstream_spec = json.loads(upstream_spec_path.read_text())
    assert metadata['spec'] == upstream_spec
    assert upstream_spec['reference_revision'] == module.FORWARD_REFERENCE_REVISION
    assert module.capture_numbers(upstream_spec, True) == [item['capture']]
    original = upstream_spec['captures'][0]
    assert original['competition_id'] == data['receipt']['competition_id']
    inputs = module.sealed_forward_inputs(original)
    from scripts.evaluate_observed_season import observed_capture
    from scripts.replay_serialized_client import PARAMETERS
    receipt, frames, coverage = observed_capture(*inputs, original['competition_id'], case['limits'])
    assert data['receipt'] == receipt and data['frames'] == frames
    reference = Path(upstream_spec['reference_root'])
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=reference, text=True).strip() == module.FORWARD_REFERENCE_REVISION
    reference_sources = {}
    for p in module.source_files(reference):
        relative = p.relative_to(reference).as_posix()
        assert p.read_bytes() == subprocess.check_output(
            ['git', 'show', f'{module.FORWARD_REFERENCE_REVISION}:{relative}'], cwd=reference)
        reference_sources[relative] = digest(p)
        sources.append(p)
    module.verify_forward_archive(original, receipt, frames, reference_sources, PARAMETERS,
                                  reference_revision=module.FORWARD_REFERENCE_REVISION)
    upstream_archive = Path(original['archive_results'])
    dependencies = module.source_files(root) + [root / 'bot/practice.py',
        root / 'scripts/replay_practice_supervisor.py', driver,
        root / 'docs/supervised-replay-plan.md', root / 'docs/practice-round-transition-plan.md',
        upstream_spec_path, root / 'docs/supervised-forward-plan.md', *inputs,
        upstream_archive, upstream_archive.parent / 'metadata.json', upstream_archive.parent / 'summary.json',
        *(Path(p) for p in runtime)]
    for p in dependencies:
        if p.is_relative_to(root):
            relative = p.relative_to(root).as_posix()
            assert p.read_bytes() == subprocess.check_output(
                ['git', 'show', f'{FORWARD_DRIVER}:{relative}'], cwd=root)
    expected = dict(phase='supervised', source_revision=FORWARD_DRIVER,
        source_sha256={str(p): digest(p) for p in dependencies}, spec=upstream_spec,
        grid=[list(x) for x in module.GRID], fraction=.1, loss_trigger=250., prior_pnl=0.,
        forward=True, driver_revision=FORWARD_DRIVER, driver_sha256=digest(driver),
        runtime_revision=FROZEN, runtime_sha256=runtime,
        forward_plan_sha256=digest(root / 'docs/supervised-forward-plan.md'),
        forward_plan_revision=FORWARD_DRIVER,
        captures=[dict(capture=item['capture'], competition_id=receipt['competition_id'], year=receipt['year'],
            coverage=coverage, receipt_sha256=value_hash(receipt), frames_sha256=value_hash(frames),
            archive_sha256=digest(upstream_archive), receipt_at=receipt['at'],
            first_at=frames[0]['received_at'], last_at=frames[-1]['received_at'], frame_count=len(frames))])
    validate_upstream_metadata(metadata, summary, rows, item['capture'], expected)
    sources.extend(dependencies)


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
    parser.add_argument('--capture', type=int, choices=[248, 249], required=True)
    args = parser.parse_args()
    GRID = forward_grid(args.capture)
    spec = json.loads(args.spec.read_text())
    assert [item['capture'] for item in spec['captures']] == [args.capture]
    frozen_root = Path(spec['baseline_root'])
    runtime_root = frozen_root if args.phase == 'baseline' else ROOT
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=frozen_root, text=True).strip() == FROZEN
    candidate_revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT)

    sources = [Path(__file__), ROOT / 'docs/cleanup-retry-window-plan.md',
               ROOT / 'docs/cleanup-retry-forward-plan.md', args.spec]
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
    assert runtime_changes == ['bot/practice.py'], runtime_changes

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
    assert Path(replay.__file__).resolve().parents[1] == runtime_root.resolve()

    tree = ast.parse((runtime_root / 'bot/practice.py').read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'reconcile_stop')
    loop = next(node for node in function.body if isinstance(node, ast.For)
                and isinstance(node.target, ast.Name) and node.target.id == 'attempt')
    pass_lines = loop.lineno, loop.end_lineno

    inputs, archives, archive_directories = {}, {}, {}
    case_definition = json.loads((runtime_root / 'data/case.json').read_text())
    for item in spec['captures']:
        capture = item['capture']
        cached, archive = Path(item['input']), Path(item['archive'])
        assert digest(cached) == item['input_sha256']
        for name in ('metadata.json', 'results.jsonl', 'summary.json'):
            assert digest(archive / name) == item['archive_sha256'][name]
            sources.append(archive / name)
        sources.append(cached)
        data = json.loads(cached.read_text())
        validate_forward_receipt(data['receipt'], capture=capture, symbols=case_definition['limits'])
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
        verify_upstream(spec, item, data, metadata, summary, rows, case_definition, sources)
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
    metadata = dict(phase=args.phase, started_at=time.time(), candidate_revision=candidate_revision,
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
            assert set(row['journal_sha256']) == set(JOURNALS + ['cleanup-profile.json', 'mutation-profile.json'])
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
            self.mutation_profile = []

        def request(self, *a, **kw):
            stack, cleanup_attempt = [], None
            if 'cleanup_request_index' in active:
                frame = sys._getframe(1)
                while frame:
                    if (frame.f_code.co_name == 'reconcile_stop'
                            and frame.f_code.co_filename.endswith('/bot/practice.py')
                            and pass_lines[0] < frame.f_lineno <= pass_lines[1]):
                        cleanup_attempt = frame.f_locals['attempt']
                    if frame.f_code.co_filename.endswith(('/bot/practice.py', '/bot/live.py')):
                        stack.append(dict(file=Path(frame.f_code.co_filename).name,
                                          function=frame.f_code.co_name, line=frame.f_lineno))
                    frame = frame.f_back
            response = super().request(*a, **kw)
            if 'cleanup_request_index' in active:
                self.cleanup_profile.append(dict(request=copy.deepcopy(self.requests[-1]), stack=stack,
                                                 cleanup_attempt=cleanup_attempt))
            request = self.requests[-1]
            if request['method'] in ('POST', 'DELETE'):
                now = request['started_at']
                count = sum(row['method'] in ('POST', 'DELETE') and row['started_at'] >= now - 60
                            for row in self.requests)
                self.mutation_profile.append(dict(request_index=len(self.requests) - 1,
                    started_at=now, method=request['method'], path=request['path'],
                    rolling_60s=count, cleanup_attempt=cleanup_attempt))
                enforce(count <= 180, 'whole-stream rolling mutation ceiling exceeded')
                if cleanup_attempt is not None and cleanup_attempt >= 5:
                    enforce(count <= 90, 'extra-pass shared rolling mutation ceiling exceeded')
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
                (directory / 'mutation-profile.json').write_text(json.dumps(server.mutation_profile, indent=2) + '\n')
                first_five = [item['request'] for item in server.cleanup_profile
                              if item['cleanup_attempt'] is not None and item['cleanup_attempt'] < 5]
                first_five_hash = value_hash(first_five)
                original = archives[setting]
                if args.phase == 'baseline':
                    assert result == {k: v for k, v in original.items() if k not in ('capture', 'comparison_status')}
                    for name in JOURNALS:
                        archived = archive_directories[capture] / directory.name / name
                        assert (directory / name).read_bytes() == archived.read_bytes(), name
                    comparison = 'exact_archive'
                else:
                    assert prefix == baseline_rows[setting]['pre_cleanup_trace']
                    assert first_five_hash == baseline_rows[setting]['first_five_requests_sha256']
                    for field in ['stop_reason', 'stop_at', 'stop_phase', 'stop_market_open',
                                  'monitor_started_at', 'monitor_detected_at', 'cleanup_started_at',
                                  'final_report_rounds', 'history_block_reason', 'prefix_messages', 'client_steps']:
                        assert result[field] == original[field], field
                    comparison = 'identical_before_cleanup'
                row.update(result, pre_cleanup_trace=prefix, comparison_status=comparison,
                           first_five_requests_sha256=first_five_hash,
                           maximum_rolling_mutations=max((item['rolling_60s'] for item in server.mutation_profile), default=0),
                           extra_pass_mutations=sum(item['cleanup_attempt'] is not None and item['cleanup_attempt'] >= 5
                                                    for item in server.mutation_profile),
                           journal_sha256={name: digest(directory / name)
                                           for name in JOURNALS + ['cleanup-profile.json', 'mutation-profile.json']})
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
