import json
from pathlib import Path

import pytest

from ctc.sim import Sim
from ctc.strategies import FairValueTrader


CASE = json.loads((Path(__file__).resolve().parents[1] / "data/case.json").read_text())


@pytest.fixture
def market(tmp_path):
    (tmp_path / "settlement.json").write_text(json.dumps({"PORT": 100}))
    (tmp_path / "market.csv").write_text("time,round,PORT\n")
    (tmp_path / "feed.jsonl").write_text("")
    sim = Sim(tmp_path, CASE)
    sim.market_open = True
    sim.mid = {"PORT": 100}
    sim.quotes = {"PORT": (99.9, 100.1)}
    return sim


def submit(market, fair, **kwargs):
    trader = FairValueTrader(min_edge=0.08, edge_full=0.03,
                            symbols=["PORT"], **kwargs)
    trader.on_start(market)
    trader.model.round = 3
    trader.model.storm_reported = True
    trader.fair = {"PORT": fair}
    trader.on_quotes(market)
    return market.pending


@pytest.mark.parametrize("fair,side", [(110, "buy"), (90, "sell")])
def test_uncertain_forecast_can_take_half_size_instead_of_all_in(market, fair, side):
    # An 8% edge floor and another 2% edge are halfway through a 4% ramp.
    orders = submit(market, fair, edge_ramp=0.04)
    assert len(orders) == 1
    assert orders[0].side == side
    assert orders[0].qty == CASE["limits"]["PORT"] // 2


@pytest.mark.parametrize("fair,side", [(130, "buy"), (70, "sell")])
def test_sizing_ramp_still_caps_at_position_limit(market, fair, side):
    orders = submit(market, fair, edge_ramp=0.04)
    assert orders[0].qty == CASE["limits"]["PORT"]
    assert orders[0].side == side


def test_zero_ramp_preserves_previous_sizing(market):
    assert submit(market, 110, edge_ramp=0)[0].qty == CASE["limits"]["PORT"]


def test_rounding_a_passive_quote_does_not_create_a_full_size_bet(market):
    trader = FairValueTrader(passive=0.75, edge_full=0.03, edge_ramp=0.04)
    trader.on_start(market)
    # Rounding 100.0047 to 100 adds only 0.005% excess edge, not a full-size signal.
    trader.quote_passive(market, "PORT", 106.005, 99.9, 100.1, 1, 0.08, 200, 0)
    assert not market.pending


def test_smaller_final_edge_is_gated_on_all_three_final_reports(market):
    trader = FairValueTrader(min_edge=0.025, final_exact=True, final_edge=0.005)
    trader.on_start(market)
    trader.model.round = 3
    trader.model.storm_reported = True
    trader.model.reported_rounds = {1, 3}
    assert trader.min_edge_for(market, "PORT") == pytest.approx(0.025)
    trader.model.reported_rounds.add(2)
    assert trader.min_edge_for(market, "PORT") == pytest.approx(0.005)
    # An uncertain symbol must still retain its residual-error floor.
    market.mid["PORT"] = 1
    assert trader.min_edge_for(market, "PORT") > 0.1


def test_final_phase_can_size_to_a_smaller_full_edge(market):
    trader = FairValueTrader(min_edge=0.025, edge_full=0.03, final_exact=True,
                            final_edge=0.005, final_edge_full=0.01, symbols=["PORT"])
    trader.on_start(market)
    trader.model.round = 3
    trader.model.storm_reported = True
    trader.model.reported_rounds = {1, 2, 3}
    trader.fair = {"PORT": 101}
    trader.on_quotes(market)
    assert market.pending[0].qty == CASE["limits"]["PORT"]


@pytest.mark.parametrize("edge", [-0.01, float("nan"), float("inf")])
def test_invalid_final_edge_is_rejected(edge):
    with pytest.raises(ValueError, match="final_edge"):
        FairValueTrader(final_edge=edge)


@pytest.mark.parametrize("ramp", [-0.01, float("nan"), float("inf")])
def test_invalid_sizing_ramp_is_rejected(ramp):
    with pytest.raises(ValueError, match="edge_ramp"):
        FairValueTrader(edge_ramp=ramp)
