"""Mario Markets desk: reads the exchange through the trading UI's own session (mario/tap.py), prices every contract
(mario/pricer.py), ranks the trades (mario/engine.py) and shows them on a local dashboard. The humans enter each race
result (four overall places) and click the orders in the exchange UI; the packet allows bots to assist but not to trade.

    python3 mario/desk.py                         # real exchange: opens a Chrome window, log in there, dashboard on http://localhost:8787
                                                  # "prepare" buttons type the order into the UI's form; you click the button (allowed by the organisers)
    python3 mario/mock_exchange.py --race-every 45 &  ; python3 mario/desk.py --mock --auto-results   # drill against the mock
    python3 mario/desk.py --mock --tap browser    # exercise the browser tap against the mock page

Commands (terminal prompt or the dashboard box): race P1 P2 P3 P4  (overall places of BIRDO DAISY PEACH YOSHI, in
that order) | undo | cpu -0.3 (CPU strength prior; see mario/README.md) | map (symbols and roles) | prepare N
(type action N, leg L, into the Chrome window's order form) | fill SYM buy|sell QTY PX (mock only: sends the order) | q.
Every snapshot and every command is appended to recordings/mario_desk.jsonl.
"""
from __future__ import annotations
import argparse, json, sys, threading, time, traceback, html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mario.pricer import Pricer
from mario.engine import Engine, Params
from mario.contracts import RACERS, load_roles, role_label
from mario.tap import HttpTap, BrowserTap, book_levels

REC = Path(__file__).resolve().parents[1] / "recordings" / "mario_desk.jsonl"


