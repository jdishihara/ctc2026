import copy
from types import SimpleNamespace

import pytest

from scripts import check_repeat_blend_development as driver


@pytest.mark.parametrize('access', [lambda p: p['PORT'], lambda p: p.copy(), copy.copy, copy.deepcopy])
def test_settlement_reads_and_copies_latch_early_access(access):
    violations = []
    prices = driver.TerminalPrices({'PORT': 100}, SimpleNamespace(t=0, market_open=False), violations)
    with pytest.raises(RuntimeError, match='before season end'):
        access(prices)
    assert violations == ['early settlement read']


def test_settlement_mapping_preserves_normal_values_api_after_terminal():
    violations = []
    prices = driver.TerminalPrices({'PORT': 100}, SimpleNamespace(t=2340, market_open=False), violations)
    assert list(prices.values()) == [100]
    assert prices.copy() == {'PORT': 100}
    assert dict(copy.copy(prices)) == {'PORT': 100}
    assert dict(copy.deepcopy(prices)) == {'PORT': 100}
    assert not violations


@pytest.mark.parametrize('clock', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_terminal_clock_never_releases_prices(clock):
    violations = []
    prices = driver.TerminalPrices({'PORT': 100}, SimpleNamespace(t=clock, market_open=False), violations)
    with pytest.raises(RuntimeError):
        prices['PORT']
    assert violations


@pytest.mark.parametrize('name', ['feed.jsonl', 'market.csv', 'settlement.json'])
def test_other_history_root_and_out_of_split_are_blocked(tmp_path, name):
    history = tmp_path / 'declared'
    forbidden = []
    audit = driver.make_input_audit(history, forbidden)
    audit('open', (str(history / 'season-451' / name), 'r', 0))
    for path in [history / 'season-450' / name, history / 'season-526' / name,
                 tmp_path / 'another-tree' / 'season-451' / name]:
        with pytest.raises(RuntimeError):
            audit('open', (str(path), 'r', 0))
    assert len(forbidden) == 3


def test_unmatched_pair_difference_is_distinguished_from_recognition_change():
    rows = [dict(season=s, repeat_prefix=e, pnl=p) for s, e, p in [
        (451, False, 10), (451, True, 11), (452, False, 10), (452, True, 11),
        (453, False, 12), (453, True, 12)]]
    scans = [dict(season=s, first_match=([21, 4] if s == 452 else None))
             for s in (451, 452, 453) for _ in range(3)]
    assert driver.unmatched_differences(rows, scans) == [451]


@pytest.mark.parametrize('target_name', ['feed.jsonl', 'track-data.txt'])
def test_declared_input_symlink_cannot_escape_the_allowed_split(tmp_path, target_name):
    history = tmp_path / 'declared'
    source = history / 'season-451' / 'feed.jsonl'
    source.parent.mkdir(parents=True)
    source.symlink_to(tmp_path / 'outside' / 'season-526' / target_name)
    forbidden = []
    audit = driver.make_input_audit(history, forbidden)
    with pytest.raises(RuntimeError, match='outside declared'):
        audit('open', (str(source), 'r', 0))
    assert len(forbidden) == 1
