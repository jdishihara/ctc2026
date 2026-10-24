import itertools

import pytest

from scripts.compare_cleanup_retry_forward import forward_grid, validate_forward_receipt


@pytest.mark.parametrize('capture', [248, 249])
def test_fixed_forward_grid(capture):
    assert forward_grid(capture) == list(itertools.product(
        [capture], [0., .05, .25, 1.], [1., .5], [False, True]))


@pytest.mark.parametrize('capture', [247, 250, 248.0, True, '248', None])
def test_reject_unplanned_capture(capture):
    with pytest.raises(ValueError):
        forward_grid(capture)


@pytest.mark.parametrize('at', [1792837680., 1792843199.999])
def test_accept_only_declared_receipt_window(at):
    validate_forward_receipt({'kind': 'settlement', 'at': at}, now=1792843201.)


@pytest.mark.parametrize('at', [1792837679.999, 1792843200., float('nan'),
                               float('inf'), True, '1792838000', None])
def test_reject_invalid_or_ineligible_receipt_time(at):
    with pytest.raises(ValueError):
        validate_forward_receipt({'kind': 'settlement', 'at': at}, now=1792843201.)


@pytest.mark.parametrize('receipt', [{}, [], None, {'kind': 'clock', 'at': 1792838000.}])
def test_reject_nonsettlement_receipt(receipt):
    with pytest.raises(ValueError):
        validate_forward_receipt(receipt, now=1792843201.)


def test_reject_not_yet_observed_receipt():
    with pytest.raises(ValueError):
        validate_forward_receipt({'kind': 'settlement', 'at': 1792838001.}, now=1792838000.)
