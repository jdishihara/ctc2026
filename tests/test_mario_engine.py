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
