"""Live bot for the Hurricane Season exchange (testnet or competition).

    pip install "websockets>=14"
    python bot/live.py --url https://hurricane.cornelltradingcompetition.org --key BOT_KEY --dry-run

Wraps the exchange in an object with the same surface as ctc.sim.Sim, so the strategies in ctc/strategies.py run
unchanged. Reads the news and quotes channels, keeps positions and open orders in sync by polling, and logs fair vs
mid for the operator every 10 s. Start with --dry-run: orders are printed, not sent.
"""
from __future__ import annotations
import argparse, asyncio, collections, json, math, sys, time, urllib.error, urllib.request
from http.client import HTTPException
from pathlib import Path
from typing import Any
import websockets
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc import strategies as S
from ctc.valuation import SYMS

HEADERS = {"User-Agent": "ctc2026-bot/1.0"}
TICK = 0.01   # exchange rejects prices that are not a multiple of 0.01


def tick_price(price: float, side: str) -> float:
    """Round a limit price to the tick, never past the limit: buys round down, sells round up."""
    n = price / TICK
    k = math.floor(n + 1e-9) if side == "buy" else math.ceil(n - 1e-9)
    return round(k * TICK, 2)



class LiveExchange:
    def __init__(self, url: str, key: str, dry_run: bool, rate_limit: int = 120):
        self.url, self.key, self.dry_run = url.rstrip("/"), key, dry_run
        self.case = self.get("/cases/hurricane.json", api=False)
        self.limits = self.case["limits"]; self.symbols = list(self.limits)
        self.quotes: dict[str, tuple[float, float]] = {}
        self.mid: dict[str, float] = {}
        self.quote_times: dict[str, float] = {}
        self.position: dict[str, int] = {s: 0 for s in self.symbols}
        self.open_orders: list[dict[str, Any]] = []
        self.market_open = False
        self.state_ready = False  # complete account snapshot required before any new exposure
        self.t0 = time.time()
        self.actions: collections.deque[float] = collections.deque()
        self.rate_limit = rate_limit
        self.rejected = 0
        self.round = 0
        self.competition_id = None
        self.last_positions: Any = None
        self.pnl_now = 0.0
        self.reopened = False
        self.trade_cursor = None        # /trades pagination cursor (ignored by the exchange); our fills are logged as FILL lines
        self.seen_trades: set = set()   # trade ids already logged
        self.fill_cost = [0.0, 0.0]     # (sum of signed slippage vs mid in $, notional) since start, for the FILL lines

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
                payload = r.read()
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as exc:
            self.rejected += 1
            self.state_ready = False
            try:
                detail = exc.read().decode(errors="replace")[:200]
            except (OSError, HTTPException):
                detail = "unreadable error response"
            print(f"HTTP {exc.code} {method} {path} {body}: {detail}", flush=True)
            if exc.code == 403 and "halted" in detail:
                self.market_open = False                     # stop sending until the next time poll says running
            return None
        except (OSError, ValueError, HTTPException) as exc:
            # A timeout may have happened after the exchange accepted the action.
            # Do not retry or free capacity until positions/orders are reconciled.
            self.state_ready = False
            print(f"uncertain {method} {path}: {exc}; waiting for account refresh", flush=True)
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
            was_open = self.market_open
            cid = tm.get("competition_id")
            # Orders first, positions second: a fill between the two reads is
            # counted in the position without losing its reservation prematurely.
            oo = self.get("/orders/open")
            orders = oo.get("orders", oo) if isinstance(oo, dict) else oo
            pos = self.get("/positions")
            items = pos.get("positions", pos) if isinstance(pos, dict) else pos
            if not isinstance(items, list) or not isinstance(orders, list):
                raise ValueError("positions and open orders must be lists")
            positions = {s: 0 for s in self.symbols}
            for p in items:
                sym = p.get("symbol"); q = p.get("quantity", p.get("position"))
                if sym in positions:
                    if q is None:
                        raise ValueError(f"missing position quantity for {sym}")
                    positions[sym] = int(q)
            for o in orders:
                if o.get("symbol") not in self.limits or o.get("side") not in ("buy", "sell"):
                    raise ValueError("invalid open order")
                if int(o["quantity"]) < int(o.get("filled_quantity", 0)):
                    raise ValueError("invalid remaining order quantity")
            summary = {"realized": round(sum(p.get("realized_pnl", 0) for p in items)),
                       "unrealized": round(sum(p.get("unrealized_pnl", 0) for p in items)),
                       "positions": positions.copy(),
                       "realized_by": {p["symbol"]: round(p.get("realized_pnl", 0)) for p in items},
                       "avg_price": {p["symbol"]: p.get("average_price") for p in items}}
            if self.competition_id and cid != self.competition_id:
                print(f"SEASON END competition {self.competition_id} ({tm.get('fictional_time')}): last positions {json.dumps(self.last_positions)}", flush=True)
                self.trade_cursor = None
                self.quotes.clear(); self.mid.clear()
                self.quote_times.clear()
            # Publish a complete snapshot only after every required request succeeds.
            self.competition_id = cid
            self.position, self.open_orders = positions, orders
            self.last_positions = summary
            self.pnl_now = summary["realized"] + summary["unrealized"]
            self.market_open = tm.get("state") == "running"
            self.reopened = self.market_open and not was_open
            self.state_ready = True
            self.poll_trades()
        except Exception as exc:
            self.state_ready = False
            self.market_open = False
            self.reopened = False
            print(f"refresh failed: {exc}", flush=True)

    def poll_trades(self) -> None:
        """Log every fill the exchange reports for this key (price, size, mid at the time, slippage in bp) so the live
        fill cost can be audited against the simulator's ladder; the per-10 s pnl line is not enough for that."""
        try:
            q = f"?cursor={self.trade_cursor}" if self.trade_cursor else ""
            d = self.get("/trades" + q)
        except Exception as exc:
            print(f"trades poll failed: {exc}", flush=True)
            return
        trades = d.get("trades", []) if isinstance(d, dict) else d
        # the endpoint returns the latest 100 trades newest first and ignores its own cursor (measured 2026-10-23: the
        # same 238 fills were logged 43,576 times), so dedupe by trade id and log oldest first
        new = [tr for tr in (trades or []) if tr.get("trade_id", tr.get("id")) not in self.seen_trades]
        for tr in reversed(new):
            self.seen_trades.add(tr.get("trade_id", tr.get("id")))
            sym, px, qty = tr.get("symbol"), tr.get("price"), tr.get("quantity")
            side = tr.get("side")
            if side not in ("buy", "sell"):
                side = "?"
                for field in ("buyer_is_me", "is_buyer"):
                    if isinstance(tr.get(field), bool):
                        side = "buy" if tr[field] else "sell"
                        break
            if sym is None or px is None or qty is None:
                print(f"FILL raw {json.dumps(tr)[:200]}", flush=True)
                continue
            mid = self.mid.get(sym)
            slip = ""
            if mid and side in ("buy", "sell"):
                sgn = 1 if side == "buy" else -1
                cost = sgn * (float(px) - mid) * float(qty)
                self.fill_cost[0] += cost; self.fill_cost[1] += float(px) * float(qty)
                slip = f" mid {mid:.2f} slip {cost / max(1e-9, float(px) * float(qty)) * 1e4:+.0f} bp (cum {self.fill_cost[0] / max(1e-9, self.fill_cost[1]) * 1e4:+.0f} bp)"
            print(f"FILL {sym} {side} {qty} @ {px}{slip} id {str(tr.get('trade_id', tr.get('id', '')))[:8]} t {str(tr.get('executed_at', tr.get('timestamp', '')))[11:23]}", flush=True)
        if len(self.seen_trades) > 5000:
            self.seen_trades = set(list(self.seen_trades)[-2000:])

    def resting(self, symbol: str, side: str) -> int:
        return sum(int(o.get("quantity", 0)) - int(o.get("filled_quantity", 0)) for o in self.open_orders
                   if o.get("symbol") == symbol and o.get("side") == side)

    # ---- orders (same signatures as Sim) ----
    def place(self, symbol: str, side: str, qty: int, price: float | None = None) -> int | None:
        if not self.market_open or not self.state_ready or qty <= 0:
            return None
        sign = 1 if side == "buy" else -1
        room = self.limits[symbol] - sign * self.position[symbol] - self.resting(symbol, side)
        qty = min(int(qty), room)
        if qty <= 0:
            return None
        if not self._action_ok():
            return None
        order = {"symbol": symbol, "side": side, "order_type": "limit" if price is not None else "market", "quantity": qty}
        if price is not None:
            order["price"] = tick_price(price, side)
        if self.dry_run:
            print(f"[dry-run] would send {order}", flush=True)
            return -1
        resp = self.send("POST", "/orders", order)
        print(f"ORDER {order} -> {resp}", flush=True)
        try:
            if not isinstance(resp, dict):
                raise ValueError("missing order acknowledgement")
            oid = resp.get("order_id", resp.get("id"))
            if isinstance(oid, bool) or not isinstance(oid, (str, int)) or oid == "":
                raise ValueError("missing order id")
            raw_filled = resp.get("filled_quantity", resp.get("filled", 0))
            raw_accepted = resp.get("quantity", qty)
            accepted, filled = int(raw_accepted), int(raw_filled)
            if (isinstance(raw_accepted, bool) or accepted != raw_accepted
                    or isinstance(raw_filled, bool) or filled != raw_filled
                    or not 0 <= filled <= accepted <= qty or accepted <= 0):
                raise ValueError("invalid acknowledged quantity")
            status = resp.get("status")
            if status is not None and status not in {"new", "pending", "accepted", "open", "resting", "partial", "partially_filled", "filled"}:
                raise ValueError("unrecognized order status")
            if status == "filled" and filled != accepted:
                raise ValueError("filled acknowledgement lacks complete fill quantity")
        except (TypeError, ValueError, OverflowError):
            self.state_ready = False
            print("uncertain order acknowledgement; waiting for account refresh", flush=True)
            return None
        self.position[symbol] += sign * filled  # refresh() reconciles later fills
        if filled < accepted:
            self.open_orders.append({**order, "quantity": accepted, "filled_quantity": filled, "order_id": oid})
        return oid

    def cancel_all(self, symbol: str | None = None) -> bool:
        if not self._action_ok():
            return False
        if self.dry_run:
            print(f"[dry-run] would cancel all {symbol or ''}", flush=True)
            self.open_orders = [o for o in self.open_orders if symbol is not None and o.get("symbol") != symbol]
            return True
        else:
            if self.send("DELETE", "/orders/all" + (f"?symbol={symbol}" if symbol else "")) is None:
                return False
        # A fill can beat the cancel. Reconcile its position before a caller
        # calculates replacement quantity, and verify the targeted orders vanished.
        self.refresh()
        return self.state_ready and not any(symbol is None or o.get("symbol") == symbol for o in self.open_orders)

    def liquidity(self, symbol: str, side: str, limit: float) -> int | None:
        """Current external executable depth; unavailable books fail closed for baskets."""
        if not self.state_ready:
            return None
        try:
            book = self.get(f'/orderbook/{symbol}')
            levels = book['asks' if side == 'buy' else 'bids']
            resting_side = 'sell' if side == 'buy' else 'buy'
            total = 0
            for level in levels:
                price, quantity = level['price'], level['quantity']
                if (isinstance(price, bool) or isinstance(quantity, bool)
                        or not math.isfinite(price) or price <= 0
                        or not math.isfinite(quantity) or quantity < 0 or int(quantity) != quantity):
                    return None
                own = sum(int(o['quantity']) - int(o.get('filled_quantity', 0) or 0)
                          for o in self.open_orders if o['symbol'] == symbol and o['side'] == resting_side
                          and o.get('price') is not None and math.isclose(o['price'], price, rel_tol=0, abs_tol=1e-8))
                if (side == 'buy' and price <= limit) or (side == 'sell' and price >= limit):
                    total += max(0, int(quantity) - own)
            return total
        except (OSError, HTTPException, ValueError, TypeError, KeyError):
            return None

    def create(self, etf: str, qty: int) -> bool:
        return self._convert(etf, qty, "create")

    def redeem(self, etf: str, qty: int) -> bool:
        return self._convert(etf, qty, "redeem")

    def _convert(self, etf: str, qty: int, action: str) -> bool:
        if not self.market_open or not self.state_ready or qty <= 0 or not self._action_ok():
            return False
        if self.dry_run:
            return True
        response = self.send("POST", f"/etf/{etf}/{action}", {"quantity": qty})
        # Conversion changes several positions. Reconcile the complete basket
        # before a subsequent order can use any of its position capacity.
        self.state_ready = False
        return response is not None


