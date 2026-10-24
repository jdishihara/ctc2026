"""Mock of the exchange for Mario Markets: the live exchange's 23 contracts per series (TOP_PEA, RACE1_PEA, SCORE_1ST, ...
under a competition named "Mario Kart Series N", switching to series 2 after race 4 with the same symbol names), a house
market maker with its own (imperfect) view, a hidden tournament that advances one race every --race-every seconds,
settlements, and the /api/v1 shapes the real UI uses. --legacy-symbols serves the old 46-contract scheme (R1_BIRDO ...).

    python3 mario/mock_exchange.py --port 8790 --race-every 60 --seed 3
    python3 mario/desk.py --mock --auto-results          # the desk reads it over HTTP (or --tap browser, same page)

Endpoints: GET /api/v1/symbols, /api/v1/orderbook/{sym}, /api/v1/positions, /api/v1/orders/open, /api/v1/trades,
/api/v1/competitions/current, /api/v1/teams/me; POST /api/v1/orders {symbol, side, quantity, price} fills the
marketable part against the house book (no resting orders). GET /mock/results lists completed races (overall places of
BIRDO DAISY PEACH YOSHI). GET / serves a stub page with the live UI's structure (group tabs, outcome rows, BUY/SELL,
Limit, #order-qty, #order-price, a "Buy 20 TOP_PEA" button, "X is halted" while halted) so mario/tap.py's browser mode
can be drilled here.
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

SYMBOLS: dict[str, tuple] = {}                 # every contract of the tournament, keyed by an internal name
for r in range(1, 9):
    for h in RACERS:
        SYMBOLS[f"R{r}_{h}"] = ("race", r, h)
for s in (1, 2):
    for h in RACERS:
        SYMBOLS[f"S{s}_WIN_{h}"] = ("swin", s, h)
    SYMBOLS[f"S{s}_NO1"] = ("s1", s); SYMBOLS[f"S{s}_NO2"] = ("s2", s); SYMBOLS[f"S{s}_TOP2"] = ("top2", s)
LEGACY = False                                 # --legacy-symbols: serve the internal names for every series at once
TICK = {"race": 1.0, "swin": 1.0, "s1": 0.01, "s2": 0.01, "top2": 0.01}
MAX_PRICE = {"race": 100.0, "swin": 100.0, "s1": 60.0, "s2": 54.0, "top2": 108.0}


def live_name(role: tuple) -> tuple[str, str, str]:
    """(symbol, name, group) as the live exchange lists this contract within its own series."""
    if role[0] == "race":
        r = (role[1] - 1) % 4 + 1
        return f"RACE{r}_{role[2][:3]}", f"Race {r} Winner: {role[2].title()}", f"RACE{r}"
    if role[0] == "swin":
        return f"TOP_{role[2][:3]}", f"Top Scorer: {role[2].title()}", "TOP"
    return {"s1": ("SCORE_1ST", "Top Scorer's Total Points", "SCORE"), "s2": ("SCORE_2ND", "Second Scorer's Total Points", "SCORE"),
            "top2": ("SCORE_TOP2SUM", "Sum of the Top Two Totals", "SCORE")}[role[0]]


def current_series(n_done: int) -> int:
    return 1 if n_done < 4 else 2


def listed(n_done: int) -> dict[str, str]:
    """external symbol -> internal name for the series on display (all of them with --legacy-symbols)."""
    if LEGACY:
        return {s: s for s in SYMBOLS}
    s = current_series(n_done)
    return {live_name(role)[0]: name for name, role in SYMBOLS.items() if series_of(role) == s}


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
        self.halted = False
        self.start = time.time(); self.next_race = self.start + race_every
        self._reprice(new_race=True)

    def internal(self, ext: str) -> str:
        """The internal name of an external (live-scheme) symbol of the series on display; unknown names pass through."""
        with self.lock:
            n = len(self.results)
        return listed(n).get(ext, ext)

    def external(self, sym: str) -> str:
        if LEGACY:
            return sym
        return live_name(SYMBOLS[sym])[0]

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
        tick = 0.1 if LEGACY else TICK[role[0]]
        lo, hi = tick, (100.0 if role[0] in ("race", "swin") else 120.0) if LEGACY else MAX_PRICE[role[0]]
        on_tick = lambda x: round(round(x / tick) * tick, 2)
        bids, asks = [], []
        for i in range(4):
            bp = on_tick(max(lo, fv - half - 1.5 * i)); ap = on_tick(min(hi, fv + half + 1.5 * i))
            q = 10 + (abs(hash(sym + str(i))) % 31)
            bids.append({"price": bp, "quantity": q}); asks.append({"price": ap, "quantity": q})
        bids = [b for b in bids if b["price"] >= lo]; asks = [a for a in asks if a["price"] <= hi]
        if bids and asks and bids[0]["price"] >= asks[0]["price"]:
            asks[0]["price"] = on_tick(bids[0]["price"] + tick)
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
                self.trades.append({"trade_id": uuid.uuid4().hex, "symbol": self.external(sym), "side": side, "quantity": take, "price": lv["price"], "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
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
                out.append({"symbol": self.external(sym), "quantity": p["quantity"], "average_price": round(p["average_price"], 2),
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
                if n == 4 and not LEGACY:
                    print("competition is now 'Mario Kart Series 2': the same symbol names, series 2 contracts", flush=True)
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
                print(f"  settled {self.external(sym)} (S{series_of(role)}) at {v:.0f}", flush=True)


WORLD: World | None = None
PAGE = r"""<!doctype html><title>Mario mock</title><body style='font-family:sans-serif;background:#0f172a;color:#eee'>
<h3>Mario Markets mock exchange (the live UI's structure: group tabs, outcome rows, the order form's ids and buttons)</h3>
<div id=comp></div><div id=groups></div><div id=rows></div><div id=order></div><pre id=out></pre>
<script>
let side='buy', sym=null, group=null, symbols=[];
function el(tag, text, onclick){const b=document.createElement(tag); b.textContent=text; if(onclick) b.onclick=onclick; return b}
function renderGroups(){const g=document.getElementById('groups'); g.innerHTML='';
  [...new Set(symbols.map(s=>s.group))].forEach(k=>{g.appendChild(el('button', k, ()=>{group=k; sym=null; renderRows(); renderOrder()})); g.append(' ')})}
