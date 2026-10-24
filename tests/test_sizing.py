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


def final_report_trader(market, fair, full_edge=.005):
    trader = FairValueTrader(min_edge=.025, edge_full=.03, final_exact=True,
                            final_edge=.005, final_edge_full=full_edge,
                            max_cross=.02, symbols=['PORT'])
    trader.on_start(market)
    trader.model.round = 3
    trader.model.storm_reported = True
    trader.model.reported_rounds = {1, 2, 3}
    trader.fair = {'PORT': fair}
    return trader


@pytest.mark.parametrize('fair', [101., 99., 102.3, 97.7])
def test_wide_spread_cannot_force_new_risk_past_fair_value_edge(market, fair):
    market.quotes['PORT'] = (98., 102.)
    trader = final_report_trader(market, fair)
    trader.on_quotes(market)
    assert not market.pending


@pytest.mark.parametrize('fair,side', [(103., 'buy'), (97., 'sell')])
def test_executable_entry_preserves_its_edge_after_paying_spread(market, fair, side):
    market.quotes['PORT'] = (98., 102.)
    trader = final_report_trader(market, fair)
    trader.on_quotes(market)
    assert len(market.pending) == 1
    order = market.pending[0]
    assert order.side == side
    if side == 'buy':
        assert 102 <= order.price <= fair / 1.005
    else:
        assert fair / .995 <= order.price <= 98


@pytest.mark.parametrize('position,fair,side', [(100, 101., 'sell'), (-100, 99., 'buy')])
def test_fair_value_entry_guard_allows_reducing_existing_risk(market, position, fair, side):
    market.quotes['PORT'] = (98., 102.)
    market.position['PORT'] = position
    trader = final_report_trader(market, fair, full_edge=.05)
    trader.on_quotes(market)
    assert len(market.pending) == 1
    order = market.pending[0]
    assert order.side == side
    assert 0 < order.qty <= abs(position)


@pytest.mark.parametrize('position,fair,side', [(100, 99., 'sell'), (-100, 101., 'buy')])
def test_unexecutable_reversal_can_flatten_but_cannot_open_opposite_risk(market, position, fair, side):
    market.quotes['PORT'] = (98., 102.)
    market.position['PORT'] = position
    trader = final_report_trader(market, fair)
    trader.on_quotes(market)
    assert len(market.pending) == 1
    order = market.pending[0]
    assert order.side == side
    assert order.qty == abs(position)


@pytest.mark.parametrize('initial_fair,new_fair,side', [(103., 101., 'buy'), (97., 99., 'sell')])
def test_partially_filled_entry_is_cancelled_when_its_price_loses_required_edge(market, initial_fair, new_fair, side):
    market.quotes['PORT'] = (98., 102.)
    market.depth = 20
    trader = final_report_trader(market, initial_fair)
    trader.on_quotes(market)
    market.t = .25
    market._activate_pending()
    assert abs(market.position['PORT']) == 20
    assert market.resting('PORT', side) == 180
    trader.fair['PORT'] = new_fair
    trader.last_trade_t = -1e9  # valuation-changing news resets this timer
    trader.on_quotes(market)
    assert market.resting('PORT', side) == 0
    assert abs(market.position['PORT']) == 20


def test_opposing_stale_orders_are_cancelled_even_when_their_net_quantity_is_zero(market):
    market.quotes['PORT'] = (98., 102.)
    market.place('PORT', 'buy', 5, 110)
    market.place('PORT', 'sell', 5, 90)
    trader = final_report_trader(market, 100.)
    trader.on_quotes(market)
    assert market.resting('PORT', 'buy') == 0
    assert market.resting('PORT', 'sell') == 0


