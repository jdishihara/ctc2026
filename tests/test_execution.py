import json
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import patch

import pytest

from bot.live import LiveExchange
from ctc.sim import Sim
from ctc.strategies import FairValueTrader

CASE = json.loads((Path(__file__).resolve().parents[1] / "data/case.json").read_text())


class ScriptedExchange(LiveExchange):
    """Replace only external HTTP; exercise real account/order/strategy logic."""
    def __init__(self):
        self.responses = {
            "/cases/hurricane.json": CASE,
            "/competitions/time": {"state": "running", "competition_id": "season-1"},
            "/positions": {"positions": [{"symbol": "PORT", "quantity": 10,
                "average_price": 100, "realized_pnl": 20, "unrealized_pnl": -10}]},
            "/orders/open": {"orders": []},
            "/trades": {"trades": []},
        }
        super().__init__("http://example.invalid", "test-only", False)
        self.refresh()

    def get(self, path, api=True):
        value = self.responses[path if path in self.responses else path.partition('?')[0]]
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def exchange():
    return ScriptedExchange()


def order(side="buy", qty=100):
    return {"symbol": "PORT", "side": side, "quantity": qty,
            "filled_quantity": 0, "order_id": "old", "price": 100}


def test_live_liquidity_subtracts_our_resting_size_and_respects_limit(exchange):
    exchange.responses['/orderbook/PORT'] = {'asks': [{'price': 100, 'quantity': 20},
        {'price': 101, 'quantity': 30}], 'bids': [{'price': 99, 'quantity': 40}]}
    exchange.open_orders = [{**order('sell', 8), 'filled_quantity': 3}]
    assert exchange.liquidity('PORT', 'buy', 100.5) == 15
    assert exchange.liquidity('PORT', 'buy', 101) == 45
    assert exchange.liquidity('PORT', 'sell', 98) == 40


@pytest.mark.parametrize('book', [OSError('offline'), IncompleteRead(b'partial', 100), {'asks': [{'price': 100, 'quantity': float('nan')}]},
                                  {'asks': [{'price': 100, 'quantity': -1}]}, {'asks': []}])
def test_live_missing_or_invalid_depth_never_manufactures_capacity(exchange, book):
    exchange.responses['/orderbook/PORT'] = book
    assert not exchange.liquidity('PORT', 'buy', 100.5)


def test_failed_cancel_preserves_reservation(exchange):
    exchange.open_orders = [order()]
    with patch.object(exchange, "send", return_value=None):
        assert exchange.cancel_all("PORT") is False
    assert exchange.resting("PORT", "buy") == 100


def test_successful_empty_cancel_ack_clears_only_requested_symbol(exchange):
    exchange.open_orders = [order(), {**order(), "symbol": "GRID"}]
    exchange.responses["/orders/open"] = {"orders": [{**order(), "symbol": "GRID"}]}
    with patch.object(exchange, "send", return_value={}):
        assert exchange.cancel_all("PORT") is True
    assert exchange.resting("PORT", "buy") == 0
    assert exchange.resting("GRID", "buy") == 100


def test_rate_limited_cancel_preserves_reservation(exchange):
    exchange.open_orders = [order()]
    exchange.rate_limit = 0
    assert exchange.cancel_all("PORT") is False
    assert exchange.resting("PORT", "buy") == 100


def test_failed_refresh_blocks_trading_until_complete_reconciliation(exchange):
    exchange.responses["/orders/open"] = TimeoutError("account unavailable")
    exchange.responses["/positions"]["positions"][0]["quantity"] = 150
    exchange.refresh()
    assert exchange.position["PORT"] == 10  # A partial snapshot must not leak into live state.
    with patch.object(exchange, "send", return_value={"order_id": "new", "filled_quantity": 1}):
        assert exchange.place("PORT", "buy", 1, 90) is None
        assert exchange.create("ARCH", 1) is False
        assert exchange.redeem("ARCH", 1) is False
    exchange.responses["/orders/open"] = {"orders": []}
    exchange.refresh()
    with patch.object(exchange, "send", return_value={"order_id": "new", "filled_quantity": 1}):
        assert exchange.place("PORT", "buy", 1, 90) == "new"
    assert exchange.position["PORT"] == 151


def test_empty_positions_clear_previous_account_state(exchange):
    exchange.responses["/positions"] = {"positions": []}
    exchange.refresh()
    assert exchange.position["PORT"] == 0
    assert exchange.pnl_now == 0