function renderRows(){const r=document.getElementById('rows'); r.innerHTML='';
  symbols.filter(s=>s.group===group).forEach(s=>{const b=el('button', s.name+' '+s.symbol, ()=>{sym=s.symbol; renderOrder()}); b.style.display='block'; r.appendChild(b)})}
function renderOrder(){const o=document.getElementById('order'); o.innerHTML=''; if(!sym){o.textContent='Pick an outcome'; return}
  const s=symbols.find(x=>x.symbol===sym);
  if(s.settlement_active){o.textContent='Settled at '+Number(s.settlement_price).toFixed(2)+' · orders rejected'; return}
  if(s.trading_halted){o.textContent=sym+' is halted · orders rejected'; return}
  const p=document.createElement('p'); p.appendChild(el('button','BUY',()=>{side='buy'; lbl()})); p.append(' '); p.appendChild(el('button','SELL',()=>{side='sell'; lbl()}));
  p.append(' '); p.appendChild(el('button','Limit')); p.append(' '); p.appendChild(el('button','Market')); o.appendChild(p);
  const q=document.createElement('p'); q.innerHTML='Qty <input id=order-qty placeholder=1> Price <input id=order-price placeholder=1.00> '; const sb=el('button','', send); sb.id='submit'; q.appendChild(sb); o.appendChild(q); lbl()}
function lbl(){const b=document.getElementById('submit'); if(b) b.textContent=(side==='buy'?'Buy':'Sell')+' '+(document.getElementById('order-qty').value||'')+' '+(sym||'')}
document.addEventListener('input', e=>{if(e.target.id==='order-qty') lbl()});
async function refresh(){const d=await (await fetch('/api/v1/symbols')).json(); const c=await (await fetch('/api/v1/competitions/current')).json();
  const changed=JSON.stringify(d.symbols.map(s=>[s.symbol,s.trading_halted,s.settlement_active]))!==JSON.stringify(symbols.map(s=>[s.symbol,s.trading_halted,s.settlement_active]));
  symbols=d.symbols; document.getElementById('comp').textContent=c.name+' ('+c.state+')';
  if(changed){ if(!symbols.some(s=>s.group===group)) group=symbols.length?symbols[0].group:null; renderGroups(); renderRows(); if(sym && !symbols.some(s=>s.symbol===sym)) sym=null; renderOrder()}}
