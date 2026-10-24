"""Evaluate newly closed public-market captures with a frozen offline strategy.

No exchange client, credentials, historical outcomes, or live order submission.
Every eligible receipt receives a result or a visible terminal failure.
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_observed_season import evaluate, observed_capture


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def row_hash(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, allow_nan=False).encode()).hexdigest()


def verify_sources(manifest):
    for name, expected in manifest['sources'].items():
        if file_hash(name) != expected:
            raise ValueError(f'frozen source changed: {name}')


def complete_lines(path):
    with Path(path).open() as source:
        for line in source:
            if not line.endswith('\n'):
                break
            yield json.loads(line)


def append_event(out, event):
    with (out / 'ledger.jsonl').open('a') as output:
        output.write(json.dumps({'written_at': time.time(), **event}, allow_nan=False) + '\n')


def save_json(path, result):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def summarize(result):
    rows = result['results']
    key = lambda r: (r['latency_seconds'], r['displayed_depth_fraction'],
                     r['basket_enabled'], r['reset_warmup_each_snapshot'])
    expected = {(lat, depth, basket, reset) for lat in (.25, 1., 3.)
                for depth in (1., .5) for basket in (False, True) for reset in (True, False)}
    if len(rows) != 24 or {key(r) for r in rows} != expected:
        raise ValueError('all 24 fixed scenarios required')
    profits = [r['simulated_settlement_pnl'] for r in rows]
    if not all(type(p) in (int, float) and math.isfinite(p) for p in profits):
        raise ValueError('finite scenario profits required')
    current = [r['simulated_settlement_pnl'] for r in rows if not r['reset_warmup_each_snapshot']]
    coverage = result.get('coverage', {})
    return {'scenarios': 24, 'negative_scenarios': sum(p < 0 for p in profits),
        'worst': min(profits), 'best': max(profits),
        'current_behavior_worst': min(current), 'current_behavior_best': max(current),
        'current_behavior_negative_scenarios': sum(p < 0 for p in current),
        'quote_path_completeness_proven': coverage.get('quote_path_completeness_proven', False),
        'recorded_disconnect_frames': coverage.get('recorded_disconnect_frames'),
        'disconnect_count_known': coverage.get('disconnect_count_known', False),
        'subscription_acknowledgements': len(coverage.get('subscription_acknowledgements', [])),
        'unusable_quotes': coverage.get('unusable_quotes')}


def validate_artifact(result, cid, year, fingerprint, manifest, start, until):
    worker = result.get('worker', {})
    if (result.get('competition_id') != cid or result.get('year') != year
            or result.get('evaluation') != 'fixed_observed_market_grid'
            or result.get('fraction') != .1
            or row_hash(result.get('official_receipt')) != fingerprint
            or worker.get('receipt_sha256') != fingerprint
            or worker.get('sources') != manifest['sources']
            or worker.get('start_at') != start or worker.get('until') != until):
        raise ValueError('artifact identity, bounds, receipt, or source mismatch')
    return summarize(result)


def process_once(observations, feed, out, case, manifest, start, until):
    verify_sources(manifest)
    ledger = out / 'ledger.jsonl'
    previous = {}
    if ledger.exists():
        if ledger.read_bytes() and not ledger.read_bytes().endswith(b'\n'):
            raise ValueError('incomplete worker ledger; preserve and inspect before restart')
        for row in complete_lines(ledger):
            if row.get('kind') in ('evaluated', 'failed'):
                cid = row['competition_id']
                if cid in previous:
                    raise ValueError('duplicate terminal ledger entry')
                if row['kind'] == 'evaluated':
                    path = out / f'{cid}.json'
                    if (row.get('artifact') != path.name or not path.is_file()
                            or file_hash(path) != row.get('artifact_sha256')):
                        raise ValueError(f'saved artifact missing or changed: {cid}')
                    validate_artifact(json.loads(path.read_text()), cid, row.get('year'),
                                      row['receipt_sha256'], manifest, start, until)
                previous[cid] = row
    events, seen = [], set()
    for receipt in complete_lines(observations):
        if receipt.get('kind') != 'settlement':
            continue
        at = receipt.get('at')
        if type(at) not in (int, float) or not math.isfinite(at):
            raise ValueError('invalid receipt timestamp')
        if not start <= at < until:
            continue
        cid = receipt.get('competition_id')
        if not isinstance(cid, str) or str(uuid.UUID(cid)) != cid:
            raise ValueError('canonical receipt UUID required')
        fingerprint = row_hash(receipt)
        if cid in previous:
            if previous[cid]['receipt_sha256'] != fingerprint:
                raise ValueError(f'receipt changed: {cid}')
            continue
        if cid in seen:
            raise ValueError(f'duplicate receipt: {cid}')
        seen.add(cid)
        verify_sources(manifest)
        path = out / f'{cid}.json'
        event = {'competition_id': cid, 'year': receipt.get('year'),
                 'receipt_at': at, 'receipt_sha256': fingerprint}
        try:
            orphan = None
            if path.exists():
                orphan = json.loads(path.read_text())
                validate_artifact(orphan, cid, receipt.get('year'), fingerprint,
                                  manifest, start, until)
            validated, frames, coverage = observed_capture(observations, feed, cid, case['limits'])
            result = evaluate(case, validated, frames, coverage)
            result['worker'] = {'receipt_sha256': fingerprint, 'sources': manifest['sources'],
                                'start_at': start, 'until': until}
            # Check before writing, including after the potentially long replay.
            verify_sources(manifest)
            validate_artifact(result, cid, receipt.get('year'), fingerprint, manifest, start, until)
            if orphan is not None:
                # A crash can leave a result without its terminal ledger row.
                # Reproduce it before certifying recovery; never trust it alone.
                if row_hash(orphan) != row_hash(result):
                    raise ValueError('orphan artifact differs from reproduced result')
            else:
                save_json(path, result)
            event.update(kind='evaluated', **summarize(result), artifact=path.name,
                         artifact_sha256=file_hash(path))
        except Exception as error:
            event.update(kind='failed', error=f'{type(error).__name__}: {error}')
        append_event(out, event)
        previous[cid] = event
        events.append(event)
    return events


def run_loop(observations, feed, out, case, manifest, start, until, once=False):
    while True:
        final_pass = time.time() >= until
        for event in process_once(observations, feed, out, case, manifest, start, until):
            print(json.dumps(event), flush=True)
        if once or final_pass:
            break
        time.sleep(min(30, max(0, until - time.time())))


def utc_timestamp(value):
    parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError('an explicit timezone is required')
    return parsed.timestamp()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--feed', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--start-at', type=utc_timestamp, required=True)
    parser.add_argument('--until', type=utc_timestamp, required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if not math.isfinite(args.start_at) or not args.start_at < args.until:
        parser.error('start must precede the stop time')
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        files = [*ROOT.glob('ctc/*.py'), *ROOT.glob('ctc/*.json'), *ROOT.glob('ctc/*.npz'),
            ROOT / 'bot/live.py', ROOT / 'data/case.json', Path(__file__),
            ROOT / 'scripts/replay_captured_market.py', ROOT / 'scripts/evaluate_observed_season.py',
            ROOT / 'scripts/observe_market_seasons.py']
        manifest = {'sources': {str(p): file_hash(p) for p in files},
            'git_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'start_at': args.start_at, 'until': args.until,
            'observations': str(args.observations.resolve()), 'feed': str(args.feed.resolve()),
            'limitation': 'Frozen counterfactual replay; no actual account profit attribution.'}
        saved = args.out / 'manifest.json'
        if saved.exists():
            if json.loads(saved.read_text()) != manifest:
                raise ValueError('restart manifest differs from frozen run')
        else:
            if any(p.name != 'worker.lock' for p in args.out.iterdir()):
                raise ValueError('new run requires an empty output directory')
            save_json(saved, manifest)
        case = json.loads((ROOT / 'data/case.json').read_text())
        append_event(args.out, {'kind': 'worker_started', 'manifest_sha256': file_hash(saved)})
        try:
            run_loop(args.observations, args.feed, args.out, case, manifest,
                     args.start_at, args.until, args.once)
        except Exception as error:
            append_event(args.out, {'kind': 'worker_failed', 'error': f'{type(error).__name__}: {error}'})
            raise
        finally:
            append_event(args.out, {'kind': 'worker_stopped'})


if __name__ == '__main__':
    main()
