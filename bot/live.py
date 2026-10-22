"""Live bot for the Hurricane Season exchange (testnet or competition).

    pip install "websockets>=14"
    python bot/live.py --url https://hurricane.cornelltradingcompetition.org --key BOT_KEY --dry-run

Wraps the exchange in an object with the same surface as ctc.sim.Sim, so the strategies in ctc/strategies.py run
unchanged. Reads the news and quotes channels, keeps positions and open orders in sync by polling, and logs fair vs
mid for the operator every 10 s. Start with --dry-run: orders are printed, not sent.
"""
from __future__ import annotations
import argparse, asyncio, collections, json, sys, time, urllib.error, urllib.request
from pathlib import Path
from typing import Any
import websockets
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc import strategies as S
from ctc.valuation import SYMS

HEADERS = {"User-Agent": "ctc2026-bot/1.0"}


class LiveExchange:
    def __init__(self, url: str, key: str, dry_run: bool, rate_limit: int = 280):
        self.url, self.key, self.dry_run = url.rstrip("/"), key, dry_run
        self.case = self.get("/cases/hurricane.json", api=False)
        self.limits = self.case["limits"]; self.symbols = list(self.limits)
        self.quotes: dict[str, tuple[float, float]] = {}
        self.mid: dict[str, float] = {}
        self.position: dict[str, int] = {s: 0 for s in self.symbols}
        self.open_orders: list[dict[str, Any]] = []
        self.market_open = False
        self.t0 = time.time()
        self.actions: collections.deque[float] = collections.deque()
        self.rate_limit = rate_limit
        self.rejected = 0
        self.round = 0

    @property
    def t(self) -> float:
        return time.time() - self.t0

    # ---- http ----
    def get(self, path: str, api: bool = True) -> Any:
        req = urllib.request.Request(self.url + ("/api/v1" if api else "") + path, headers={**HEADERS, "X-API-Key": self.key})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    def send(self, method: str, path: str, body: dict | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + "/api/v1" + path, data=data, method=method,
                                     headers={**HEADERS, "X-API-Key": self.key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            self.rejected += 1
            print(f"HTTP {exc.code} {method} {path} {body}: {exc.read().decode()[:200]}", flush=True)
            return None

    def _action_ok(self) -> bool:
        now = self.t
        while self.actions and self.actions[0] < now - 60:
            self.actions.popleft()
        if len(self.actions) >= self.rate_limit:
            return False
        self.actions.append(now)
        return True

    # ---- sync ----
    def refresh(self) -> None:
        try:
            tm = self.get("/competitions/time")
            self.market_open = tm.get("state") == "running"
            pos = self.get("/positions")
            items = pos.get("positions", pos) if isinstance(pos, dict) else pos
            for p in items if isinstance(items, list) else []:
                sym = p.get("symbol"); q = p.get("quantity", p.get("position"))
                if sym in self.position and q is not None:
                    self.position[sym] = int(q)
            oo = self.get("/orders/open")
            self.open_orders = oo.get("orders", oo) if isinstance(oo, dict) else oo
        except Exception as exc:  # keep trading on stale state rather than crash
            print(f"refresh failed: {exc}", flush=True)

    def resting(self, symbol: str, side: str) -> int:
        return sum(int(o.get("remaining", o.get("quantity", 0))) for o in self.open_orders if o.get("symbol") == symbol and o.get("side") == side)

    # ---- orders (same signatures as Sim) ----
    def place(self, symbol: str, side: str, qty: int, price: float | None = None) -> int | None:
        if not self.market_open or qty <= 0 or not self._action_ok():
            return None
        sign = 1 if side == "buy" else -1
        room = self.limits[symbol] - sign * self.position[symbol] - self.resting(symbol, side)
        qty = min(int(qty), room)
        if qty <= 0:
            return None
        order = {"symbol": symbol, "side": side, "order_type": "limit" if price is not None else "market", "quantity": qty}
        if price is not None:
            order["price"] = round(price, 4)
        if self.dry_run:
            print(f"[dry-run] would send {order}", flush=True)
            return -1
        resp = self.send("POST", "/orders", order)
        if resp:
            filled = int(resp.get("filled_quantity", resp.get("filled", 0)) or 0)
            self.position[symbol] += sign * filled                     # apply what we know now; refresh() corrects later
            if filled < qty:
                self.open_orders.append({**order, "remaining": qty - filled, "id": resp.get("order_id", resp.get("id"))})
            return resp.get("order_id", resp.get("id"))
        return None

    def cancel_all(self, symbol: str | None = None) -> None:
        if not self._action_ok():
            return
        if self.dry_run:
            print(f"[dry-run] would cancel all {symbol or ''}", flush=True)
        else:
            self.send("DELETE", "/orders/all" + (f"?symbol={symbol}" if symbol else ""))
        self.open_orders = [o for o in self.open_orders if symbol is not None and o.get("symbol") != symbol]

    def create(self, etf: str, qty: int) -> bool:
        return bool(self._action_ok() and (self.dry_run or self.send("POST", f"/etf/{etf}/create", {"quantity": qty})))

    def redeem(self, etf: str, qty: int) -> bool:
        return bool(self._action_ok() and (self.dry_run or self.send("POST", f"/etf/{etf}/redeem", {"quantity": qty})))


def quote_from_frame(d: dict[str, Any]) -> tuple[str, float, float] | None:
    sym = d.get("symbol")
    bid = d.get("bid", d.get("best_bid")); ask = d.get("ask", d.get("best_ask"))
    if isinstance(bid, dict): bid = bid.get("price")
    if isinstance(ask, dict): ask = ask.get("price")
    if sym and bid is not None and ask is not None:
        return sym, float(bid), float(ask)
    return None


async def run(args: argparse.Namespace) -> None:
    ex = LiveExchange(args.url, args.key, args.dry_run)
    strat = S.FairValueTrader(min_edge=args.min_edge, edge_full=args.edge_full, project=True)
    strat.on_start(ex)
    ex.refresh()
    ws_url = (args.ws or ex.url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)) + "/ws/v1/market-data"
    subscribe = {"action": "subscribe", "symbols": ex.symbols, "channels": ["news", "quotes"]}
    last_sync = last_log = 0.0
    seen_seq: set[int] = set()
    last_round = 0
    while True:
        try:
            async with websockets.connect(ws_url, additional_headers={"X-API-Key": ex.key}) as ws:
                await ws.send(json.dumps(subscribe))
                print("connected", flush=True)
                async for frame in ws:
                    d = json.loads(frame)
                    if d.get("type") == "quote":
                        q = quote_from_frame(d)
                        if q:
                            ex.quotes[q[0]] = (q[1], q[2]); ex.mid[q[0]] = (q[1] + q[2]) / 2
                    elif d.get("type") == "news" and isinstance(d.get("message"), dict):
                        m = d["message"]
                        seq = m.get("seq")
                        if seq is not None:
                            if seq in seen_seq:
                                continue
                            seen_seq.add(seq)
                        if m.get("type") == "storm_formed":
                            if m["round"] < last_round:          # new season on the testnet
                                print("new season: resetting model", flush=True)
                                strat.on_start(ex); seen_seq.clear()
                            last_round = ex.round = m["round"]
                        if m.get("type") == "snapshot":
                            strat.model.on_snapshot(m)
                            continue
                        if m.get("type") == "announcement":
                            print(f"ANNOUNCEMENT {m.get('symbols')}: {m.get('headline')}  -> pausing those symbols", flush=True)
                            strat.pause(m.get("symbols", []))
                        strat.on_news(ex, m)
                    now = ex.t
                    if now - last_sync > args.sync:
                        ex.refresh(); last_sync = now
                    if len(ex.quotes) >= len(ex.symbols) // 2:
                        strat.on_quotes(ex)
                    if now - last_log > 10 and strat.fair:
                        print(f"t={now:7.0f} r{strat.model.round} " + " ".join(
                            f"{s}:{ex.mid.get(s, 0):.2f}/{strat.fair.get(s, 0):.2f}/{ex.position[s]:+d}" for s in SYMS), flush=True)
                        last_log = now
        except (OSError, websockets.WebSocketException) as exc:
            print(f"disconnected ({exc}); reconnecting", flush=True)
            await asyncio.sleep(2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="https://hurricane.cornelltradingcompetition.org")
    ap.add_argument("--key", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-edge", type=float, default=0.01)
    ap.add_argument("--edge-full", type=float, default=0.05)
    ap.add_argument("--sync", type=float, default=3.0, help="seconds between position/open-order polls")
    ap.add_argument("--ws", default=None, help="override the market-data host, e.g. ws://localhost:8766 for the mock")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
