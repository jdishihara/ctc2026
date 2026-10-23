import math

import pytest

from ctc.wind import SiteState


def state(cumulative, damage):
    case = {"companies": {"PORT": {"sites": [
        {"weight": 0.5, "x": 0, "y": 0}, {"weight": 0.5, "x": 1, "y": 1}]}}}
    result = SiteState(case, "PORT")
    result.cum = list(cumulative)
    result.exposure = [-math.log(1 - d / (100 - c)) / result.c
                       for c, d in zip(cumulative, damage)]
    return result


def test_report_excess_is_redistributed_after_a_site_hits_its_capacity():
    st = state([90, 0], [9, 9])
    st.set_from_report(30)
    assert st.storm_damage() == pytest.approx(30, abs=1e-8)
    assert st.storm_damage_site(0) == pytest.approx(10, abs=1e-8)
    assert st.storm_damage_site(1) == pytest.approx(50, abs=1e-8)
    st.new_storm()
    assert st.cum_damage() == pytest.approx(75, abs=1e-8)


def test_missing_track_reports_use_remaining_capacity_not_original_capacity():
    st = state([20, 60], [0, 0])
    st.set_from_report(15)
    assert st.storm_damage() == pytest.approx(15)
    assert st.storm_damage_site(0) == pytest.approx(20)
    assert st.storm_damage_site(1) == pytest.approx(10)


def test_report_can_allocate_damage_to_a_previously_unobserved_site():
    st = state([90, 0], [9, 0])
    st.set_from_report(30)
    assert st.storm_damage() == pytest.approx(30, abs=1e-8)


def test_report_never_exceeds_remaining_company_capacity():
    st = state([90, 0], [9, 9])
    st.set_from_report(80)
    assert st.storm_damage() == pytest.approx(55, abs=1e-8)
    assert all(st.cum[j] + st.storm_damage_site(j) <= 100 for j in range(2))


def test_uncapped_rescaling_retains_original_site_ratios():
    st = state([0, 0], [5, 15])
    st.set_from_report(20)
    assert st.storm_damage_site(0) == pytest.approx(10)
    assert st.storm_damage_site(1) == pytest.approx(30)
