"""Mock of the exchange API that replays one research season, to exercise bot/live.py without the testnet.

    python scripts/mock_exchange.py --season 451 --speed 20 --port 8765
    python bot/live.py --url http://localhost:8765 --key test

Serves GET /cases/hurricane.json, /api/v1/competitions/time, /positions, /orders/open; POST /orders fills at the
house quote immediately; DELETE /orders/all; POST /etf/.../create|redeem. Streams quote and news frames on
/ws/v1/market-data at `speed` times real time. Response shapes are our guess at the real API: adjust after a
testnet session.
"""
from __future__ import annotations
import argparse, asyncio, json, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import websockets
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc.sim import Sim

ROOT = Path(__file__).resolve().parents[1] / "data"
STATE = {"mid": {}, "half_spread": 0.0015, "position": {}, "cash": 0.0, "fills": 0, "open": True, "lock": threading.Lock(), "case": None}


class H(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == "/cases/hurricane.json":
            return self._json(STATE["case"])
        if self.path.startswith("/api/v1/competitions/time"):
            return self._json({"state": "running" if STATE["open"] else "paused"})
        if self.path.startswith("/api/v1/positions"):
            with STATE["lock"]:
                return self._json({"positions": [{"symbol": s, "quantity": q} for s, q in STATE["position"].items()]})
        if self.path.startswith("/api/v1/orders/open"):
            return self._json({"orders": []})
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/v1/orders":
            sym, side, qty = body["symbol"], body["side"], int(body["quantity"])
            with STATE["lock"]:
                mid = STATE["mid"].get(sym)
                if mid is None:
                    return self._json({"error": "no market"}, 400)
                px = mid * (1 + STATE["half_spread"]) if side == "buy" else mid * (1 - STATE["half_spread"])
                if body.get("order_type") == "limit" and ((side == "buy" and body["price"] < px) or (side == "sell" and body["price"] > px)):
                    return self._json({"order_id": STATE["fills"] + 1000, "status": "resting"})
                lim = STATE["case"]["limits"][sym]; sign = 1 if side == "buy" else -1
                pos = STATE["position"].get(sym, 0)
                qty = min(qty, lim - sign * pos)
                if qty <= 0:
                    return self._json({"error": "position limit"}, 400)
                STATE["position"][sym] = pos + sign * qty; STATE["cash"] -= sign * qty * px; STATE["fills"] += 1
                return self._json({"order_id": STATE["fills"], "status": "filled", "filled_quantity": qty, "price": px})
        if "/etf/" in self.path:
            return self._json({"status": "ok"})
        self._json({"error": "not found"}, 404)

    def do_DELETE(self):
        self._json({"status": "ok"})


async def stream(sim: Sim, speed: float, port: int):
    clients = set()

    async def handler(ws):
        clients.add(ws)
        try:
            await ws.recv()   # subscribe
            await ws.wait_closed()
        finally:
            clients.discard(ws)

    async with websockets.serve(handler, "localhost", port + 1):
        print(f"ws on ws://localhost:{port + 1}/ws/v1/market-data  (http on {port})", flush=True)
        t0 = time.time(); last_t = 0.0
        for t, _, kind, payload in sim.events:
            wait = (t - last_t) / speed - (time.time() - t0)
            if wait > 0:
                await asyncio.sleep(wait)
            t0 = time.time(); last_t = t
            if kind == "price":
                with STATE["lock"]:
                    STATE["mid"] = payload
                frames = [json.dumps({"type": "quote", "symbol": s, "bid": p * (1 - STATE["half_spread"]), "ask": p * (1 + STATE["half_spread"])}) for s, p in payload.items()]
            else:
                frames = [json.dumps({"type": "news", "message": payload})]
            for ws in list(clients):
                for f in frames:
                    try:
                        await ws.send(f)
                    except Exception:
                        clients.discard(ws)
        STATE["open"] = False
        with STATE["lock"]:
            pnl = STATE["cash"] + sum(q * sim.settlement[s] for s, q in STATE["position"].items())
            print(f"season over: fills {STATE['fills']}, settlement pnl {pnl:.0f}", flush=True)
        await asyncio.sleep(5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=451); ap.add_argument("--speed", type=float, default=20.0); ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    case = json.loads((ROOT / "case.json").read_text()); man = json.loads((ROOT / "history" / "manifest.json").read_text())
    STATE["case"] = case
    sim = Sim(ROOT / "history" / man["seasons"][a.season - 1]["dir"], case)
    srv = ThreadingHTTPServer(("localhost", a.port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    asyncio.run(stream(sim, a.speed, a.port))
    srv.shutdown()


if __name__ == "__main__":
    main()