def test_refresh_keeps_realized_pnl_from_closed_positions(exchange):
    exchange.responses['/positions'] = {'positions': []}
    exchange.responses['/positions?include_zero=true'] = {'positions': [
        {'symbol': 'PORT', 'quantity': 0, 'average_price': None,
         'current_price': 86.03, 'unrealized_pnl': None, 'realized_pnl': 20.37}
    ]}
    exchange.refresh()
    assert exchange.state_ready
    assert exchange.position['PORT'] == 0
    assert exchange.pnl_now == 20
    assert exchange.last_positions['realized_by'] == {'PORT': 20}


def test_fill_audit_uses_our_side_when_we_are_the_passive_seller(exchange, capsys):
    exchange.mid["PORT"] = 100
    exchange.responses["/trades"] = {"trades": [{"trade_id": "maker-fill",
        "symbol": "PORT", "quantity": 10, "price": 99,
        "aggressor_side": "buy", "buyer_is_me": False}]}
    exchange.poll_trades()
    assert "FILL PORT sell 10 @ 99" in capsys.readouterr().out
    assert exchange.fill_cost == [10, 990]
    exchange.poll_trades()
    assert exchange.fill_cost == [10, 990]  # duplicate history does not double-count


def test_unknown_own_side_does_not_pollute_slippage_audit(exchange, capsys):
    exchange.mid["PORT"] = 100
    exchange.responses["/trades"] = {"trades": [{"trade_id": "unknown-fill",
        "symbol": "PORT", "quantity": 10, "price": 99, "aggressor_side": "buy"}]}
    exchange.poll_trades()
    assert "FILL PORT ? 10 @ 99" in capsys.readouterr().out
    assert exchange.fill_cost == [0, 0]


def test_order_timeout_requires_reconciliation_before_another_order(exchange):
    with patch("bot.live.urllib.request.urlopen", side_effect=TimeoutError("unknown order outcome")):
        assert exchange.place("PORT", "buy", 5, 90) is None
    with patch.object(exchange, "send", return_value={"order_id": "duplicate", "filled_quantity": 5}):
        assert exchange.place("PORT", "buy", 5, 90) is None


def test_zero_capacity_does_not_spend_order_action(exchange):
    exchange.position["PORT"] = CASE["limits"]["PORT"]
    assert exchange.place("PORT", "buy", 1, 90) is None
    assert len(exchange.actions) == 0


def trader(exchange):
    strategy = FairValueTrader(min_edge=0.025, edge_full=0.03, symbols=["PORT"])
    strategy.on_start(exchange)
    strategy.model.round = 3
    strategy.model.storm_reported = True
    strategy.fair = {"PORT": 120}
    exchange.mid = {"PORT": 100}
    exchange.quotes = {"PORT": (99, 101)}
    return strategy


def test_aggressive_replacement_waits_for_successful_cancel(exchange):
    strategy = trader(exchange)
    exchange.open_orders = [order("sell", 30)]
    with patch.object(exchange, "cancel_all", return_value=False), \
            patch.object(exchange, "send", return_value={"order_id": "wrong", "filled_quantity": 1}):
        strategy.on_quotes(exchange)
    # Failure left the existing order and position unchanged; no replacement was submitted.
    assert exchange.position["PORT"] == 10
    assert exchange.open_orders == [order("sell", 30)]
    assert len(exchange.actions) == 0


@pytest.mark.parametrize('position,after_fill,side', [(200, 50, 'sell'), (-200, -50, 'buy')])
def test_fill_during_reduction_cancel_cannot_turn_into_an_unprofitable_addition(exchange, position, after_fill, side):
    strategy = trader(exchange)
    strategy.carry = .5
    strategy.model.round = 1
    strategy.fair = {'PORT': 100.}
    exchange.quotes['PORT'] = (98., 102.)
    exchange.position['PORT'] = position
    exchange.open_orders = [order(side, 200)]
    def filled_during_cancel(symbol):
        exchange.position['PORT'] = after_fill
        exchange.open_orders = []
        return True
    with patch.object(exchange, 'cancel_all', side_effect=filled_during_cancel), \
            patch.object(exchange, 'place') as place:
        strategy.on_quotes(exchange)
    place.assert_not_called()


@pytest.mark.parametrize('cancel_succeeds', [False, True])
def test_stale_order_cancel_requires_confirmed_usable_state_before_replacing(exchange, cancel_succeeds):
    strategy = trader(exchange)
    exchange.position['PORT'] = 10
    exchange.open_orders = [{**order('buy', 190), 'price': 125.}]
    def cancel(symbol):
        if cancel_succeeds:
            exchange.open_orders = []
            exchange.state_ready = False
        return cancel_succeeds
    with patch.object(exchange, 'cancel_all', side_effect=cancel), \
            patch.object(exchange, 'place') as place:
        strategy.on_quotes(exchange)
    place.assert_not_called()


