import json

import pytest

from scripts import compare_practice_supervisor as runner


def artifacts(tmp_path):
    path = tmp_path / 'results.jsonl'
    row = dict(capture=241, rtt_seconds=.25, displayed_depth_fraction=1., basket_enabled=True,
               status='ok', comparison_status='matched_archive')
    path.write_text(json.dumps(row) + '\n')
    metadata = dict(phase='reference', source_revision='frozen', captures=[])
    summary = dict(runs=1, errors=0, mismatches=0, changed_sources=[], finished_at=123,
                   results_sha256=runner.digest(path))
    (tmp_path / 'metadata.json').write_text(json.dumps(metadata))
    (tmp_path / 'summary.json').write_text(json.dumps(summary))
    return path, summary


@pytest.mark.parametrize('corruption', ['missing_summary', 'changed_source', 'wrong_hash', 'error', 'mismatch', 'unfinished'])
def test_gate_rejects_incomplete_or_modified_predecessor(tmp_path, corruption):
    path, summary = artifacts(tmp_path)
    if corruption == 'missing_summary':
        (tmp_path / 'summary.json').unlink()
    else:
        if corruption == 'changed_source':
            summary['changed_sources'] = ['model.py']
        elif corruption == 'wrong_hash':
            summary['results_sha256'] = 'different'
        elif corruption == 'error':
            summary['errors'] = 1
        elif corruption == 'mismatch':
            summary['mismatches'] = 1
        elif corruption == 'unfinished':
            summary.pop('finished_at')
        (tmp_path / 'summary.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError):
        runner.completed_phase(path, 'reference', {(241, .25, 1., True)})


def test_gate_accepts_completed_matching_results(tmp_path):
    path, summary = artifacts(tmp_path)
    rows, metadata = runner.completed_phase(path, 'reference', {(241, .25, 1., True)})
    assert len(rows) == 1 and metadata['source_revision'] == 'frozen'


@pytest.mark.parametrize('field', ['competition_id', 'year', 'receipt_sha256', 'frames_sha256', 'archive_sha256'])
def test_gate_binds_capture_identity_and_bytes_across_phases(field):
    capture = dict(capture=241, competition_id='closed', year='1786', receipt_sha256='r',
                   frames_sha256='f', archive_sha256='a', receipt_at=5, first_at=1,
                   last_at=4, frame_count=2)
    with pytest.raises(ValueError, match='capture input changed'):
        runner.same_captures([capture], [{**capture, field: 'different'}])
