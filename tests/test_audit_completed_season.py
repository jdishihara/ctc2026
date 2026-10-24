import json
from pathlib import Path
import sys

import pytest

from scripts import audit_completed_season


@pytest.mark.parametrize('season, trial_year, receipt_year', [
    (242, '1786', '1786'),
    (241, '1786', '1785'),
    (241, '1786-extra', '1786'),
    (241, None, '1786'),
], ids=['next-season', 'receipt-year-mismatch', 'malformed-year', 'missing-year'])
def test_audit_rejects_unbound_season_before_reading_history(
        tmp_path, monkeypatch, capsys, season, trial_year, receipt_year):
    batch = tmp_path / 'batch'
    batch.mkdir()
    (batch / 'status.json').write_text(json.dumps({'trials': {'closed': {
        'completed': True, 'year': trial_year, 'started_at': 1000,
        'completed_at': 2000,
    }}}))
    (batch / 'actions.jsonl').write_text(json.dumps({
        'kind': 'settlement', 'competition_id': 'closed',
        'clock': {'competition_id': 'closed', 'state': 'ready',
                  'fictional_time': f'{receipt_year}-05-31T16:00:00'},
    }) + '\n')
    feed = tmp_path / 'feed.jsonl'
    feed.write_text('')
    monkeypatch.setattr(audit_completed_season, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['audit_completed_season.py',
        '--batch', str(batch), '--feed', str(feed),
        '--competition-id', 'closed', '--season', str(season)])

    # This boundary must reject the request before even opening the manifest,
    # which itself contains historical outcome metadata.
    original_open = Path.open
    history = tmp_path / 'data/history'

    def guarded_open(path, *args, **kwargs):
        if history in path.parents:
            pytest.fail(f'Historical data opened before the season was bound: {path}')
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', guarded_open)
    with pytest.raises(SystemExit) as error:
        audit_completed_season.main()
    assert error.value.code == 2
    assert 'year' in capsys.readouterr().err