@pytest.mark.parametrize('passive', [False, True])
def test_account_rollover_during_cancel_cannot_trade_old_season_fair(exchange, passive):
    strategy = trader(exchange)
    strategy.passive = .75 if passive else 0
    exchange.open_orders = [order('sell', 30)]
    exchange.responses['/competitions/time']['competition_id'] = 'season-2'
    exchange.responses['/positions'] = {'positions': []}
    with patch.object(exchange, 'send', return_value={}) as send:
        if passive:
            strategy.quote_passive(exchange, 'PORT', 103, 100, 101, 1, .025, 200, 10)
        else:
            strategy.on_quotes(exchange)
    assert [call.args[0] for call in send.call_args_list] == ['DELETE']
    assert not exchange.open_orders and exchange.position['PORT'] == 0


def test_paused_symbol_cancels_resting_quotes_even_during_warmup(exchange):
    strategy = trader(exchange)
    strategy.warmup = 20
    strategy.on_round(exchange)
    strategy.pause(["PORT"])
    exchange.open_orders = [order()]
    with patch.object(exchange, "send", return_value={"cancelled": 1}):
        strategy.on_quotes(exchange)
    assert exchange.resting("PORT", "buy") == 0


def test_simulator_reserves_pending_orders(tmp_path):
    # No market replay is required to exercise the order/latency boundary.
    (tmp_path / "settlement.json").write_text(json.dumps({"PORT": 100}))
    (tmp_path / "market.csv").write_text("time,round,PORT\n")
    (tmp_path / "feed.jsonl").write_text("")
    sim = Sim(tmp_path, {"limits": {"PORT": 200}})
    sim.market_open = True
    sim.place("PORT", "buy", 150, 100)
    sim.place("PORT", "buy", 150, 100)
    assert sum(o.qty for o in sim.pending) == 200
    assert sim.resting("PORT", "buy") == 200
    assert sim.cancel_all("PORT") is True
    assert sim.resting("PORT", "buy") == 0


def test_filled_passive_quote_is_replenished(exchange):
    strategy = trader(exchange)
    strategy.passive = 0.75
    strategy.passive_order["PORT"] = ("buy", 100.99, exchange.t)
    exchange.open_orders = []  # Previous order filled; cached quote metadata is stale.
    with patch.object(exchange, "send", return_value={"order_id": "replacement", "filled_quantity": 0}):
        strategy.quote_passive(exchange, "PORT", 103, 100, 101, 1, 0.025, 200, 10)
    assert exchange.resting("PORT", "buy") > 0


def test_passive_replacement_does_not_ignore_cancel_failure(exchange):
    strategy = trader(exchange)
    strategy.passive = 0.75
    strategy.passive_order["PORT"] = ("sell", 99, exchange.t)
    exchange.open_orders = [order("sell", 30)]
    with patch.object(exchange, "cancel_all", return_value=False), \
            patch.object(exchange, "send", return_value={"order_id": "wrong", "filled_quantity": 1}):
        strategy.quote_passive(exchange, "PORT", 103, 100, 101, 1, 0.025, 200, 10)
    assert exchange.position["PORT"] == 10
    assert exchange.open_orders == [order("sell", 30)]


def test_pause_retries_cancel_after_failure(exchange):
    strategy = trader(exchange)
    strategy.pause(["PORT"])
    exchange.open_orders = [order()]
    with patch.object(exchange, "send", return_value=None):
        strategy.on_quotes(exchange)
    assert exchange.resting("PORT", "buy") == 100
    exchange.t0 -= 2
    with patch.object(exchange, "send", return_value={"cancelled": 1}):
        strategy.on_quotes(exchange)
    assert exchange.resting("PORT", "buy") == 0


@pytest.mark.parametrize("response", [None, {"error": "unavailable"}, {"positions": [{"symbol": "PORT"}]}])
def test_malformed_position_response_blocks_new_orders(exchange, response):
    exchange.responses["/positions"] = response
    exchange.refresh()
    with patch.object(exchange, "send", return_value={"order_id": "wrong", "filled_quantity": 1}):
        assert exchange.place("PORT", "buy", 1, 90) is None
    assert exchange.position["PORT"] == 10


@pytest.mark.parametrize("ack", [{}, [], {"filled_quantity": 0},
    {"order_id": "a", "filled_quantity": -1}, {"order_id": "a", "filled_quantity": 6},
    {"order_id": "a", "quantity": True}, {"order_id": "a", "quantity": 2.5},
    {"order_id": "a", "filled_quantity": True}, {"order_id": "a", "status": "rejected"},
    {"order_id": "a", "status": "filled", "filled_quantity": 0}])
def test_uncertain_order_ack_blocks_further_submissions(exchange, ack):
    with patch.object(exchange, "send", return_value=ack):
        assert exchange.place("PORT", "buy", 5, 90) is None
    with patch.object(exchange, "send", return_value={"order_id": "second", "filled_quantity": 5}):
        assert exchange.place("PORT", "buy", 5, 90) is None
    assert exchange.position["PORT"] == 10


