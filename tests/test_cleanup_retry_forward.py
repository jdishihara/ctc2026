import itertools
import time
from copy import deepcopy

import pytest

from scripts.compare_cleanup_retry_forward import (
    forward_grid, validate_forward_receipt, validate_upstream_metadata,
)


def receipt(at=1792838000.):
    clock = dict(competition_id='closed-test', state='ready', fictional_time='1779-06-07T16:00:00')
    return dict(kind='settlement', at=at, source='read_only_market_observer',
                competition_id='closed-test', year='1779', clock=clock, end_clock=deepcopy(clock),
                prices={'X': 100.}, coverage=dict(first_at=1792837000., last_at=1792837999.,
                contiguous=True, conflicting_sequences=False, final_rounds=[1, 2, 3],
                seq_count=3, last_seq=2, advertised_last_seq=2))


def validate(value, now=1792843201.):
    return validate_forward_receipt(value, capture=248, symbols=['X'], now=now)


@pytest.mark.parametrize('capture', [248, 249])
def test_fixed_forward_grid(capture):
    assert forward_grid(capture) == list(itertools.product(
        [capture], [0., .05, .25, 1.], [1., .5], [False, True]))


@pytest.mark.parametrize('capture', [247, 250, 248.0, True, '248', None])
def test_reject_unplanned_capture(capture):
    with pytest.raises(ValueError):
        forward_grid(capture)


@pytest.mark.parametrize('at', [1792837693., 1792843199.999])
def test_accept_only_declared_receipt_window(at):
    r = receipt(at)
    r['coverage'].update(first_at=at - 10, last_at=at - 1)
    validate(r)


@pytest.mark.parametrize('at', [1792837692.999, 1792843200., float('nan'),
                               float('inf'), True, '1792838000', None])
def test_reject_invalid_or_ineligible_receipt_time(at):
    with pytest.raises(ValueError):
        validate(receipt(at))


@pytest.mark.parametrize('receipt', [{}, [], None, {'kind': 'clock', 'at': 1792838000.}])
def test_reject_nonsettlement_receipt(receipt):
    with pytest.raises(ValueError):
        validate(receipt)


def test_reject_not_yet_observed_receipt():
    with pytest.raises(ValueError):
        validate(receipt(1792838001.), now=1792838000.)


@pytest.mark.parametrize('field,value', [('source', 'not_an_observer'), ('year', '9999'),
                                       ('competition_id', 'other'), ('prices', {}),
                                       ('coverage', {}), ('clock', None), ('end_clock', [])])
def test_reject_inconsistent_official_receipt(field, value):
    r = receipt()
    r[field] = value
    with pytest.raises(ValueError):
        validate(r)


@pytest.mark.parametrize('field', ['clock', 'end_clock'])
def test_reject_running_clock_before_capture_use(field):
    r = receipt()
    r[field]['state'] = 'running'
    with pytest.raises(ValueError):
        validate(r)


@pytest.mark.parametrize('field,value', [('contiguous', False), ('conflicting_sequences', True),
                                       ('final_rounds', [1, 2]), ('first_at', True),
                                       ('last_at', float('nan')), ('last_at', 1792838001.)])
def test_reject_incomplete_coverage(field, value):
    r = receipt()
    r['coverage'][field] = value
    with pytest.raises(ValueError):
        validate(r)


def phase():
    expected = dict(phase='supervised', forward=True, source_revision='frozen',
                    source_sha256={'source': 'hash'}, runtime_revision='baseline',
                    runtime_sha256={'runtime': 'hash'}, fraction=.1, loss_trigger=250., prior_pnl=0.)
    metadata = dict(expected, started_at=time.time() - 2)
    summary = dict(runs=16, errors=0, mismatches=0, changed_sources=[], finished_at=time.time() - 1)
    rows = [dict(capture=c, rtt_seconds=rtt, displayed_depth_fraction=depth, basket_enabled=basket,
                 status='ok', errors=[], comparison_status='supervised_after_verified_baseline')
            for c, rtt, depth, basket in forward_grid(248)]
    return metadata, summary, rows, expected


def test_accept_exact_completed_upstream_phase():
    m, s, rows, expected = phase()
    validate_upstream_metadata(m, s, rows, 248, expected)


@pytest.mark.parametrize('field,value', [('phase', 'reference'), ('forward', False),
    ('source_revision', 'unreviewed'), ('source_sha256', {}), ('runtime_revision', 'wrong'),
    ('runtime_sha256', {}), ('fraction', 1.), ('loss_trigger', 500.), ('prior_pnl', 1.)])
def test_reject_wrong_upstream_provenance(field, value):
    m, s, rows, expected = phase()
    m[field] = value
    with pytest.raises(ValueError):
        validate_upstream_metadata(m, s, rows, 248, expected)


@pytest.mark.parametrize('field,value', [('runs', 15), ('errors', 1), ('mismatches', 1),
    ('changed_sources', ['source']), ('forbidden_attempts', ['network']),
    ('finished_at', float('nan')), ('finished_at', True), ('finished_at', 0.)])
def test_reject_incomplete_upstream_summary(field, value):
    m, s, rows, expected = phase()
    s[field] = value
    with pytest.raises(ValueError):
        validate_upstream_metadata(m, s, rows, 248, expected)


@pytest.mark.parametrize('mutation', ['duplicate', 'missing', 'extra', 'status', 'errors', 'comparison'])
def test_reject_incomplete_or_unverified_upstream_rows(mutation):
    m, s, rows, expected = phase()
    if mutation == 'duplicate':
        rows[0] = deepcopy(rows[1])
    elif mutation == 'missing':
        rows.pop()
    elif mutation == 'extra':
        rows.append(deepcopy(rows[0]))
    elif mutation == 'status':
        rows[0]['status'] = 'error'
    elif mutation == 'errors':
        rows[0]['errors'] = ['failure']
    else:
        rows[0]['comparison_status'] = 'unverified'
    with pytest.raises(ValueError):
        validate_upstream_metadata(m, s, rows, 248, expected)
