import copy
import json

import pytest

from scripts import compare_practice_supervisor as runner


def forward_spec(tmp_path):
    observations = tmp_path / 'observations.jsonl'
    observations.write_text('{"kind":"clock"}\n')
    feed = tmp_path / 'feed.jsonl'
    feed.write_text('{"type":"snapshot"}\n')
    return dict(captures=[dict(capture=245, mode='observed', observations=str(observations),
        observations_bytes=observations.stat().st_size, observations_sha256=runner.digest(observations),
        feed=str(feed), feed_bytes=feed.stat().st_size, feed_sha256=runner.digest(feed))])


def test_default_comparison_still_requires_original_four_captures(tmp_path):
    with pytest.raises(ValueError):
        runner.capture_numbers(forward_spec(tmp_path), forward=False)
    assert runner.capture_numbers({'captures': [{'capture': n} for n in [241, 242, 243, 244]]}, False) == [241, 242, 243, 244]


@pytest.mark.parametrize('capture', [244, True, 245., '245', 601])
def test_forward_rejects_wrong_capture_domain(tmp_path, capture):
    spec = forward_spec(tmp_path)
    spec['captures'][0]['capture'] = capture
    with pytest.raises(ValueError):
        runner.capture_numbers(spec, forward=True)


def test_forward_requires_one_observed_capture(tmp_path):
    spec = forward_spec(tmp_path)
    assert runner.capture_numbers(spec, forward=True) == [245]
    spec['captures'] *= 2
    with pytest.raises(ValueError):
        runner.capture_numbers(spec, forward=True)
    spec['captures'] = spec['captures'][:1]
    spec['captures'][0]['mode'] = 'completed'
    with pytest.raises(ValueError):
        runner.capture_numbers(spec, forward=True)


@pytest.mark.parametrize('field', ['observations', 'feed'])
def test_sealed_inputs_reject_appends_even_when_original_prefix_hash_is_unchanged(tmp_path, field):
    spec = forward_spec(tmp_path)
    item = spec['captures'][0]
    runner.sealed_forward_inputs(item)
    with open(item[field], 'a') as handle:
        handle.write('{"kind":"later_duplicate"}\n')
    with pytest.raises(ValueError, match='sealed'):
        runner.sealed_forward_inputs(item)


@pytest.mark.parametrize('at', [1792828814.999, 1792843200, float('nan'), True])
def test_forward_receipt_window_is_fixed_and_excludes_cutoff(at):
    with pytest.raises(ValueError):
        runner.forward_receipt_in_window({'at': at})


def test_forward_receipt_window_accepts_boundaries_inside_interval():
    runner.forward_receipt_in_window({'at': 1792828815})
    runner.forward_receipt_in_window({'at': 1792843199.999})


def archive_fixture(tmp_path):
    path = tmp_path / 'results.jsonl'
    rows = [dict(status='ok', rtt_seconds=r, displayed_depth_fraction=d, basket_enabled=b)
            for r, d, b in runner.GRID]
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    receipt, frames = {'at': 1792829000}, [{'received_at': 1792828900}]
    sources = {'frozen.py': 'source-hash'}
    parameters = {'warmup': 20}
    metadata = dict(mode='observed', competition_id='closed', year='1782', source_revision='frozen',
        source_sha256=sources, receipt_sha256=runner.value_hash(receipt),
        frames_sha256=runner.value_hash(frames), official_receipt=receipt,
        frame_count=1, first_at=frames[0]['received_at'], last_at=frames[0]['received_at'],
        receipt_at=receipt['at'], fraction=.1, parameters=parameters,
        rtts=[0., .05, .25, 1.], depths=[1., .5], baskets=[False, True])
    summary = dict(runs=16, errors=0, elapsed_seconds=1.)
    for name, data in [('metadata.json', metadata), ('summary.json', summary)]:
        (tmp_path / name).write_text(json.dumps(data))
    item = dict(capture=245, competition_id='closed', archive_results=str(path),
        archive_results_sha256=runner.digest(path),
        archive_metadata_sha256=runner.digest(tmp_path / 'metadata.json'),
        archive_summary_sha256=runner.digest(tmp_path / 'summary.json'))
    return item, receipt, frames, sources, parameters


def test_upstream_archive_provenance_accepts_complete_matching_artifacts(tmp_path):
    args = archive_fixture(tmp_path)
    runner.verify_forward_archive(*args, reference_revision='frozen')


@pytest.mark.parametrize('corruption', ['metadata_hash', 'summary_hash', 'results_hash', 'source',
    'receipt', 'frames', 'identity', 'parameters', 'errors', 'runs', 'missing_summary', 'row_error', 'grid'])
def test_upstream_archive_provenance_rejects_corruption(tmp_path, corruption):
    item, receipt, frames, sources, parameters = archive_fixture(tmp_path)
    if corruption.endswith('_hash'):
        item['archive_' + corruption.replace('_hash', '_sha256')] = 'wrong'
    elif corruption == 'missing_summary':
        (tmp_path / 'summary.json').unlink()
    else:
        name = 'summary.json' if corruption in ('errors', 'runs') else 'results.jsonl' if corruption in ('row_error', 'grid') else 'metadata.json'
        path = tmp_path / name
        if name.endswith('jsonl'):
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            if corruption == 'row_error':
                rows[0]['status'] = 'error'
            else:
                rows[-1] = copy.deepcopy(rows[0])
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        else:
            data = json.loads(path.read_text())
            field = {'source': 'source_sha256', 'receipt': 'receipt_sha256', 'frames': 'frames_sha256',
                     'identity': 'competition_id', 'parameters': 'parameters', 'errors': 'errors', 'runs': 'runs'}[corruption]
            data[field] = 1 if corruption == 'errors' else 'wrong'
            path.write_text(json.dumps(data))
        item['archive_' + name.split('.')[0] + '_sha256'] = runner.digest(path)
    with pytest.raises((ValueError, OSError)):
        runner.verify_forward_archive(item, receipt, frames, sources, parameters, reference_revision='frozen')