@pytest.mark.parametrize("side,status,position,remaining", [
    ("buy", "filled", 15, 0), ("sell", "filled", 5, 0),
    ("buy", "partial", 12, 3), ("sell", "partial", 8, 3),
    ("buy", "partially_filled", 12, 3), ("sell", "partially_filled", 8, 3),
])
def test_status_only_fill_ack_reconciles_actual_account(exchange, side, status, position, remaining):
    # The real testnet acknowledges fills without quantity/filled_quantity.
    ack = {"order_id": "live-order", "status": status,
           "created_at": "2026-10-23T22:56:37.356530",
           "message": "Placed", "message_type": "success"}
    exchange.responses["/positions"]["positions"][0]["quantity"] = position
    exchange.responses["/orders/open"] = {"orders": [
        {**order(side, 5), "order_id": "live-order", "filled_quantity": 2}
    ] if remaining else []}
    with patch.object(exchange, "send", return_value=ack):
        assert exchange.place("PORT", side, 5, 90) == "live-order"
    assert exchange.position["PORT"] == position
    assert exchange.resting("PORT", side) == remaining
    assert exchange.state_ready


def test_status_only_fill_ack_retains_id_and_blocks_orders_if_refresh_fails(exchange):
    exchange.responses["/positions"] = TimeoutError("account unavailable")
    with patch.object(exchange, "send", return_value={"order_id": "accepted", "status": "filled"}):
        assert exchange.place("PORT", "buy", 5, 90) == "accepted"
        assert exchange.place("PORT", "buy", 5, 90) is None
    assert exchange.position["PORT"] == 10
    assert not exchange.state_ready


def test_truncated_order_response_blocks_trading(exchange):
    with patch("bot.live.urllib.request.urlopen", side_effect=IncompleteRead(b'{"order_id":')):
        assert exchange.place("PORT", "buy", 5, 90) is None
    with patch.object(exchange, "send", return_value={"order_id": "second", "filled_quantity": 5}):
        assert exchange.place("PORT", "buy", 5, 90) is None


def test_refresh_captures_fill_between_account_requests(exchange):
    original_get = exchange.get
    server_position = 10

    def get(path, api=True):
        nonlocal server_position
        if path == "/orders/open":
            server_position = 110  # Existing order filled just before this response.
            return {"orders": []}
        if path.partition('?')[0] == "/positions":
            return {"positions": [{"symbol": "PORT", "quantity": server_position}]}
        return original_get(path, api)

    with patch.object(exchange, "get", side_effect=get):
        exchange.refresh()
    assert exchange.position["PORT"] == 110


def test_successful_cancel_reconciles_fills_that_won_the_race(exchange):
    exchange.open_orders = [order("buy", 100)]
    exchange.responses["/positions"]["positions"][0]["quantity"] = 110
    with patch.object(exchange, "send", return_value={"cancelled": 0}):
        assert exchange.cancel_all("PORT") is True
    assert exchange.position["PORT"] == 110


def test_replacement_uses_position_after_cancel_reconciliation(exchange):
    strategy = trader(exchange)
    strategy.fair = {"PORT": 90}
    exchange.open_orders = [order("buy", 100)]
    exchange.responses["/positions"]["positions"][0]["quantity"] = 110
    server_position = 110

    def send(method, path, body=None):
        nonlocal server_position
        if method == "DELETE":
            return {"cancelled": 0}
        server_position -= body["quantity"]
        return {"order_id": "replacement", "filled_quantity": body["quantity"]}

    with patch.object(exchange, "send", side_effect=send):
        strategy.on_quotes(exchange)
    assert exchange.position["PORT"] == -200
    assert server_position == -200


def test_passive_replacement_rechecks_position_after_cancel(exchange):
    strategy = trader(exchange)
    strategy.passive = 0.75
    exchange.open_orders = [order("buy", 100)]
    exchange.responses["/positions"]["positions"][0]["quantity"] = 110
    with patch.object(exchange, "send", return_value={"cancelled": 0}):
        strategy.quote_passive(exchange, "PORT", 103, 100, 101, 1, 0.025, 200, 10)
    assert exchange.position["PORT"] == 110
    assert exchange.resting("PORT", "buy") == 0
    assert len(exchange.actions) == 1


def test_pausing_cancels_even_when_acknowledgement_was_lost(exchange):
    strategy = trader(exchange)
    exchange.open_orders = []
    exchange.state_ready = False
    strategy.pause(["PORT"])
    with patch.object(exchange, "send", return_value={"cancelled": 1}):
        strategy.on_quotes(exchange)
    assert len(exchange.actions) == 1