def replay_feed_log(path: str, ex: "LiveExchange", strat, seen_seq: set[int], tail_bytes: int = 150_000_000) -> tuple[str, int, int]:
    """Feed every recorded news message of the current season (same fictional year as the exchange clock) through the
    model, in seq order. Returns (season year, last round seen, messages replayed)."""
    try:
        tm = ex.get("/competitions/time"); year = str(tm.get("fictional_time") or "")[:4]
    except Exception as exc:
        print(f"feed-log replay skipped: time poll failed ({exc})", flush=True); return "", 0, 0
    p = Path(path)
    if not year or not p.exists():
        print(f"feed-log replay skipped: {'no fictional year' if not year else path + ' missing'}", flush=True); return year, 0, 0
    msgs: dict[int, dict] = {}
    with p.open("rb") as f:
        size = f.seek(0, 2); f.seek(max(0, size - tail_bytes))
        if size > tail_bytes:
            f.readline()
        for raw in f:
            if b'"news"' not in raw:
                continue
            try:
                d = json.loads(raw)
            except Exception:
                continue
            m = d.get("message") if d.get("type") == "news" else None
            if not isinstance(m, dict) or m.get("type") == "snapshot" or m.get("seq") is None:
                continue
            if str(m.get("time") or "")[:4] != year:
                continue
            msgs[m["seq"]] = m
    last_round = 0
    for seq in sorted(msgs):
        m = msgs[seq]
        strat.model.on_message(m); seen_seq.add(seq)
        if m.get("type") == "storm_formed":
            last_round = m["round"]
    return year, last_round, len(msgs)