class Desk:
    def __init__(self, a: argparse.Namespace):
        self.a = a
        self.lock = threading.Lock()
        self.pricer = Pricer(cpu_skill=a.cpu_skill, cpu_sd=a.cpu_sd, noise_sd=a.noise, skill_sd=a.skill_sd)
        self.engine: Engine | None = None
        self.params = Params(clip=a.clip, risk_pts=a.risk, min_profit=a.min_profit)
        self.fairs = None; self.snap = None; self.result = None; self.roles = {}; self.unmapped = []
        self.status = "starting"; self.log: list[str] = []; self.last_ok = 0.0
        self.tap = None; self.stop = False
        self.auto_seen = 0
        REC.parent.mkdir(exist_ok=True)

    # ---- state changes ----
    def say(self, msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"; print(line, flush=True)
        self.log.append(line); self.log = self.log[-40:]
        with open(REC, "a") as f:
            f.write(json.dumps({"t": time.time(), "log": msg}) + "\n")

    def refair(self) -> None:
        t0 = time.time(); f = self.pricer.fairs()
        with self.lock:
            self.fairs = f
        n = len(self.pricer.races)
        self.say(f"fairs recomputed after {n} race(s) in {time.time() - t0:.1f} s; skill " + " ".join(f"{h} {s:+.2f}" for h, s in zip(RACERS, f["skill"])))

    def command(self, line: str) -> str:
        line = line.strip(); parts = line.split()
        if not parts:
            return ""
        with open(REC, "a") as f:
            f.write(json.dumps({"t": time.time(), "cmd": line}) + "\n")
        try:
            if parts[0] == "race":
                places = [int(x) for x in parts[1:5]]
                if len(self.pricer.races) >= 8:
                    return "all 8 races are already entered"
                self.pricer.add_race(places); self.refair()
                return f"race {len(self.pricer.races)} recorded: " + " ".join(f"{h} {p}" for h, p in zip(RACERS, places))
            if parts[0] == "undo":
                if not self.pricer.races:
                    return "nothing to undo"
                self.pricer.undo(); self.refair(); return f"last race dropped; {len(self.pricer.races)} race(s) remain"
            if parts[0] == "cpu":
                races = list(self.pricer.races); cs = float(parts[1])
                self.pricer = Pricer(cpu_skill=cs, cpu_sd=self.a.cpu_sd, noise_sd=self.a.noise, skill_sd=self.a.skill_sd)
                for r in races:
                    self.pricer.add_race(r)
                self.refair(); return f"CPU prior set to {cs:+.2f}, {len(races)} race(s) replayed"
            if parts[0] == "map":
                return "\n".join(f"{s:14s} {role_label(r)}" for s, r in sorted(self.roles.items())) + ("\nUNMAPPED: " + " ".join(self.unmapped) if self.unmapped else "")
            if parts[0] == "prepare":
                if not isinstance(self.tap, BrowserTap):
                    return "prepare needs the browser tap"
                if not self.a.prefill:
                    return "prefill is disabled (--no-prefill)"
                acts = self.result["actions"] if self.result else []
                i = int(parts[1]) - 1
                if not 0 <= i < len(acts):
                    return "no such action"
                leg = int(parts[2]) - 1 if len(parts) > 2 else 0
                if not 0 <= leg < len(acts[i].legs):
                    return "no such leg"
                self.pending_prefill = acts[i].legs[leg]; return f"preparing leg {leg + 1}/{len(acts[i].legs)}: {self.pending_prefill} ..."
            if parts[0] == "fill":
                if not isinstance(self.tap, HttpTap):
                    return "fill only works against the mock (HTTP tap)"
                sym, side, qty, px = parts[1], parts[2], int(parts[3]), float(parts[4])
                r = self.tap.post("/api/v1/orders", {"symbol": sym, "side": side, "quantity": qty, "price": px})
                return f"mock fill: {r}"
            if parts[0] in ("q", "quit"):
                self.stop = True; return "stopping"
            return "commands: race P1 P2 P3 P4 | undo | cpu X | map | prepare N [leg] | fill SYM buy QTY PX | q"
        except Exception as exc:
            return f"error: {exc}"

    # ---- tap thread ----
    def run_tap(self) -> None:
        a = self.a
        try:
            if a.tap == "browser":
                self.tap = BrowserTap(a.url, headless=a.headless); self.tap.start()
                self.status = "waiting for login in the Chrome window"
                while not self.stop and not self.tap.ready():
                    time.sleep(1.0)
            else:
                self.tap = HttpTap(a.url, a.key)
                while not self.stop and not self.tap.ready():
                    self.status = f"waiting for {a.url}"; time.sleep(1.0)
            self.status = "connected"; self.say(f"tap connected to {a.url} ({a.tap})")
        except Exception as exc:
            self.status = f"tap failed: {exc}"; self.say(self.status); return
        self.pending_prefill = None
        while not self.stop:
            t0 = time.time()
            try:
                if self.pending_prefill:
                    sym, side, qty, px = self.pending_prefill; self.pending_prefill = None
                    self.say(self.tap.prefill(sym, side, qty, px))
                snap = self.tap.snapshot()
                self.ingest(snap)
                self.last_ok = time.time(); self.status = "connected"
            except Exception as exc:
                self.status = f"poll failed: {exc}"
                if time.time() - self.last_ok > 10:
                    self.say(self.status)
            time.sleep(max(0.0, a.interval - (time.time() - t0)))

    def ingest(self, snap: dict) -> None:
        syms = snap["symbols"]
        if self.engine is None or set(self.roles) != {s["symbol"] for s in syms} - set(self.unmapped):
            self.roles, self.unmapped = load_roles(syms)
            self.engine = Engine(self.roles, self.params)
            self.say(f"{len(self.roles)} contracts mapped" + (f"; UNMAPPED: {' '.join(self.unmapped)} (fix mario/contracts.json)" if self.unmapped else ""))
        if self.a.auto_results:
            try:
                res = self.tap._get("/mock/results")["results"] if isinstance(self.tap, HttpTap) else []
                while len(self.pricer.races) < len(res):
                    self.say("auto: " + self.command("race " + " ".join(map(str, res[len(self.pricer.races)]))))
            except Exception:
                pass
        if self.fairs is None:
            self.refair()
        books = {s: book_levels(b) for s, b in snap["books"].items()}
        positions = {}
        for p in snap.get("positions") or []:
            positions[p["symbol"]] = {"qty": p.get("quantity", p.get("position", 0)), "avg": p.get("average_price"),
                                      "realized": p.get("realized_pnl", 0), "unrealized": p.get("unrealized_pnl", 0)}
        tradable = {s["symbol"] for s in syms if not s.get("settlement_active") and not s.get("trading_halted")}
        with self.lock:
            fairs = self.fairs
        res = self.engine.evaluate(fairs, books, positions, len(self.pricer.races), tradable)
        res["exchange_pnl"] = round(sum(float(p.get("realized") or 0) + float(p.get("unrealized") or 0) for p in positions.values()), 1)
        with self.lock:
            self.snap = snap; self.result = res; self.positions = positions
        with open(REC, "a") as f:
            f.write(json.dumps({"t": snap["t"], "books": snap["books"], "positions": snap.get("positions"), "trades": (snap.get("trades") or [])[:20]}) + "\n")

    # ---- dashboard ----
    def state(self) -> dict:
        with self.lock:
            r = self.result; f = self.fairs
        acts = [{"kind": a.kind, "legs": a.legs, "profit": a.profit, "note": a.note} for a in (r["actions"] if r else [])]
        rows = r["rows"] if r else []
        return {"status": self.status, "age": round(time.time() - self.last_ok, 1) if self.last_ok else None, "races": self.pricer.races,
                "n_done": len(self.pricer.races), "racers": RACERS, "skill": [round(float(x), 2) for x in f["skill"]] if f else None,
                "points": [[int(x) for x in p] for p in f["points"]] if f else None, "rows": rows, "actions": acts[:15],
                "pnl": r["pnl"] if r else None, "exchange_pnl": r.get("exchange_pnl") if r else None, "log": self.log[-12:],
                "unmapped": self.unmapped, "prefill": bool(self.a.prefill), "cpu_skill": self.pricer.cpu_skill}


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Mario desk</title>
<style>body{font-family:-apple-system,Helvetica,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:12px;font-size:13px}
table{border-collapse:collapse;width:100%}th,td{padding:2px 6px;text-align:right;border-bottom:1px solid #1e293b}th{color:#94a3b8;font-weight:600}
td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}.buy{color:#4ade80;font-weight:700}.sell{color:#f87171;font-weight:700}
.arb{background:#422006}.grid{display:grid;grid-template-columns:2fr 1fr;gap:12px}.box{background:#111c34;border-radius:8px;padding:8px 10px;margin-bottom:12px}
h3{margin:0 0 6px;font-size:14px;color:#cbd5e1}input{background:#1e293b;color:#fff;border:1px solid #334155;border-radius:4px;padding:4px 6px;font-size:13px}
button{background:#2563eb;color:#fff;border:0;border-radius:4px;padding:4px 10px;cursor:pointer}pre{white-space:pre-wrap;margin:0;color:#94a3b8;font-size:11px}
.stale{color:#f87171}.dim{color:#64748b}.settled{color:#475569}</style></head><body>
<div class="grid"><div>
<div class="box"><h3>Actions, best first <span id="pnl" class="dim"></span></h3><table id="acts"></table></div>
<div class="box"><h3>Contracts</h3><table id="rows"></table></div></div>
<div><div class="box"><h3>Status <span id="status"></span></h3>
<div>Races: <span id="races"></span></div><div>Skill: <span id="skill"></span></div><div>Points: <span id="points"></span></div>
<form onsubmit="return send()"><input id="cmd" size="34" placeholder="race 1 2 5 9  (Birdo Daisy Peach Yoshi)"> <button>send</button></form>
<div class="dim">race P1 P2 P3 P4 · undo · cpu -0.3 · map · prepare N</div></div>
<div class="box"><h3>Log</h3><pre id="log"></pre></div></div></div>
<script>
async function send(){const c=document.getElementById('cmd');const r=await fetch('/cmd',{method:'POST',body:c.value});document.getElementById('log').textContent=(await r.text())+"\n"+document.getElementById('log').textContent;c.value='';return false}
async function prep(i,l){await fetch('/cmd',{method:'POST',body:'prepare '+i+' '+l})}
function f(x,d=1){return x==null?'':(+x).toFixed(d)}
async function tick(){try{const s=await (await fetch('/state.json')).json();
document.getElementById('status').innerHTML=(s.age>5?'<span class=stale>':'<span>')+s.status+' (data '+(s.age??'-')+' s old)</span>'+(s.unmapped.length?' <span class=stale>UNMAPPED: '+s.unmapped.join(' ')+'</span>':'');
document.getElementById('races').textContent=s.races.map((r,i)=>'R'+(i+1)+': '+r.join('-')).join('  ')||'none yet';
document.getElementById('skill').textContent=s.skill?s.racers.map((h,i)=>h+' '+(s.skill[i]>=0?'+':'')+s.skill[i]).join('  ')+'  (CPU prior '+s.cpu_skill+')':'';
document.getElementById('points').textContent=s.points?s.points.map((p,k)=>'S'+(k+1)+' '+s.racers.map((h,i)=>h.slice(0,2)+p[i]).join(' ')).join(' | '):'';
document.getElementById('pnl').textContent=s.pnl?('  PnL mark-to-fair '+f(s.pnl.total,0)+' (realized '+f(s.pnl.realized,0)+')  exchange '+f(s.exchange_pnl,0)):'';
document.getElementById('acts').innerHTML='<tr><th>#</th><th>legs</th><th>profit</th><th>why</th>'+(s.prefill?'<th></th>':'')+'</tr>'+s.actions.map((a,i)=>'<tr class="'+a.kind+'"><td>'+(i+1)+'</td><td>'+a.legs.map(l=>'<span class="'+l[1]+'">'+l[1].toUpperCase()+' '+l[2]+' '+l[0]+' @ '+l[3]+'</span>').join(' + ')+'</td><td>'+f(a.profit,0)+'</td><td style="text-align:left">'+a.note+'</td>'+(s.prefill?'<td>'+a.legs.map((l,k)=>'<button onclick="prep('+(i+1)+','+(k+1)+')">'+(a.legs.length>1?'leg '+(k+1):'prepare')+'</button>').join(' ')+'</td>':'')+'</tr>').join('');
document.getElementById('rows').innerHTML='<tr><th>symbol</th><th>contract</th><th>bid</th><th>ask</th><th>fair</th><th>sd</th><th>edge buy</th><th>edge sell</th><th>bounds</th><th>pos</th><th>avg</th><th>action</th></tr>'+s.rows.map(r=>'<tr class="'+(r.bid==null&&r.ask==null?'settled':'')+'"><td>'+r.symbol+'</td><td>'+r.role+'</td><td>'+f(r.bid)+(r.bid_qty?'<span class=dim>×'+r.bid_qty+'</span>':'')+'</td><td>'+f(r.ask)+(r.ask_qty?'<span class=dim>×'+r.ask_qty+'</span>':'')+'</td><td><b>'+f(r.fair)+'</b></td><td class=dim>'+f(r.sd)+'</td><td class="'+(r.edge_buy>0?'buy':'')+'">'+f(r.edge_buy)+'</td><td class="'+(r.edge_sell>0?'sell':'')+'">'+f(r.edge_sell)+'</td><td class=dim>'+(r.lo==null?'':f(r.lo,0)+'-'+f(r.hi,0))+'</td><td>'+(r.pos||'')+'</td><td class=dim>'+f(r.avg)+'</td><td class="'+(r.action.startsWith('BUY')?'buy':r.action?'sell':'')+'">'+r.action+'</td></tr>').join('');
document.getElementById('log').textContent=s.log.slice().reverse().join('\n');}catch(e){}}
setInterval(tick,700);tick();
</script></body></html>"""


def serve(desk: Desk, port: int) -> None:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def _send(self, body: bytes, ctype: str):
            self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/state.json"):
                return self._send(json.dumps(desk.state(), default=float).encode(), "application/json")
            self._send(PAGE.encode(), "text/html; charset=utf-8")

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0)); line = self.rfile.read(n).decode()
            out = desk.command(line); desk.say(f"> {line}: {out.splitlines()[0] if out else ''}")
            self._send(out.encode(), "text/plain; charset=utf-8")

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="https://cornelltradingcompetition.org")
    ap.add_argument("--mock", action="store_true", help="use the mock exchange on http://127.0.0.1:8790 (HTTP tap unless --tap browser)")
    ap.add_argument("--tap", choices=["browser", "http"], default=None)
    ap.add_argument("--key", default=None, help="API key for the HTTP tap, if the organisers give one")
    ap.add_argument("--port", type=int, default=8787); ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--auto-results", action="store_true", help="mock only: read race results from /mock/results instead of typing them")
    ap.add_argument("--no-prefill", dest="prefill", action="store_false", help="disable 'prepare N' (typing an order into the UI's form; the organisers allowed it on 2026-10-23)")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--cpu-skill", type=float, default=-0.6); ap.add_argument("--cpu-sd", type=float, default=0.5)
    ap.add_argument("--noise", type=float, default=1.0); ap.add_argument("--skill-sd", type=float, default=1.0)
    ap.add_argument("--clip", type=int, default=50); ap.add_argument("--risk", type=float, default=1500.0); ap.add_argument("--min-profit", type=float, default=5.0)
    ap.add_argument("--no-repl", action="store_true", help="no terminal prompt (commands only from the dashboard)")
    a = ap.parse_args()
    if a.mock:
        a.url = "http://127.0.0.1:8790"
    if a.tap is None:
        a.tap = "http" if a.mock else "browser"
    desk = Desk(a)
    serve(desk, a.port)
    desk.say(f"dashboard on http://localhost:{a.port}  exchange {a.url} via {a.tap} tap")
    threading.Thread(target=desk.run_tap, daemon=True).start()
    if a.no_repl or not sys.stdin.isatty():
        try:
            while not desk.stop:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    else:
        while not desk.stop:
            try:
                line = input("> ")
            except EOFError:
                break
            out = desk.command(line)
            if out:
                print(out, flush=True)
    desk.stop = True
    if isinstance(desk.tap, BrowserTap):
        desk.tap.stop()


if __name__ == "__main__":
    main()
