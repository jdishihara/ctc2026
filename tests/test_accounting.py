import pytest

from ctc import accounting


def trade(ident, side, qty, price, time):
    return {"trade_id": ident, "symbol": "PORT", "side": side, "quantity": qty,
            "price": price, "executed_at": f"2026-10-23T10:00:{time:02d}Z"}


def test_round_trip_and_position_flip_have_correct_realized_pnl():
    fills = [trade("a", "buy", 10, 100, 1), trade("b", "sell", 15, 110, 2),
             trade("c", "buy", 2, 90, 3)]
    state = accounting.replay(fills)["PORT"]
    assert state == {"quantity": -3, "average_price": 110.0, "realized_pnl": 140.0}


def test_latest_first_export_and_duplicate_fills_replay_once():
    a, b = trade("a", "buy", 10, 100, 1), trade("b", "sell", 10, 110, 2)
    state = accounting.replay([b, a, b])["PORT"]
    assert state == {"quantity": 0, "average_price": 0.0, "realized_pnl": 100.0}


def test_opening_inventory_and_realized_pnl_are_preserved():
    opening = [{"symbol": "PORT", "quantity": -10, "average_price": 120, "realized_pnl": 30}]
    state = accounting.replay([trade("a", "buy", 15, 100, 1)], opening)["PORT"]
    assert state == {"quantity": 5, "average_price": 100.0, "realized_pnl": 230.0}


def test_additions_use_weighted_average_cost():
    state = accounting.replay([trade("a", "buy", 10, 100, 1), trade("b", "buy", 30, 120, 2)])["PORT"]
    assert state == {"quantity": 40, "average_price": 115.0, "realized_pnl": 0.0}


def test_explicit_fees_are_charged_once():
    a = {**trade("a", "buy", 10, 100, 1), "fee": 0.25}
    assert accounting.replay([a, a])["PORT"]["realized_pnl"] == -0.25


def test_conflicting_duplicate_id_is_not_silently_deduplicated():
    a = trade("a", "buy", 10, 100, 1)
    with pytest.raises(ValueError, match="duplicate"):
        accounting.replay([a, {**a, "price": 105}])


def test_aggressor_side_is_not_assumed_to_be_our_side():
    a = trade("a", "buy", 10, 100, 1)
    del a["side"]
    a["aggressor_side"] = "buy"
    with pytest.raises(ValueError, match="side"):
        accounting.replay([a])


def test_equal_timestamps_with_opposing_trades_require_sequence():
    with pytest.raises(ValueError, match="order"):
        accounting.replay([trade("a", "buy", 10, 100, 1), trade("b", "sell", 20, 110, 1)])


def test_explicit_sequence_resolves_equal_timestamps():
    fills = [{**trade("b", "sell", 20, 110, 1), "sequence": 2},
             {**trade("a", "buy", 10, 100, 1), "sequence": 1}]
    assert accounting.replay(fills)["PORT"] == {
        "quantity": -10, "average_price": 110.0, "realized_pnl": 100.0}


def test_same_side_position_flip_honors_sequence_in_reversed_export():
    opening = [{"symbol": "PORT", "quantity": 10, "average_price": 100}]
    fills = [{**trade("b", "sell", 10, 120, 1), "sequence": 2},
             {**trade("a", "sell", 5, 110, 1), "sequence": 1}]
    assert accounting.replay(fills, opening)["PORT"] == {
        "quantity": -5, "average_price": 120.0, "realized_pnl": 150.0}


def test_same_side_position_flip_rejects_ambiguous_timestamps():
    opening = [{"symbol": "PORT", "quantity": 10, "average_price": 100}]
    with pytest.raises(ValueError, match="order"):
        accounting.replay([trade("a", "sell", 5, 110, 1),
                           trade("b", "sell", 10, 120, 1)], opening)


@pytest.mark.parametrize("field,value", [("quantity", -2), ("quantity", 2.5),
    ("price", float("nan")), ("price", 0), ("quantity", True)])
def test_invalid_trade_values_are_rejected(field, value):
    with pytest.raises(ValueError):
        accounting.replay([{**trade("a", "buy", 10, 100, 1), field: value}])


def test_audit_separates_quantity_and_realized_differences():
    fills = [trade("a", "buy", 10, 100, 1), trade("b", "sell", 5, 110, 2)]
    snapshot = [{"symbol": "PORT", "quantity": 5, "average_price": 100, "realized_pnl": 40}]
    report = accounting.audit(fills, snapshot)
    assert report["positions_match"] is True
    assert report["realized_difference"] == -10
    assert report["symbols"]["PORT"]["quantity_difference"] == 0
    assert report["symbols"]["PORT"]["average_price_difference"] == 0
