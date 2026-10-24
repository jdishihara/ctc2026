"""Check already-closed captured storm tracks against the fitted analog library.

This is an overlap audit, not a replay, retraining job, or forecast. It reads
only the five previously sealed closed inputs and the existing model artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

SPEC_SHA = '8d08de8cca753d3333f141a0a462ce2f24914ab366cc0cdcf27ed87e0845fc6f'
LIBRARY_SHA = '22694387c3b612f5c20853feb9143e1bf8b8f5722a845da8ed584ab1b30bdf09'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if not __debug__:
        raise RuntimeError('audit requires Python assertions')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    forbidden = []

    def audit(event, event_args):
        if event in ('socket.connect', 'socket.getaddrinfo', 'socket.bind'):
            forbidden.append(event)
            raise RuntimeError('overlap audit forbids network access')
        if event == 'open' and isinstance(event_args[0], (str, bytes)):
            name = str(event_args[0]).lower()
            if any(word in name for word in ('.botkey', '/.env', '/data/history/', 'credentials')):
                forbidden.append(name)
                raise RuntimeError('overlap audit forbids credentials and downloaded history')
    sys.addaudithook(audit)

    assert digest(args.spec) == SPEC_SHA
    assert digest(args.library) == LIBRARY_SHA
    spec = json.loads(args.spec.read_text())
    assert [item['capture'] for item in spec['captures']] == list(range(241, 246))
    sources = {str(args.spec): SPEC_SHA, str(args.library): LIBRARY_SHA,
               str(Path(__file__).resolve()): digest(__file__)}
    with np.load(args.library, allow_pickle=False) as library:
        tracks = library['tracks'].copy()
    assert tracks.shape == (1350, 241, 4) and np.isfinite(tracks).all()
    results = []
    for item in spec['captures']:
        capture = item['capture']
        path = args.inputs / f'{capture}.json'
        assert digest(path) == item['input_sha256']
        sources[str(path)] = item['input_sha256']
        data = json.loads(path.read_text())
        receipt, frames = data['receipt'], data['frames']
        assert receipt['clock']['state'] == 'ready'
        assert receipt['clock']['competition_id'] == receipt['competition_id']
        assert receipt['at'] >= frames[-1]['received_at']
        if 'end_clock' in receipt:
            assert receipt['end_clock']['state'] == 'ready'
            assert receipt['end_clock']['competition_id'] == receipt['competition_id']
        for round_number in (1, 2, 3):
            observations = {}
            repeated = 0
            for frame in frames:
                message = frame.get('message', {})
                if (frame['type'] != 'news' or not isinstance(message, dict)
                        or message.get('type') != 'storm' or message.get('round') != round_number):
                    continue
                age = message['age']
                assert type(age) in (int, float) and age % 2 == 0 and 0 <= age <= 480
                point = [message[k] for k in ('x', 'y', 'radius', 'intensity')]
                if age in observations:
                    assert observations[age] == point, 'conflicting repeated storm observation'
                    repeated += 1
                observations[age] = point
            ages = sorted(observations)
            assert ages == list(range(0, 481, 2))
            captured = np.array([observations[age] for age in ages])
            assert captured.shape == (241, 4) and np.isfinite(captured).all()
            delta = tracks - captured[None, :, :]
            max_error = np.max(np.abs(delta), axis=(1, 2))
            rmse = np.sqrt(np.mean(delta ** 2, axis=(1, 2)))
            exact = np.flatnonzero(max_error == 0).tolist()
            results.append(dict(capture=capture, round=round_number,
                competition_id=receipt['competition_id'], receipt_at=receipt['at'],
                observations=len(ages), repeated_identical_observations=repeated,
                exact_match_count=len(exact), exact_library_rows_zero_based=exact,
                closest_full_track_rmse=float(rmse.min()),
                captured_track_sha256=hashlib.sha256(captured.astype('<f8').tobytes()).hexdigest()))
    changed = [path for path, expected in sources.items() if digest(path) != expected]
    assert not changed and not forbidden
    report = dict(audit='closed-capture fitted-analog overlap', completed_at=time.time(),
        library_shape=list(tracks.shape), source_sha256=sources, results=results,
        captured_storms=len(results), exact_matching_storms=sum(bool(r['exact_match_count']) for r in results),
        changed_sources=changed, forbidden_attempts=forbidden,
        limitations=['Exact weather-track overlap does not establish identical advisories, market quotes or execution.',
                    'Chronological source freezes do not make these storms independent of model fitting.',
                    'No active capture, downloaded-history file, trading call or alternative performance run was used.'])
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('captured_storms', 'exact_matching_storms',
                                           'changed_sources', 'forbidden_attempts')}))


if __name__ == '__main__':
    main()
