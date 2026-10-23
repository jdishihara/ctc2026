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
            if self.path == "/api/v1/positions":
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
