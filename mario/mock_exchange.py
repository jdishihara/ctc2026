"""Mock of the exchange for Mario Markets: 46 contracts, a house market maker with its own (imperfect) view, a hidden
tournament that advances one race every --race-every seconds, settlements, and the /api/v1 shapes the real UI uses.

    python3 mario/mock_exchange.py --port 8790 --race-every 60 --seed 3
    python3 mario/desk.py --mock --auto-results          # the desk reads it over HTTP (or --tap browser, same page)

Endpoints: GET /api/v1/symbols, /api/v1/orderbook/{sym}, /api/v1/positions, /api/v1/orders/open, /api/v1/trades,
/api/v1/competitions/current, /api/v1/teams/me; POST /api/v1/orders {symbol, side, quantity, price} fills the
marketable part against the house book (no resting orders). GET /mock/results lists completed races (overall places of
BIRDO DAISY PEACH YOSHI). GET / serves a stub page so mario/tap.py's browser mode can be tested here.
The house: a Pricer with another seed, a per-contract bias redrawn every race (sd --house-bias), a random-walk jitter,
spread 2-6 points and 10-40 contracts per level, and deliberately leaves the binary sets a few points away from 100.
"""
from __future__ import annotations
import argparse, json, sys, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mario.pricer import Pricer, POINTS
from mario.contracts import RACERS, LIMITS, series_of

SYMBOLS: dict[str, tuple] = {}
for r in range(1, 9):
    for h in RACERS:
        SYMBOLS[f"R{r}_{h}"] = ("race", r, h)
for s in (1, 2):
    for h in RACERS:
        SYMBOLS[f"S{s}_WIN_{h}"] = ("swin", s, h)
    SYMBOLS[f"S{s}_NO1"] = ("s1", s); SYMBOLS[f"S{s}_NO2"] = ("s2", s); SYMBOLS[f"S{s}_TOP2"] = ("top2", s)