def quote_from_frame(d: dict[str, Any]) -> tuple[str, float, float] | None:
    sym = d.get("symbol")
    bid = d.get("bid", d.get("best_bid")); ask = d.get("ask", d.get("best_ask"))
    if isinstance(bid, dict): bid = bid.get("price")
    if isinstance(ask, dict): ask = ask.get("price")
    if sym and bid is not None and ask is not None:
        return sym, float(bid), float(ask)
    return None


async def run(args: argparse.Namespace) -> None:
    ex = LiveExchange(args.url, args.key, args.dry_run, rate_limit=args.rate)
    if args.nowcast:
        strat = S.FairValueTrader(min_edge=args.min_edge, edge_full=args.edge_full, project=True)
    else:   # the analog ensemble, same parameters as scripts/backtest.py --strategy analog
        strat = S.FairValueTrader(min_edge=args.min_edge, edge_full=args.edge_full, analog=True, sd_mult=args.sd_mult,
                                  basket_edge=args.basket_edge, basket_participation=args.basket_participation,
                                  final_exact=args.final_exact, final_edge=args.final_edge, final_edge_full=args.final_edge_full,
                                  sigma=args.sigma, k=args.k, passive=args.passive, warmup=args.warmup, max_cross=args.max_cross,
                                  carry=args.carry, ent_cut=args.ent_cut, cone_w=args.cone_w, cone_s0=args.cone_s0, cone_nu=args.cone_nu, isl_w=args.isl_w)
    print(f"strategy {'nowcast' if args.nowcast else 'analog'} min_edge {args.min_edge} edge_full {args.edge_full} sd_mult {args.sd_mult} sigma {args.sigma} k {args.k} passive {args.passive} warmup {args.warmup} max_cross {args.max_cross} carry {args.carry} ent_cut {args.ent_cut} cone_w {args.cone_w} cone_s0 {args.cone_s0} cone_nu {args.cone_nu} isl_w {args.isl_w}", flush=True)
    strat.on_start(ex)
    print(f"final phase exact={strat.final_exact} entry={strat.final_edge} full={strat.final_edge_full}", flush=True)
    print(f"basket edge={strat.basket_edge} participation={strat.basket_participation} max_lot=10", flush=True)
    ex.refresh()
    season_year = ""
    last_round = 0
    seen_seq: set[int] = set()
    if args.feed_log:
        # rebuild the model from the recorder's feed file instead of the exchange snapshot: a snapshot rebuild lacks the
        # closure history of earlier storms and integrates the current storm over a coarse track (fair values off by
        # 2-5 points for the rest of the season, up to 20 points right after the rebuild; measured 2026-10-23)
        season_year, last_round, n = replay_feed_log(args.feed_log, ex, strat, seen_seq)
        print(f"replayed {n} feed messages of season year {season_year or '?'} from {args.feed_log} (round {last_round})", flush=True)
        if n:
            strat.fair = strat.compute_fair(); ex.round = last_round
    ws_url = (args.ws or ex.url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)) + "/ws/v1/market-data"
    subscribe = {"action": "subscribe", "symbols": ex.symbols, "channels": ["news", "quotes"]}
    last_sync = last_log = 0.0
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
                            ex.quote_times[q[0]] = ex.t
                    elif d.get("type") == "news" and isinstance(d.get("message"), dict):
                        m = d["message"]
                        seq = m.get("seq")
                        if seq is not None:
                            if seq in seen_seq:
                                continue
                            seen_seq.add(seq)
                        year = (m.get("time") or "")[:4]
                        if year and season_year and year != season_year and m.get("type") != "snapshot":
                            # the fictional year names the season; a change means the testnet moved on (02:07 tonight the first
                            # snapshot still described the previous season and its damage was carried into the new one)
                            print(f"new season (year {season_year} -> {year}): resetting model", flush=True)
                            strat.on_start(ex); seen_seq.clear(); last_round = 0
                        if year and m.get("type") != "snapshot":
                            season_year = year
                        if m.get("type") == "storm_formed":
                            if m["round"] < last_round or (m["round"] == 1 and (strat.model.reported_rounds or strat.model.round)):
                                print("new season: resetting model", flush=True)
                                strat.on_start(ex); seen_seq.clear()
                            last_round = ex.round = m["round"]
                        if m.get("type") == "snapshot":
                            if year and season_year and year != season_year:
                                print(f"snapshot from another season (year {season_year} -> {year}): resetting model", flush=True)
                                strat.on_start(ex); seen_seq.clear(); last_round = 0
                            if year:
                                season_year = year
                            strat.model.on_snapshot(m)
                            strat.fair = strat.compute_fair()
                            strat.last_trade_t = -1e9
                            # fair values right after a snapshot can be far off until live messages arrive
                            # (14:10 reconnect: PORT fair 99.9 vs mid 81, full-size orders, -4k in 30 s); warm up as at a round open
                            print("snapshot processed: warm-up before trading", flush=True)
                            strat.on_round(ex)
                            continue
                        if m.get("type") == "announcement":
                            print(f"ANNOUNCEMENT {m.get('symbols')}: {m.get('headline')}  -> pausing those symbols", flush=True)
                            strat.pause(m.get("symbols", []))
                        strat.on_news(ex, m)
                    now = ex.t
                    if now - last_sync > args.sync:
                        cid_before = ex.competition_id
                        ex.refresh(); last_sync = now
                        if cid_before and ex.competition_id != cid_before:
                            print("new competition id: resetting model", flush=True)
                            strat.on_start(ex); seen_seq.clear(); last_round = 0
                        if ex.reopened:
                            print("market (re)opened: warm-up", flush=True)
                            strat.on_round(ex); ex.reopened = False
                    if len(ex.quotes) >= len(ex.symbols) // 2:
                        strat.on_quotes(ex)
                    if now - last_log > 10 and strat.fair:
                        print(f"t={now:7.0f} r{strat.model.round} pnl {ex.pnl_now:+.0f} " + " ".join(
                            f"{s}:{ex.mid.get(s, 0):.2f}/{strat.fair.get(s, 0):.2f}/{ex.position[s]:+d}" for s in SYMS), flush=True)
                        last_log = now
        except (OSError, websockets.WebSocketException) as exc:
            print(f"disconnected ({exc}); reconnecting", flush=True)
            await asyncio.sleep(2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="https://cornelltradingcompetition.org")
    ap.add_argument("--key", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-edge", type=float, default=0.025)
    ap.add_argument("--edge-full", type=float, default=0.03)
    ap.add_argument('--basket-edge', type=float, default=0.01, help='net quoted ETF/basket edge (0 disables the overlay)')
    ap.add_argument('--basket-participation', type=float, default=0.5, help='maximum fraction of displayed external depth per closing leg')
    ap.add_argument("--final-exact", action=argparse.BooleanOptionalAction, default=True,
                    help="use exact final rules after three reports and complete recorded weather")
    ap.add_argument("--final-edge", type=float, default=0.005, help="entry floor in the exact final phase (0 = normal floor)")
    ap.add_argument("--final-edge-full", type=float, default=0.005, help="full-size edge in the exact final phase (0 = normal)")
    ap.add_argument("--sync", type=float, default=3.0, help="seconds between position/open-order polls")
    ap.add_argument("--ws", default=None, help="override the market-data host, e.g. ws://localhost:8766 for the mock")
    ap.add_argument("--rate", type=int, default=120, help="max order actions per minute for this bot (team limit is 180)")
    ap.add_argument("--nowcast", action="store_true", help="constant-velocity nowcast instead of the analog ensemble (debug only)")
    ap.add_argument("--sd-mult", type=float, default=0.7)
    ap.add_argument("--sigma", type=float, default=15.0)
    ap.add_argument("--k", type=int, default=100)
    ap.add_argument("--passive", type=float, default=0.75, help="rest orders inside the spread at edge = passive*floor (0 = off)")
    ap.add_argument("--warmup", type=float, default=20.0, help="seconds after the market opens with no trading")
    ap.add_argument("--max-cross", type=float, default=0.02, help="aggressive orders never pay more than this fraction through the touch (0 = off)")
    ap.add_argument("--feed-log", default=None, help="recorder output (record_feed.py --out ...) to rebuild the season from on start, instead of the exchange snapshot")
    ap.add_argument("--carry", type=float, default=0.5, help="between storms the position limit is carry x the exchange limit (1 = off; 0.5 accepted 2026-10-23 with the cone)")
    ap.add_argument("--cone-w", type=float, default=1.0, help="analog likelihood power for the official advisory cone (0 = off)")
    ap.add_argument("--cone-s0", type=float, default=20.0, help="spread floor (map units) added in quadrature to the cone spread")
    ap.add_argument("--cone-nu", type=float, default=0.0, help="Student-t degrees of freedom for the cone likelihood (0 = Gaussian)")
    ap.add_argument("--isl-w", type=float, default=0.0, help="analog likelihood power for the advisory island probabilities (0 = off; rejected, fattens the tail)")
    ap.add_argument("--ent-cut", type=float, default=1.2, help="do not add while the pattern posterior entropy exceeds this, nats (0 = off)")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
