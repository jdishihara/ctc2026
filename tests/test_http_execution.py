"""Exercise HTTP serialization and failure handling against a local-only exchange."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

from bot.live import LiveExchange


def test_http_cancel_rejection_then_empty_success_ack():
    case = json.loads((Path(__file__).resolve().parents[1] / "data/case.json").read_text())
    state = {"orders": [], "reject_cancel": True, "placed": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, value, status=200):
            payload = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == "/cases/hurricane.json":
                return self.reply(case)
            assert self.headers["X-API-Key"] == "local-test-key"
            if self.path == "/api/v1/competitions/time":
                return self.reply({"state": "running", "competition_id": "local-season"})
            if self.path == "/api/v1/positions?include_zero=true":
                return self.reply({"positions": []})
            if self.path == "/api/v1/orders/open":
                return self.reply({"orders": state["orders"]})
            if self.path == "/api/v1/trades":
                return self.reply({"trades": []})
            self.reply({"error": "unknown route"}, 404)

        def do_POST(self):
            assert self.path == "/api/v1/orders"
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["placed"] += 1
            item = {**body, "order_id": str(state["placed"]), "filled_quantity": 0}
            state["orders"].append(item)
            self.reply(item, 201)

        def do_DELETE(self):
            assert self.path == "/api/v1/orders/all?symbol=PORT"
            if state["reject_cancel"]:
                return self.reply({"error": "temporarily unavailable"}, 503)
            state["orders"] = []
            self.send_response(204)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        exchange = LiveExchange(f"http://127.0.0.1:{server.server_port}", "local-test-key", False)
        exchange.refresh()
        assert exchange.place("PORT", "buy", 20, 90.009) == "1"
        assert state["orders"][0]["price"] == 90.0
        assert exchange.cancel_all("PORT") is False
        assert exchange.resting("PORT", "buy") == 20
        assert exchange.place("PORT", "buy", 20, 90) is None
        assert state["placed"] == 1
        state["reject_cancel"] = False
        assert exchange.cancel_all("PORT") is True
        assert exchange.resting("PORT", "buy") == 0
        exchange.refresh()
        assert exchange.place("PORT", "buy", 30, 90) == "2"
        assert exchange.resting("PORT", "buy") == 30
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_replay_mock_reports_own_fills_once(monkeypatch, capsys):
    from scripts import mock_exchange

    case = json.loads((Path(__file__).resolve().parents[1] / "data/case.json").read_text())
    monkeypatch.setattr(mock_exchange, "STATE", {"mid": {"PORT": 100}, "half_spread": .0015,
        "position": {}, "cash": 0., "fills": 0, "trades": [], "open": True,
        "lock": threading.Lock(), "case": case})
    server = ThreadingHTTPServer(("127.0.0.1", 0), mock_exchange.H)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        exchange = LiveExchange(f"http://127.0.0.1:{server.server_port}", "local-test-key", False)
        exchange.refresh()
        assert exchange.place("PORT", "buy", 5) == 1
        exchange.refresh()
        exchange.refresh()
        assert exchange.position["PORT"] == 5
        assert exchange.seen_trades == {1}
        output = capsys.readouterr().out
        assert output.count("FILL PORT buy 5") == 1
        assert "trades poll failed" not in output
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_http_basket_conversion_refresh_and_closing_legs(monkeypatch):
    from ctc.basket import BasketOverlay
    from scripts import mock_exchange
    case = {'limits': {'A': 100, 'B': 100, 'ETF': 100},
            'etfs': {'ETF': {'basket': {'A': 1, 'B': 2}}}, 'timing': {'pre_storm': 60}}
    starting = {'A': 7, 'B': -9, 'ETF': 3}
    prices = {'A': 10, 'B': 20, 'ETF': 60}
    state = {'mid': prices, 'half_spread': .0015, 'position': starting.copy(),
             'cash': 0., 'fills': 0, 'trades': [], 'open': True,
             'lock': threading.Lock(), 'case': case}
    monkeypatch.setattr(mock_exchange, 'STATE', state)
    server = ThreadingHTTPServer(('127.0.0.1', 0), mock_exchange.H)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        exchange = LiveExchange(f'http://127.0.0.1:{server.server_port}', 'local-test-key', False)
        exchange.refresh()
        exchange.mid = prices
        exchange.quotes = {s: (p * .9985, p * 1.0015) for s, p in prices.items()}
        exchange.quote_times = {s: exchange.t for s in prices}
        overlay = BasketOverlay(.005, participation=.5)
        overlay.on_news(exchange, {'type': 'storm', 'age': 60})
        assert overlay.on_quotes(exchange)
        assert not overlay.on_quotes(exchange)
        exchange.refresh()
        assert state['position'] == starting == exchange.position
        assert state['fills'] == 3 and state['cash'] > 90
        assert exchange.seen_trades == {1, 2, 3}
        # A temporary conversion limit failure must be atomic across all legs.
        state['position']['ETF'] = 99
        unchanged = state['position'].copy()
        assert not exchange.create('ETF', 2)
        assert state['position'] == unchanged
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
