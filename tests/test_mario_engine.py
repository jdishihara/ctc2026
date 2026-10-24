"""Packet settlement guarantees, independent of the racer skill model."""
import pytest

from mario.contracts import RACERS
from mario.engine import Engine


@pytest.mark.parametrize(
    "kind,side,price,guaranteed_profit",
    [
        ("swin", "sell", 30, None),  # 120 collected; a four-way tie owes 200.
        ("swin", "sell", 50, None),  # No strictly positive worst-case profit.
        ("swin", "sell", 55, 1000),  # (220 - 200) * 50 complete sets.
        ("swin", "buy", 20, 1000),   # All series outcomes pay at least 100.
        ("race", "sell", 30, 1000), # Each race has exactly one human winner.
        ("race", "buy", 20, 1000),
    ],
)
def test_complete_set_arbitrage_uses_packet_settlement_bounds(
    kind, side, price, guaranteed_profit
):
    roles = {f"{kind}_{racer}": (kind, 1, racer) for racer in RACERS}
    level = "bids" if side == "sell" else "asks"
    books = {symbol: {level: [{"price": price, "quantity": 50}]} for symbol in roles}
    fairs = {(kind, 1): [25] * 4 if kind == "swin" else [0.25] * 4}

    actions = Engine(roles).evaluate(fairs, books, {}, n_done=0)["actions"]
    arbs = [action for action in actions if action.kind == "arb"]

    if guaranteed_profit is None:
        assert arbs == []
    else:
        assert len(arbs) == 1
        assert arbs[0].profit == guaranteed_profit
        assert len(arbs[0].legs) == 4
        assert all(leg[1:] == (side, 50, price) for leg in arbs[0].legs)


def test_model_uncertainty_widens_the_edge_margin():
    """A 3-point edge on a score contract is listed with the default margin but not when the parameter ensemble
    disagrees about the fair by 5 points (margin >= model_sd_k x model sd)."""
    roles = {"S1_NO1": ("s1", 1)}
    fairs = {("s1", 1): (48.0, 4.0), "points": [[0, 0, 0, 0], [0, 0, 0, 0]]}
    books = {"S1_NO1": {"asks": [{"price": 45.0, "quantity": 20}], "bids": [{"price": 44.0, "quantity": 20}]}}
    plain = Engine(roles).evaluate(fairs, books, {}, n_done=0)["actions"]
    assert [a.kind for a in plain] == ["edge"] and plain[0].legs[0][1] == "buy"
    wide = Engine(roles).evaluate(fairs, books, {}, n_done=0, model_sd={"S1_NO1": 5.0})["actions"]
    assert wide == []
    off = Engine(roles, __import__("mario.engine", fromlist=["Params"]).Params(model_sd_k=0.0)).evaluate(fairs, books, {}, n_done=0, model_sd={"S1_NO1": 5.0})["actions"]
    assert len(off) == 1