class World:
    def __init__(self, seed: int, race_every: float, house_bias: float, cpu_skill: float):
        self.rng = np.random.default_rng(seed)
        self.lock = threading.Lock()
        self.race_every = race_every
        self.true_h = self.rng.normal(0, 1.0, 4); self.true_c = self.rng.normal(cpu_skill, 0.5, 8)
        self.results: list[list[int]] = []
        self.house = Pricer(n_particles=2000, n_sims=1000, cpu_skill=cpu_skill, seed=seed + 1)
        self.bias = {s: 0.0 for s in SYMBOLS}; self.house_bias = house_bias
        self.jitter = {s: 0.0 for s in SYMBOLS}
        self.fair = {}; self.settled: dict[str, float] = {}
        self.pos = {s: {"quantity": 0, "average_price": 0.0, "realized_pnl": 0.0} for s in SYMBOLS}
        self.trades: list[dict] = []
        self.start = time.time(); self.next_race = self.start + race_every
        self._reprice(new_race=True)

    def _reprice(self, new_race: bool) -> None:
        f = self.house.fairs()
        for sym, role in SYMBOLS.items():
            if sym in self.settled:
                continue
            if new_race:
                self.bias[sym] = self.rng.normal(0, self.house_bias)
            self.jitter[sym] = 0.8 * self.jitter[sym] + self.rng.normal(0, 0.7)
            if role[0] == "race":
                v = 100 * f[("race", role[1])][RACERS.index(role[2])]
            elif role[0] == "swin":
                v = f[("swin", role[1])][RACERS.index(role[2])]
            else:
                v = f[(role[0], role[1])][0]
            self.fair[sym] = v + self.bias[sym] + self.jitter[sym]

    def book(self, sym: str) -> dict:
        if sym in self.settled:
            return {"symbol": sym, "bids": [], "asks": [], "last_update": None}
        fv = self.fair[sym]; role = SYMBOLS[sym]
        half = (1.0 if role[0] in ("race", "swin") else 1.5) + abs(hash(sym)) % 3 * 0.5
        lo, hi = (0.0, 100.0) if role[0] in ("race", "swin") else (0.0, 120.0)
        bids, asks = [], []
        for i in range(4):
            bp = round(max(lo + 0.5, fv - half - 1.5 * i), 1); ap = round(min(hi - 0.5, fv + half + 1.5 * i), 1)
            q = 10 + (abs(hash(sym + str(i))) % 31)
            bids.append({"price": bp, "quantity": q}); asks.append({"price": ap, "quantity": q})
        return {"symbol": sym, "bids": bids, "asks": asks, "last_update": time.strftime("%Y-%m-%dT%H:%M:%S")}

    def order(self, sym: str, side: str, qty: int, price: float | None) -> dict:
        with self.lock:
            if sym in self.settled:
                return {"error": "settled"}
            b = self.book(sym); levels = b["asks"] if side == "buy" else b["bids"]
            p = self.pos[sym]; lim = LIMITS[SYMBOLS[sym][0]]
            room = lim - p["quantity"] if side == "buy" else lim + p["quantity"]
            filled, cost = 0, 0.0
            for lv in levels:
                if price is not None and ((side == "buy" and lv["price"] > price) or (side == "sell" and lv["price"] < price)):
                    break
                take = min(lv["quantity"], qty - filled, room - filled)
                if take <= 0:
                    break
                filled += take; cost += take * lv["price"]
                self.trades.append({"trade_id": uuid.uuid4().hex, "symbol": sym, "side": side, "quantity": take, "price": lv["price"], "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
            if filled:
                self._apply(sym, filled if side == "buy" else -filled, cost / filled)
                self.fair[sym] += (0.15 * filled / 10) * (1 if side == "buy" else -1)   # the house skews against us
            return {"order_id": uuid.uuid4().hex, "filled_quantity": filled, "status": "filled" if filled == qty else "partial"}

    def _apply(self, sym: str, dq: int, px: float) -> None:
        p = self.pos[sym]; q0 = p["quantity"]
        if q0 == 0 or (q0 > 0) == (dq > 0):
            p["average_price"] = (abs(q0) * p["average_price"] + abs(dq) * px) / (abs(q0) + abs(dq))
        else:
            closed = min(abs(q0), abs(dq)); p["realized_pnl"] += closed * (px - p["average_price"]) * (1 if q0 > 0 else -1)
            if abs(dq) > abs(q0):
                p["average_price"] = px
        p["quantity"] = q0 + dq

    def positions(self) -> list[dict]:
        out = []
        for sym, p in self.pos.items():
            if p["quantity"] or p["realized_pnl"]:
                mark = self.settled.get(sym, self.fair.get(sym, 0.0))
                out.append({"symbol": sym, "quantity": p["quantity"], "average_price": round(p["average_price"], 2),
                            "realized_pnl": round(p["realized_pnl"], 2), "unrealized_pnl": round(p["quantity"] * (mark - p["average_price"]), 2)})
        return out

    def tick(self) -> None:
        now = time.time()
        with self.lock:
            if now >= self.next_race and len(self.results) < 8:
                perf = np.concatenate([self.true_h, self.true_c]) + self.rng.normal(0, 1.0, 12)
                place = (np.argsort(np.argsort(-perf)) + 1)[:4].tolist()
                self.results.append(place); self.house.add_race(place); n = len(self.results)
                print(f"RACE {n} finished: places {dict(zip(RACERS, place))}", flush=True)
                self._settle(n); self._reprice(new_race=True); self.next_race = now + self.race_every
            else:
                self._reprice(new_race=False)

    def _settle(self, n: int) -> None:
        f = self.house.fairs()
        for sym, role in SYMBOLS.items():
            if sym in self.settled:
                continue
            v = None
            if role[0] == "race" and role[1] == n:
                v = 100.0 * f[("race", n)][RACERS.index(role[2])]
            elif role[0] == "swin" and role[1] * 4 == n:
                v = float(f[("swin", role[1])][RACERS.index(role[2])])
            elif role[0] in ("s1", "s2", "top2") and role[1] * 4 == n:
                v = float(f[(role[0], role[1])][0])
            if v is not None:
                self.settled[sym] = v; p = self.pos[sym]
                if p["quantity"]:
                    p["realized_pnl"] += p["quantity"] * (v - p["average_price"]); p["quantity"] = 0
                print(f"  settled {sym} at {v:.0f}", flush=True)


WORLD: World | None = None
PAGE = ("<!doctype html><title>Mario mock</title><body style='font-family:sans-serif;background:#0f172a;color:#eee'>"
        "<h3>Mario Markets mock exchange (order form copies the real UI's ids and buttons)</h3><div id=tabs></div>"
        "<p><button onclick=\"side='buy'\">BUY</button> <button onclick=\"side='sell'\">SELL</button> <button>Limit</button> <button>Market</button></p>"
        "<p>Qty <input id=order-qty placeholder=1> Price <input id=order-price placeholder=1.00> <button id=submit onclick='send()'>Buy</button></p><pre id=out></pre>"
        "<script>let side='buy',sym=null;fetch('/api/v1/symbols').then(r=>r.json()).then(d=>{const t=document.getElementById('tabs');"
        "d.symbols.forEach(s=>{const b=document.createElement('button');b.textContent=s.symbol;b.onclick=()=>{sym=s.symbol;document.getElementById('submit').textContent=side+' '+s.symbol};t.appendChild(b);t.append(' ')})});"
        "async function send(){const b={symbol:sym,side:side,quantity:+document.getElementById('order-qty').value,price:+document.getElementById('order-price').value};"
        "const r=await fetch('/api/v1/orders',{method:'POST',body:JSON.stringify(b)});document.getElementById('out').textContent=JSON.stringify(b)+' -> '+await r.text()}</script>").encode()


class H(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a): pass

    def do_GET(self):
        w = WORLD; path = self.path.split("?")[0]
        if path in ("/", "/trading"):
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(PAGE))); self.end_headers(); self.wfile.write(PAGE); return
        if path == "/api/v1/symbols":
            return self._json({"symbols": [{"symbol": s, "name": s.replace("_", " "), "symbol_type": "binary" if r[0] in ("race", "swin") else "score",
                                            "tick_size": 0.1, "max_position": LIMITS[r[0]], "settlement_active": s in w.settled,
                                            "settlement_price": w.settled.get(s), "group": f"Series {series_of(r)}", "market_name": "Mario Markets"} for s, r in SYMBOLS.items()]})
        if path.startswith("/api/v1/orderbook/"):
            sym = path.rsplit("/", 1)[1]
            return self._json(w.book(sym)) if sym in SYMBOLS else self._json({"detail": "Not Found"}, 404)
        if path == "/api/v1/positions":
            return self._json({"positions": w.positions()})
        if path == "/api/v1/orders/open":
            return self._json({"orders": []})
        if path.startswith("/api/v1/trades"):
            return self._json({"trades": list(reversed(w.trades[-100:]))})
        if path == "/api/v1/competitions/current":
            return self._json({"competition_id": "mock-mario", "name": "Mario Markets", "state": "running", "elapsed_active_seconds": int(time.time() - w.start)})
        if path == "/api/v1/teams/me":
            return self._json({"team": "mock", "members": []})
        if path == "/mock/results":
            return self._json({"results": w.results, "next_race_in": max(0, round(w.next_race - time.time())), "true_skill": dict(zip(RACERS, w.true_h.round(2).tolist()))})
        self._json({"detail": "Not Found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/v1/orders":
            return self._json(WORLD.order(body["symbol"], body["side"].lower(), int(body["quantity"]), body.get("price")))
        self._json({"detail": "Not Found"}, 404)


def main():
    global WORLD
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8790); ap.add_argument("--race-every", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=0); ap.add_argument("--house-bias", type=float, default=4.0)
    ap.add_argument("--cpu-skill", type=float, default=-0.6, help="true CPU strength (the house and the desk assume -0.6)")
    a = ap.parse_args()
    WORLD = World(a.seed, a.race_every, a.house_bias, a.cpu_skill)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"mock Mario exchange on http://127.0.0.1:{a.port}  (race every {a.race_every:.0f} s; true human skills {dict(zip(RACERS, WORLD.true_h.round(2).tolist()))})", flush=True)
    try:
        while True:
            WORLD.tick(); time.sleep(1.0)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
