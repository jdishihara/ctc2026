"""Run the predeclared closed-capture comparison in three auditable phases.

reference: rerun the frozen core client and retain request/fill trace hashes.
baseline: require equality with every archived field and reference trace.
supervised: run production supervision only after the complete baseline gate.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
GRID = list(itertools.product([0., .05, .25, 1.], [1., .5], [False, True]))
FORWARD_RUNTIME_REVISION = 'cd3eb239bd7bad97b34f10a8f2bb0b2e1c0f5026'
FORWARD_REFERENCE_REVISION = '505a5ad2d5a6f81e7c711cb550871ce7aa7f3734'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def value_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def traces(server):
    return dict(request_trace_sha256=value_hash([
        {k: v for k, v in r.items() if k != 'response' or r['method'] != 'GET'} for r in server.requests]),
        fill_trace_sha256=value_hash([asdict(f) for f in server.market.fills]))


def key(row):
    return (row['capture'], row['rtt_seconds'], row['displayed_depth_fraction'], row['basket_enabled'])


def index_rows(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines()]
    indexed = {key(row): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError('duplicate comparison rows')
    return indexed


def completed_phase(path, phase, required):
    if path is None:
        raise ValueError(f'{phase} results required')
    try:
        rows = index_rows(path)
        metadata = json.loads((path.parent / 'metadata.json').read_text())
        summary = json.loads((path.parent / 'summary.json').read_text())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f'incomplete {phase} artifacts') from exc
    expected = 'matched_archive' if phase == 'reference' else 'matched_archive_and_trace'
    if (metadata.get('phase') != phase or summary.get('runs') != len(required)
            or summary.get('errors') != 0 or summary.get('mismatches') != 0
            or summary.get('changed_sources') != []
            or type(summary.get('finished_at')) not in (int, float)
            or not math.isfinite(summary['finished_at'])
            or summary.get('results_sha256') != digest(path) or set(rows) != required
            or any(r.get('status') != 'ok' or r.get('comparison_status') != expected for r in rows.values())):
        raise ValueError(f'{phase} did not complete with verified unchanged results')
    return rows, metadata


def same_captures(previous, current):
    fields = ['capture', 'competition_id', 'year', 'receipt_sha256', 'frames_sha256',
              'archive_sha256', 'receipt_at', 'first_at', 'last_at', 'frame_count']
    if len(previous) != len(current) or any(
            any(a.get(field) != b.get(field) for field in fields) for a, b in zip(previous, current)):
        raise ValueError('capture input changed between comparison phases')


def source_files(root):
    names = ['data/case.json', 'bot/live.py', 'bot/http_transport.py', 'bot/control.py',
        'scripts/replay_serialized_client.py', 'scripts/replay_captured_market.py',
        'scripts/evaluate_observed_season.py', 'scripts/observe_market_seasons.py',
        'scripts/experiment_execution_costs.py', 'docs/serialized-replay-plan.md',
        'docs/serialized-forward-plan.md']
    return sorted([*root.glob('ctc/*.py'), *root.glob('ctc/*.json'), *root.glob('ctc/*.npz'),
                   *(root / name for name in names)])


def capture_numbers(spec, forward):
    captures = [item['capture'] for item in spec['captures']]
    if not forward:
        if captures != [241, 242, 243, 244]:
            raise ValueError('the frozen comparison requires captures 241–244 in order')
    elif (len(captures) != 1 or type(captures[0]) is not int or not 245 <= captures[0] <= 600
          or spec['captures'][0].get('mode') != 'observed'):
        raise ValueError('forward comparison requires one observed capture numbered 245–600')
    return captures


def sealed_forward_inputs(item):
    paths = []
    for field in ('observations', 'feed'):
        path = Path(item[field])
        data = path.read_bytes()
        if (type(item.get(field + '_bytes')) is not int or len(data) != item[field + '_bytes']
                or not data.endswith(b'\n')
                or hashlib.sha256(data).hexdigest() != item.get(field + '_sha256')):
            raise ValueError(f'{field} is not the declared sealed complete-line input')
        paths.append(path)
    return paths


def forward_receipt_in_window(receipt):
    at = receipt.get('at')
    if type(at) not in (int, float) or not math.isfinite(at) or not 1792828815 <= at < 1792843200:
        raise ValueError('receipt lies outside the declared forward window')


def verify_forward_runtime(root):
    paths = [p for p in source_files(root) if p.relative_to(root).parts[0] != 'docs']
    paths += [root / 'bot/practice.py', root / 'scripts/replay_practice_supervisor.py']
    verified = {}
    for path in paths:
        relative = path.relative_to(root).as_posix()
        frozen = subprocess.check_output(['git', 'show', f'{FORWARD_RUNTIME_REVISION}:{relative}'], cwd=root)
        expected = hashlib.sha256(frozen).hexdigest()
        if digest(path) != expected:
            raise ValueError(f'forward runtime differs from reviewed correction: {relative}')
        verified[str(path)] = expected
    return verified


def verify_forward_archive(item, receipt, frames, reference_sources, parameters, *, reference_revision):
    path = Path(item['archive_results'])
    for name in ('results', 'metadata', 'summary'):
        artifact = path if name == 'results' else path.parent / (name + '.json')
        if digest(artifact) != item.get('archive_' + name + '_sha256'):
            raise ValueError('upstream archive bytes differ from the declared completed artifacts')
    metadata = json.loads((path.parent / 'metadata.json').read_text())
    summary = json.loads((path.parent / 'summary.json').read_text())
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    actual_grid = {(r['rtt_seconds'], r['displayed_depth_fraction'], r['basket_enabled']) for r in rows}
    expected = dict(mode='observed', competition_id=item['competition_id'], year=str(2027 - item['capture']),
        source_revision=reference_revision, source_sha256=reference_sources,
        receipt_sha256=value_hash(receipt), frames_sha256=value_hash(frames), official_receipt=receipt,
        frame_count=len(frames), first_at=frames[0]['received_at'], last_at=frames[-1]['received_at'],
        receipt_at=receipt['at'], fraction=.1, parameters=parameters,
        rtts=[0., .05, .25, 1.], depths=[1., .5], baskets=[False, True])
    if (summary.get('runs') != len(GRID) or summary.get('errors') != 0
            or type(summary.get('elapsed_seconds')) not in (int, float)
            or not math.isfinite(summary['elapsed_seconds']) or summary['elapsed_seconds'] < 0
            or len(rows) != len(GRID) or actual_grid != set(GRID)
            or any(row.get('status') != 'ok' for row in rows)
            or any(metadata.get(k) != v for k, v in expected.items())):
        raise ValueError('upstream archive completion, source, identity or input provenance failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['reference', 'baseline', 'supervised'], required=True)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reference-results', type=Path)
    parser.add_argument('--baseline-results', type=Path)
    parser.add_argument('--forward', action='store_true', help='evaluate one later closed capture under the fixed forward protocol')
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    captures = capture_numbers(spec, args.forward)
    driver_revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    runtime_hashes, forward_dependencies = {}, []
    if args.forward:
        if spec['reference_revision'] != FORWARD_REFERENCE_REVISION:
            raise ValueError('forward reference must remain at its declared frozen revision')
        reference_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'],
            cwd=spec['reference_root'], text=True).strip()
        if reference_head != FORWARD_REFERENCE_REVISION:
            raise ValueError('forward reference checkout revision changed')
        runtime_hashes = verify_forward_runtime(ROOT)
        forward_dependencies = [ROOT / 'docs/supervised-forward-plan.md']
        for item in spec['captures']:
            forward_dependencies += sealed_forward_inputs(item)
            archive = Path(item['archive_results'])
            forward_dependencies += [archive, archive.parent / 'metadata.json', archive.parent / 'summary.json']
    source_root = Path(spec['reference_root']) if args.phase == 'reference' else ROOT
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source_root, text=True).strip()
    if args.phase == 'reference' and revision != spec['reference_revision']:
        raise ValueError('reference revision changed')
    sys.path.insert(0, str(source_root))
    from scripts import replay_serialized_client as core
    if Path(core.__file__).resolve().parents[1] != source_root.resolve():
        raise ValueError('imported the wrong reference checkout')
    if args.phase != 'reference':
        from scripts import replay_practice_supervisor as supervised
    dependencies = source_files(source_root)
    if args.phase != 'reference':
        dependencies += [ROOT / 'bot/practice.py', ROOT / 'scripts/replay_practice_supervisor.py']
    dependencies += [Path(__file__), ROOT / 'docs/supervised-replay-plan.md',
                     ROOT / 'docs/practice-round-transition-plan.md', args.spec]
    dependencies += forward_dependencies
    if args.forward:
        dependencies += [Path(p) for p in runtime_hashes]
    source_hashes = {str(p): digest(p) for p in dependencies}
    required = {(capture, rtt, depth, basket) for capture in captures
                for rtt, depth, basket in GRID}
    references, predecessor = {}, None
    if args.phase == 'baseline':
        references, predecessor = completed_phase(args.reference_results, 'reference', required)
        if predecessor['source_revision'] != spec['reference_revision']:
            raise ValueError('reference metadata revision differs from declared frozen source')
    if args.phase == 'supervised':
        _, predecessor = completed_phase(args.baseline_results, 'baseline', required)
        if predecessor['source_revision'] != revision or predecessor['source_sha256'] != source_hashes:
            raise ValueError('supervised source differs from the accepted baseline source')
    if predecessor is not None:
        if predecessor['spec'] != spec or any(digest(name) != value for name, value in predecessor['source_sha256'].items()):
            raise ValueError('prerequisite source or declared inputs changed')
        if args.forward and (predecessor.get('forward') is not True
                             or predecessor.get('driver_revision') != driver_revision
                             or predecessor.get('runtime_sha256') != runtime_hashes):
            raise ValueError('forward driver or reviewed runtime changed between phases')
    args.out.mkdir(parents=True, exist_ok=False)
    metadata = dict(phase=args.phase, source_revision=revision, source_sha256=source_hashes,
        spec=spec, grid=GRID, fraction=.1, loss_trigger=250., prior_pnl=0., captures=[],
        reference_results_sha256=digest(args.reference_results) if args.reference_results else None,
        baseline_results_sha256=digest(args.baseline_results) if args.baseline_results else None,
        started_at=time.time())
    if args.forward:
        metadata.update(forward=True, driver_revision=driver_revision,
            driver_sha256=digest(__file__), runtime_revision=FORWARD_RUNTIME_REVISION,
            runtime_sha256=runtime_hashes,
            forward_plan_sha256=digest(ROOT / 'docs/supervised-forward-plan.md'),
            forward_plan_revision=subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
                'docs/supervised-forward-plan.md'], cwd=ROOT, text=True).strip())
    case = json.loads((source_root / 'data/case.json').read_text())
    loaded, archives = [], {}
    for item in spec['captures']:
        cid = item['competition_id']
        if item['mode'] == 'completed':
            _, trial, receipt, frames, count = core.confirmed_completed_capture(
                item['batch'], item['feed'], cid, case['limits'])
            year, coverage = trial['year'], dict(news_count=count)
        else:
            receipt, frames, coverage = core.observed_capture(item['observations'], item['feed'], cid, case['limits'])
            year = receipt['year']
        if year != str(2027 - item['capture']):
            raise ValueError('capture year does not match its declared historical identity')
        if not frames or type(receipt.get('at')) not in (int, float) or not math.isfinite(receipt['at']) or receipt['at'] < frames[-1]['received_at']:
            raise ValueError('official ready receipt must follow all captured frames')
        if args.forward:
            forward_receipt_in_window(receipt)
            reference_root = Path(spec['reference_root'])
            reference_sources = {str(p.relative_to(reference_root)): digest(p)
                                 for p in source_files(reference_root)}
            verify_forward_archive(item, receipt, frames, reference_sources, core.PARAMETERS,
                                   reference_revision=spec['reference_revision'])
        archived = [json.loads(line) for line in Path(item['archive_results']).read_text().splitlines()]
        by_setting = {(r['rtt_seconds'], r['displayed_depth_fraction'], r['basket_enabled']): r for r in archived}
        if set(by_setting) != set(GRID) or len(archived) != len(GRID):
            raise ValueError('archive does not contain exactly the fixed grid')
        archives.update({(item['capture'], *setting): row for setting, row in by_setting.items()})
        loaded.append((item, receipt, frames, year))
        metadata['captures'].append(dict(capture=item['capture'], competition_id=cid, year=year,
            coverage=coverage, receipt_sha256=value_hash(receipt), frames_sha256=value_hash(frames),
            archive_sha256=digest(item['archive_results']), receipt_at=receipt['at'],
            first_at=frames[0]['received_at'], last_at=frames[-1]['received_at'], frame_count=len(frames)))
    if predecessor is not None:
        same_captures(predecessor['captures'], metadata['captures'])
    (args.out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    rows = []
    with (args.out / 'results.jsonl').open('x') as output:
        for item, receipt, frames, year in loaded:
            for rtt, depth, basket in GRID:
                settings = dict(rtt=rtt, depth_scale=depth, basket=basket)
                k = (item['capture'], rtt, depth, basket)
                try:
                    if args.phase == 'reference':
                        servers = []
                        original = core.ReplayServer

                        class RecordingServer(original):
                            def __init__(self, *a, **kw):
                                super().__init__(*a, **kw)
                                servers.append(self)

                        with patch.object(core, 'ReplayServer', RecordingServer):
                            result = core.replay_client(case, frames, year, item['competition_id'], receipt['prices'], **settings)
                        trace = traces(servers[0])
                    elif args.phase == 'baseline':
                        result, trace = supervised.replay_baseline(case, frames, year, item['competition_id'], receipt['prices'], **settings)
                    else:
                        result = supervised.replay_supervised(case, frames, year, item['competition_id'], receipt['prices'],
                            receipt_at=receipt['at'], out=args.out / f"capture-{item['capture']}-{rtt}-{depth}-{int(basket)}", **settings)
                        trace = {}
                    row = dict(capture=item['capture'], **result, **trace)
                    if args.phase != 'supervised':
                        differences = [field for field in sorted(set(result) | set(archives[k])) if result.get(field) != archives[k].get(field)]
                        if args.phase == 'baseline':
                            differences += [field for field in trace if trace[field] != references[k].get(field)]
                        row['comparison_status'] = ('mismatch' if differences else
                            'matched_archive' if args.phase == 'reference' else 'matched_archive_and_trace')
                        row['different_fields'] = differences
                    else:
                        row['comparison_status'] = 'supervised_after_verified_baseline'
                except Exception as exc:
                    row = dict(capture=item['capture'], rtt_seconds=rtt, displayed_depth_fraction=depth,
                        basket_enabled=basket, status='error', comparison_status='error', error=f'{type(exc).__name__}: {exc}')
                output.write(json.dumps(row, allow_nan=False) + '\n')
                output.flush()
                rows.append(row)
                print(json.dumps(dict(run=len(rows), capture=item['capture'], setting=[rtt, depth, basket],
                    status=row['status'], comparison=row['comparison_status'])), flush=True)
    changed = [name for name, expected in source_hashes.items() if digest(name) != expected]
    report = dict(runs=len(rows), errors=sum(r['status'] != 'ok' for r in rows),
        mismatches=sum(r['comparison_status'] == 'mismatch' for r in rows),
        changed_sources=changed, finished_at=time.time(), results_sha256=digest(args.out / 'results.jsonl'))
    (args.out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    if changed:
        raise ValueError(f'source changed during comparison: {changed}')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