@pytest.mark.parametrize('tracked_price,stale', [(98.5, False), (98.6, True)])
def test_only_the_matching_passive_quote_uses_its_fractional_edge_floor(market, tracked_price, stale):
    market.place('PORT', 'buy', 5, 98.5)
    trader = final_report_trader(market, 100.)
    trader.passive = .5
    trader.passive_order['PORT'] = ('buy', tracked_price, 0.)
    assert trader.stale_risk_orders(market, 'PORT', 100., 1., .02) is stale


def test_combined_working_orders_cannot_hide_an_unprofitable_reversal(market):
    market.position['PORT'] = 10
    market.place('PORT', 'sell', 6, 105.)
    market.place('PORT', 'sell', 6, 99.)
    trader = final_report_trader(market, 100.)
    assert trader.stale_risk_orders(market, 'PORT', 100., 1., .005)


@pytest.mark.parametrize('position,fair,old_price,side', [(100, 97., 90., 'sell'), (-100, 103., 110., 'buy')])
def test_new_target_reconciles_zero_net_orders_before_they_can_add_bad_risk(market, position, fair, old_price, side):
    market.quotes['PORT'] = (98., 102.)
    market.position['PORT'] = position
    market.place('PORT', 'buy', 100, old_price)
    market.place('PORT', 'sell', 100, old_price)
    trader = final_report_trader(market, fair)
    assert not trader.stale_risk_orders(market, 'PORT', fair, 1., .005)
    trader.on_quotes(market)
    assert len(market.pending) == 1
    assert market.pending[0].side == side
    assert market.pending[0].qty == 300
    assert not trader.stale_risk_orders(market, 'PORT', fair, 1., .005)


def test_sell_edge_of_one_rejects_working_risk_without_zero_division(market):
    market.place('PORT', 'sell', 5, 110.)
    trader = final_report_trader(market, 100.)
    assert trader.stale_risk_orders(market, 'PORT', 100., 1., 1.)


@pytest.mark.parametrize('price', [None, float('nan'), float('inf'), 0.])
def test_uncapped_or_invalid_working_entry_is_stale(market, price):
    market.place('PORT', 'buy', 5, 100.)
    market.pending[0].price = price
    trader = final_report_trader(market, 100.)
    assert trader.stale_risk_orders(market, 'PORT', 100., 1., .005)


def test_report_only_snapshot_retains_conservative_final_sizing(market):
    trader = FairValueTrader(min_edge=0.025, edge_full=0.03, final_exact=True,
                            final_edge=0.005, final_edge_full=0.005)
    trader.on_start(market)
    trader.model.on_snapshot({"round": 3, "phase": "aftermath", "damage": [
        {"round": r, "stage": "final", "damage_pct": {k: 5 for k in trader.model.states},
         "industry_loss_musd": 100} for r in (1, 2, 3)]})
    assert not trader.model.final_exact_ready
    assert trader.min_edge_for(market, "PORT") == pytest.approx(0.025)
    assert trader.full_edge_for_phase() == pytest.approx(0.03)


def test_diagnostic_recorder_preserves_round_open_warmup(market, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from dissect import Recorder

    recorder = Recorder(min_edge=0.01, edge_full=0.03, warmup=20, symbols=["PORT"])
    recorder.on_start(market)
    recorder.model.round = 3
    recorder.model.storm_reported = True
    recorder.fair = {"PORT": 110}
    market.t = 100
    recorder.on_round(market)
    recorder.on_quotes(market)
    assert not market.pending
    market.t = 120
    recorder.on_quotes(market)
    assert len(market.pending) == 1


@pytest.mark.parametrize("edge", [-0.01, float("nan"), float("inf")])
def test_invalid_final_edge_is_rejected(edge):
    with pytest.raises(ValueError, match="final_edge"):
        FairValueTrader(final_edge=edge)


@pytest.mark.parametrize("ramp", [-0.01, float("nan"), float("inf")])
def test_invalid_sizing_ramp_is_rejected(ramp):
    with pytest.raises(ValueError, match="edge_ramp"):
        FairValueTrader(edge_ramp=ramp)
