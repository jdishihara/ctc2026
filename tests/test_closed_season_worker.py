import json

import pytest

from scripts import evaluate_closed_seasons as worker


CID = '5edc122c-e97d-4d59-ada5-658c02c3c0da'


def results():
    return {'evaluation': 'fixed_observed_market_grid', 'fraction': .1,
        'results': [dict(latency_seconds=lat, displayed_depth_fraction=depth,
        basket_enabled=basket, reset_warmup_each_snapshot=reset,
        simulated_settlement_pnl=-1 if lat == 3 else 2)
        for lat in (.25, 1., 3.) for depth in (1., .5)
        for basket in (False, True) for reset in (True, False)], 'coverage': {}}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    observations = tmp_path / 'observations.jsonl'
    observations.write_text('')
    source = tmp_path / 'source.py'
    source.write_text('original')
    out = tmp_path / 'out'
    out.mkdir()
    manifest = {'sources': {str(source): worker.file_hash(source)}}
    calls = []

    def capture(obs, feed, cid, symbols):
        calls.append(cid)
        receipt = next(r for r in worker.complete_lines(obs) if r.get('competition_id') == cid)
        return receipt, [], {}

    monkeypatch.setattr(worker, 'observed_capture', capture)
    monkeypatch.setattr(worker, 'evaluate', lambda case, receipt, *args:
        {**results(), 'official_receipt': receipt, 'competition_id': receipt['competition_id'],
         'year': receipt['year']})
    return observations, source, out, manifest, calls


def run(setup):
    obs, source, out, manifest, calls = setup
    return worker.process_once(obs, obs, out, {'limits': {}}, manifest, 100, 200)


def receipt(at=150):
    return {'kind': 'settlement', 'at': at, 'competition_id': CID, 'year': '1784'}


def test_only_complete_receipts_inside_the_time_window_are_evaluated(setup):
    obs, _, out, _, calls = setup
    rows = [dict(kind='clock', at=150), receipt(99), receipt(201)]
    obs.write_text(''.join(json.dumps(r) + '\n' for r in rows) + '{"kind":"settlement"')
    assert run(setup) == []
    assert calls == []
    assert not list(out.glob('*.json'))


def test_completed_receipt_is_evaluated_once_and_all_scenarios_remain(setup):
    obs, _, out, _, calls = setup
    obs.write_text(json.dumps(receipt()) + '\n')
    events = run(setup)
    assert events[0]['kind'] == 'evaluated'
    assert events[0]['negative_scenarios'] == 8
    assert events[0]['worst'] == -1
    assert len(json.loads((out / f'{CID}.json').read_text())['results']) == 24
    assert run(setup) == []
    assert calls == [CID]


def test_invalid_capture_is_recorded_and_never_claimed_as_a_result(setup, monkeypatch):
    obs, _, out, _, calls = setup
    obs.write_text(json.dumps(receipt()) + '\n')

    def invalid(*args):
        raise ValueError('missing final report')

    monkeypatch.setattr(worker, 'observed_capture', invalid)
    events = run(setup)
    assert events[0]['kind'] == 'failed'
    assert 'missing final report' in events[0]['error']
    assert not (out / f'{CID}.json').exists()
    assert run(setup) == []


def test_source_change_stops_before_evaluation(setup):
    obs, source, _, _, calls = setup
    obs.write_text(json.dumps(receipt()) + '\n')
    source.write_text('changed')
    with pytest.raises(ValueError, match='source changed'):
        run(setup)
    assert not calls


def test_changed_receipt_cannot_silently_replace_existing_result(setup):
    obs, _, out, _, calls = setup
    obs.write_text(json.dumps(receipt()) + '\n')
    run(setup)
    original = (out / f'{CID}.json').read_bytes()
    obs.write_text(json.dumps({**receipt(), 'year': '1783'}) + '\n')
    with pytest.raises(ValueError, match='receipt changed'):
        run(setup)
    assert (out / f'{CID}.json').read_bytes() == original
    assert calls == [CID]


def test_missing_scenario_or_nonfinite_result_is_rejected():
    result = results()
    result['results'].pop()
    with pytest.raises(ValueError, match='24'):
        worker.summarize(result)
    result = results()
    result['results'][0]['simulated_settlement_pnl'] = float('nan')
    with pytest.raises(ValueError, match='finite'):
        worker.summarize(result)


@pytest.mark.parametrize('damage', ['missing', 'modified'])
def test_restart_rejects_missing_or_modified_successful_artifact(setup, damage):
    obs, _, out, _, _ = setup
    obs.write_text(json.dumps(receipt()) + '\n')
    run(setup)
    path = out / f'{CID}.json'
    if damage == 'missing':
        path.unlink()
    else:
        path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError, match='artifact'):
        run(setup)


def test_orphan_with_wrong_identity_is_not_certified(setup):
    obs, _, out, _, _ = setup
    obs.write_text(json.dumps(receipt()) + '\n')
    run(setup)
    (out / 'ledger.jsonl').unlink()
    path = out / f'{CID}.json'
    artifact = json.loads(path.read_text())
    artifact.update(competition_id='other', year='9999')
    path.write_text(json.dumps(artifact))
    events = run(setup)
    assert events[0]['kind'] == 'failed'
    assert 'identity' in events[0]['error']


def test_final_drain_evaluates_receipt_written_during_last_sleep(setup, monkeypatch):
    obs, _, out, manifest, calls = setup
    now = [180]
    monkeypatch.setattr(worker.time, 'time', lambda: now[0])

    def sleep(seconds):
        obs.write_text(json.dumps(receipt(190)) + '\n')
        now[0] += seconds

    monkeypatch.setattr(worker.time, 'sleep', sleep)
    worker.run_loop(obs, obs, out, {'limits': {}}, manifest, 100, 200)
    assert calls == [CID]
    events = list(worker.complete_lines(out / 'ledger.jsonl'))
    assert events[-1]['kind'] == 'evaluated'


@pytest.mark.parametrize('altered', [False, True])
def test_orphan_results_are_reproduced_before_recovery(setup, altered):
    obs, _, out, _, calls = setup
    obs.write_text(json.dumps(receipt()) + '\n')
    run(setup)
    (out / 'ledger.jsonl').unlink()
    path = out / f'{CID}.json'
    if altered:
        artifact = json.loads(path.read_text())
        artifact['results'][0]['simulated_settlement_pnl'] = 999
        path.write_text(json.dumps(artifact))
    events = run(setup)
    assert calls == [CID, CID]
    assert events[0]['kind'] == ('failed' if altered else 'evaluated')