async function send(){const b={symbol:sym,side:side,quantity:+document.getElementById('order-qty').value,price:+document.getElementById('order-price').value};
  const r=await fetch('/api/v1/orders',{method:'POST',body:JSON.stringify(b)}); document.getElementById('out').textContent=JSON.stringify(b)+' -> '+await r.text()}
refresh(); setInterval(refresh, 1000);
</script>""".encode()


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
            with w.lock:
                n = len(w.results)
            out = []
            for ext, s in listed(n).items():
                r = SYMBOLS[s]
                if LEGACY:
                    rec = {"symbol": s, "name": s.replace("_", " "), "symbol_type": "binary" if r[0] in ("race", "swin") else "score", "tick_size": 0.1,
                           "min_price": 0.1, "max_price": 100.0 if r[0] in ("race", "swin") else 120.0, "group": f"Series {series_of(r)}", "market_name": "Mario Markets"}
                else:
                    name, nm, grp = live_name(r)
                    rec = {"symbol": ext, "name": nm, "symbol_type": "equity", "tick_size": TICK[r[0]], "min_price": TICK[r[0]], "max_price": MAX_PRICE[r[0]], "group": grp,
                           "lot_size": 1, "market_id": None, "market_name": None, "competition_id": "mock-mario", "competition_name": None, "message": None}
                rec.update({"max_position": LIMITS[r[0]], "settlement_active": s in w.settled, "settlement_price": w.settled.get(s), "trading_halted": w.halted})
                out.append(rec)
            return self._json({"symbols": out})
        if path.startswith("/api/v1/orderbook/"):
            sym = w.internal(path.rsplit("/", 1)[1])
            return self._json(w.book(sym)) if sym in SYMBOLS else self._json({"detail": "Not Found"}, 404)
        if path == "/api/v1/positions":
            return self._json({"positions": w.positions()})
        if path == "/api/v1/orders/open":
            return self._json({"orders": []})
        if path.startswith("/api/v1/trades"):
            return self._json({"trades": list(reversed(w.trades[-100:]))})
        if path == "/api/v1/competitions/current":
            with w.lock:
                n = len(w.results)
            name = "Mario Markets" if LEGACY else f"Mario Kart Series {current_series(n)}"
            return self._json({"competition_id": "mock-mario", "name": name, "state": "running", "elapsed_active_seconds": int(time.time() - w.start),
                               "fictional_time": time.strftime("%Y-%m-%dT%H:%M:%S"), "clock_rate": 1.0})
        if path == "/api/v1/teams/me":
            return self._json({"team": "mock", "members": []})
        if path == "/mock/results":
            return self._json({"results": w.results, "next_race_in": max(0, round(w.next_race - time.time())), "true_skill": dict(zip(RACERS, w.true_h.round(2).tolist()))})
        self._json({"detail": "Not Found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/v1/orders":
            sym = WORLD.internal(body["symbol"])
            if sym not in SYMBOLS:
                return self._json({"detail": f"unknown symbol {body['symbol']}"}, 404)
            if WORLD.halted:
                return self._json({"detail": f"{body['symbol']} is halted"}, 400)
            return self._json(WORLD.order(sym, body["side"].lower(), int(body["quantity"]), body.get("price")))
        self._json({"detail": "Not Found"}, 404)


def main():
    global WORLD
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8790); ap.add_argument("--race-every", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=0); ap.add_argument("--house-bias", type=float, default=4.0)
    ap.add_argument("--cpu-skill", type=float, default=-0.6, help="true CPU strength (the house and the desk assume -0.6)")
    ap.add_argument("--legacy-symbols", action="store_true", help="serve the old 46-contract scheme (R1_BIRDO, S1_WIN_PEACH, ...) instead of the live one")
    ap.add_argument("--halted-for", type=float, default=0.0, help="start halted (no order form, orders rejected) for this many seconds, like the live open")
    a = ap.parse_args()
    global LEGACY
    LEGACY = a.legacy_symbols
    WORLD = World(a.seed, a.race_every, a.house_bias, a.cpu_skill)
    WORLD.halted = a.halted_for > 0
    if WORLD.halted:
        threading.Timer(a.halted_for, lambda: setattr(WORLD, "halted", False)).start()
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
