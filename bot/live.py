"""Live bot for the Hurricane Season exchange (testnet or competition).

    pip install "websockets>=14"
    python bot/live.py --url https://hurricane.cornelltradingcompetition.org --key BOT_KEY --dry-run

Wraps the exchange in an object with the same surface as ctc.sim.Sim, so the strategies in ctc/strategies.py run
unchanged. Reads the news and quotes channels, keeps positions and open orders in sync by polling, and logs fair vs
mid for the operator every 10 s. Start with --dry-run: orders are printed, not sent.
"""
from __future__ import annotations
import argparse, asyncio, collections, json, math, sys, threading, time, urllib.error, urllib.request
from http.client import HTTPException
from pathlib import Path
from typing import Any
import websockets
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc import strategies as S
from ctc.valuation import SYMS
from bot.control import ControlFile
from bot.http_transport import JSONConnection, proxy_required

HEADERS = {"User-Agent": "ctc2026-bot/1.0"}
TICK = 0.01   # exchange rejects prices that are not a multiple of 0.01


def tick_price(price: float, side: str) -> float:
    """Round a limit price to the tick, never past the limit: buys round down, sells round up."""
    n = price / TICK
    k = math.floor(n + 1e-9) if side == "buy" else math.ceil(n - 1e-9)
    return round(k * TICK, 2)



class LiveExchange:
    def __init__(self, url: str, key: str, dry_run: bool, rate_limit: int = 120,
                 *, reuse_http: bool = False):
        self.url, self.key, self.dry_run = url.rstrip("/"), key, dry_run
        self.http_reuse_enabled = reuse_http and not proxy_required(self.url)
        self._http = JSONConnection(self.url) if self.http_reuse_enabled else None
        try:
            self.case = self.get("/cases/hurricane.json", api=False)
            self.limits = self.case["limits"]; self.symbols = list(self.limits)
        except BaseException:
            self.close()
            raise
        self.quotes: dict[str, tuple[float, float]] = {}
        self.mid: dict[str, float] = {}
        self.quote_times: dict[str, float] = {}
        self.quotes_valid_after = -math.inf
        self.position: dict[str, int] = {s: 0 for s in self.symbols}
        self.open_orders: list[dict[str, Any]] = []
        self.market_open = False
        self.state_ready = False  # complete account snapshot required before any new exposure
        self.submission_guard = None  # LiveSession checks model/feed/quotes at each submission.
        self.t0 = time.monotonic()
        self.actions: collections.deque[float] = collections.deque()
        self.rate_limit = rate_limit
        self.rejected = 0
        self.round = 0
        self.competition_id = None
        self.season_year = ''
        self.last_positions: Any = None
        self.pnl_now = 0.0
        self.reopened = False
        self.trade_cursor = None        # /trades pagination cursor (ignored by the exchange); our fills are logged as FILL lines
        self.seen_trades: set = set()   # trade ids already logged
        self.fill_cost = [0.0, 0.0]     # (sum of signed slippage vs mid in $, notional) since start, for the FILL lines

    @property
    def t(self) -> float:
        return time.monotonic() - self.t0

    # ---- http ----
    def close(self) -> None:
        if getattr(self, '_http', None) is not None:
            self._http.close()

    def get(self, path: str, api: bool = True) -> Any:
        if getattr(self, '_http', None) is not None:
            return self._http.request('GET', ("/api/v1" if api else "") + path,
                                      headers={**HEADERS, "X-API-Key": self.key})
        req = urllib.request.Request(self.url + ("/api/v1" if api else "") + path, headers={**HEADERS, "X-API-Key": self.key})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    def send(self, method: str, path: str, body: dict | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + "/api/v1" + path, data=data, method=method,
                                     headers={**HEADERS, "X-API-Key": self.key, "Content-Type": "application/json"})
        try:
            if getattr(self, '_http', None) is not None:
                return self._http.request(method, '/api/v1' + path, body=body,
                    headers={**HEADERS, "X-API-Key": self.key, "Content-Type": "application/json"},
                    allow_empty=True)
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
            pos = self.get("/positions?include_zero=true")
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
            summary = {"realized": round(sum(p.get("realized_pnl") or 0 for p in items)),
                       "unrealized": round(sum(p.get("unrealized_pnl") or 0 for p in items)),
                       "positions": positions.copy(),
                       "realized_by": {p["symbol"]: round(p.get("realized_pnl") or 0) for p in items},
                       "avg_price": {p["symbol"]: p.get("average_price") for p in items}}
            if self.competition_id and cid != self.competition_id:
                print(f"SEASON END competition {self.competition_id} ({tm.get('fictional_time')}): last positions {json.dumps(self.last_positions)}", flush=True)
                self.trade_cursor = None
                self.quotes.clear(); self.mid.clear()
                self.quote_times.clear()
                self.quotes_valid_after = self.t
            # Publish a complete snapshot only after every required request succeeds.
            self.competition_id = cid
            self.season_year = str(tm.get('fictional_time') or '')[:4]
            self.position, self.open_orders = positions, orders
            self.last_positions = summary
            self.pnl_now = summary["realized"] + summary["unrealized"]
            self.market_open = tm.get("state") == "running"
            self.reopened = self.reopened or (self.market_open and not was_open)
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

    def working_orders(self, symbol: str) -> list[dict[str, Any]]:
        """Reconciled/local-acknowledged remaining quantities and limits."""
        return [{'side': o['side'], 'remaining': int(o['quantity']) - int(o.get('filled_quantity', 0)),
                 'price': o.get('price')} for o in self.open_orders
                if o.get('symbol') == symbol and int(o['quantity']) > int(o.get('filled_quantity', 0))]

    # ---- orders (same signatures as Sim) ----
    def place(self, symbol: str, side: str, qty: int, price: float | None = None) -> int | None:
        if not self.market_open or not self.state_ready or qty <= 0:
            return None
        if self.submission_guard is not None and not self.submission_guard((symbol,)):
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
            status_only_fill = (status in {"filled", "partial", "partially_filled"}
                                and "filled_quantity" not in resp and "filled" not in resp)
            if status == "filled" and filled != accepted and not status_only_fill:
                raise ValueError("filled acknowledgement lacks complete fill quantity")
        except (TypeError, ValueError, OverflowError):
            self.state_ready = False
            print("uncertain order acknowledgement; waiting for account refresh", flush=True)
            return None
        if status_only_fill:
            # The testnet returns order_id/status without fill quantities.
            # Reconcile actual holdings and remaining orders, rather than
            # guessing the fill. Keep the accepted ID even if refresh fails;
            # state_ready then prevents another submission until recovery.
            self.state_ready = False
            self.refresh()
            return oid
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
        symbols = (etf, *self.case['etfs'][etf]['basket'])
        if self.submission_guard is not None and not self.submission_guard(symbols):
            return False
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
    for seq in sorted(msgs):
        m = msgs[seq]
        strat.model.on_message(m); seen_seq.add(seq)
        if m.get('type') == 'announcement':
            symbols = [s for s in (m.get('symbols') or []) if s in ex.symbols]
            # Restart loses live price anchors. Re-pause these symbols and use
            # the normal fresh-price re-anchor/explicit operator control path.
            strat.announce(symbols, ex.t)
    if strat.paused:
        print(f'replayed announcement pauses: {sorted(strat.paused)}', flush=True)
    return year, strat.model.round, len(msgs)


def quote_from_frame(d: dict[str, Any]) -> tuple[str, float, float] | None:
    sym = d.get("symbol")
    bid = d.get("bid", d.get("best_bid")); ask = d.get("ask", d.get("best_ask"))
    if isinstance(bid, dict): bid = bid.get("price")
    if isinstance(ask, dict): ask = ask.get("price")
    if sym and bid is not None and ask is not None:
        return sym, float(bid), float(ask)
    return None


class MarketInbox:
    """Event-loop-owned buffer: preserve news order, retain only each latest quote."""
    def __init__(self):
        self.quotes = {}
        self.events = []
        self.sequence = 0
        self.changed = asyncio.Event()
        self.pending_news = threading.Event()

    def put(self, message, received_at):
        self.sequence += 1
        event = (self.sequence, message, received_at)
        if message.get('type') == 'quote':
            self.quotes[message.get('symbol')] = event
        else:
            self.events.append(event)
            if message.get('type') in ('news', 'disconnected'):
                self.pending_news.set()
        self.changed.set()

    def drain(self):
        events = sorted([*self.events, *self.quotes.values()], key=lambda item: item[0])
        self.events.clear()
        self.quotes.clear()
        self.changed.clear()
        self.pending_news.clear()
        return [(message, received_at) for _, message, received_at in events]


async def receive_market_data(ws, inbox, clock):
    # This coroutine never does HTTP, forecasts, or order work. Arrival time is
    # captured before the serialized trading worker can delay processing.
    async for frame in ws:
        received_at = clock()
        message = json.loads(frame)
        if isinstance(message, dict):
            inbox.put(message, received_at)


async def drive_market_data(session, inbox, receiver, interval=.25):
    """One account/strategy owner, with a heartbeat even during a feed outage."""
    session.pending_news = inbox.pending_news
    try:
        while True:
            try:
                await asyncio.wait_for(inbox.changed.wait(), timeout=interval)
            except TimeoutError:
                pass
            await asyncio.to_thread(session.step, inbox.drain())
            if receiver.done() and not inbox.changed.is_set():
                await receiver
                return
    finally:
        # Cancelling to_thread does not cancel its HTTP worker. Latch the stop
        # before asyncio waits for that worker, so it cannot submit another leg.
        session.stop()


class LiveSession:
    def __init__(self, ex, strat, sync, season_year='', last_round=0, seen_seq=None, control=None):
        self.ex, self.strat, self.sync = ex, strat, sync
        self.season_year, self.last_round = season_year or getattr(ex, 'season_year', ''), last_round
        self.retired_years = set()
        self.seen_seq = seen_seq if seen_seq is not None else set()
        self.competition_id = ex.competition_id
        self.account_year = getattr(ex, 'season_year', '')
        self.last_sync = self.last_log = 0.
        self.control = control      # ControlFile or None: human commands (announcement adjustments) polled with each sync
        self.stopped = threading.Event()
        self.pending_news = threading.Event()
        self.latest_seq = max(self.seen_seq, default=-1)
        self.news_complete = len(self.seen_seq) == self.latest_seq + 1
        self.feed_current = False  # Require a live news checkpoint after replay.
        self.reconnect_warmup_pending = False
        self.awaiting_competition_id = None
        self.last_block_reason = None
        ex.submission_guard = self.submission_allowed

    def stop(self):
        self.stopped.set()

    def history_block_reason(self):
        if self.awaiting_competition_id is not None:
            return 'waiting for the new-season account refresh'
        account_year = getattr(self.ex, 'season_year', '')
        if account_year and self.season_year and account_year != self.season_year:
            return 'waiting for account and news to agree on the season'
        if not self.news_complete:
            return 'missing news history; restart from a complete season recording'
        if not self.strat.model.live_history_ready:
            return 'incomplete weather history; wait for a new season or replay a complete recording'
        if not self.feed_current:
            return 'waiting for a live news checkpoint'
        return None

    def submission_allowed(self, symbols=()):
        if (self.stopped.is_set() or self.pending_news.is_set()
                or self.ex.competition_id != self.competition_id or self.history_block_reason()):
            return False
        now = self.ex.t
        return all(not self.symbol_paused(s) and s in self.ex.quotes
                   and self.ex.quote_times.get(s, -math.inf) >= self.ex.quotes_valid_after
                   and 0 <= now - self.ex.quote_times.get(s, -math.inf) <= 5
                   for s in symbols)

    def symbol_paused(self, symbol):
        basket = getattr(self.ex, 'case', {}).get('etfs', {}).get(symbol, {}).get('basket', {})
        return bool(({symbol} | set(basket)) & self.strat.paused)

    def _reset_news(self):
        self.seen_seq.clear()
        self.latest_seq = -1
        self.news_complete = True
        self.feed_current = False

    def _news_season_changed(self, year=''):
        """News can roll over before the REST clock/account poll does."""
        if year and self.season_year and year != self.season_year:
            self.retired_years.add(self.season_year)
        self.strat.on_start(self.ex)
        self.strat.on_round(self.ex)
        self._reset_news()
        self.last_round = self.ex.round = 0
        account_matches = year and year == getattr(self.ex, 'season_year', '')
        self.awaiting_competition_id = None if account_matches else self.ex.competition_id
        if not account_matches:
            self.ex.state_ready = False
        self.ex.quotes.clear()
        self.ex.mid.clear()
        self.ex.quote_times.clear()
        self.ex.quotes_valid_after = self.ex.t

    def _competition_changed(self):
        ex, strat = self.ex, self.strat
        changed = self.competition_id is not None and ex.competition_id != self.competition_id
        self.competition_id = ex.competition_id
        account_year = getattr(ex, 'season_year', '')
        previous_account_year, self.account_year = self.account_year, account_year
        if changed:
            if ((self.awaiting_competition_id is not None
                 or (account_year and self.season_year == account_year and account_year != previous_account_year))
                    and (not account_year or self.season_year == account_year)):
                # Already collecting this season's news: do not discard its
                # prefix when the account poll finally confirms the rollover.
                self.awaiting_competition_id = None
                strat.competition_id = ex.competition_id
                return True
            print('new competition id: resetting model', flush=True)
            if self.season_year:
                self.retired_years.add(self.season_year)
            strat.on_start(ex)
            strat.on_round(ex)
            self._reset_news()
            self.last_round = ex.round = 0
            self.season_year = account_year
            self.awaiting_competition_id = None
        return changed

    def _news(self, m):
        ex, strat = self.ex, self.strat
        year = (m.get('time') or '')[:4]
        if year in self.retired_years:
            return
        if year and self.season_year and year != self.season_year:
            if m.get('type') == 'snapshot' and year != getattr(ex, 'season_year', ''):
                # A foreign-year snapshot cannot establish a rollover. Wait for
                # the account clock/current news, without discarding history.
                self.feed_current = False
                return
            print(f'new season (year {self.season_year} -> {year}): resetting model', flush=True)
            self._news_season_changed(year)
        if year:
            self.season_year = year
        seq = m.get('seq')
        if seq is not None:
            if seq in self.seen_seq:
                if seq == self.latest_seq:
                    self.feed_current = True
                return
            if seq != self.latest_seq + 1:
                self.news_complete = False
            self.seen_seq.add(seq)
            self.latest_seq = max(seq, self.latest_seq)
            self.feed_current = True
        if m.get('type') == 'storm_formed':
            if m['round'] < self.last_round or (m['round'] == 1 and (strat.model.reported_rounds or strat.model.round)):
                print('new season: resetting model', flush=True)
                self._news_season_changed(year)
                if seq is not None:
                    self.seen_seq.add(seq)
                    self.latest_seq = seq
                    self.news_complete = seq == 0
                    self.feed_current = True
            self.last_round = ex.round = m['round']
        if m.get('type') == 'snapshot':
            checkpoint = m.get('last_seq')
            continuous = (not self.reconnect_warmup_pending
                          and checkpoint is not None and 0 <= checkpoint <= self.latest_seq
                          and m.get('round') == self.last_round == strat.model.round
                          and self.history_block_reason() is None)
            if checkpoint is not None:
                if checkpoint > self.latest_seq:
                    self.news_complete = False
                if checkpoint >= self.latest_seq:
                    self.feed_current = True
            strat.model.on_snapshot(m)
            self.last_round = ex.round = strat.model.round
            strat.fair = strat.compute_fair()
            # Healthy periodic checkpoints are not round opens or reconnects.
            # Restarting warm-up on every checkpoint suppresses valid signals.
            if not continuous or self.history_block_reason() is not None:
                strat.last_trade_t = -1e9
                print('snapshot processed: warm-up before trading', flush=True)
                strat.on_round(ex)
                if self.history_block_reason() is None:
                    self.reconnect_warmup_pending = False
            return
        if m.get('type') == 'announcement':
            syms = [s for s in (m.get('symbols') or []) if s in ex.symbols]
            wait = strat.announce_wait
            how = (f"re-anchor to the house mid in {wait:.0f} s unless a command arrives first" if wait > 0
                   else "waiting for a command (recordings/control.txt)")
            print(f"ANNOUNCEMENT {syms}: {m.get('headline')}  -> pausing those symbols; {how}", flush=True)
            strat.announce(syms, ex.t)
        strat.on_news(ex, m)

    def step(self, events):
        ex, strat = self.ex, self.strat
        if ex.t - self.last_sync > self.sync:
            ex.refresh()
            self.last_sync = ex.t
            if self.control is not None:
                for line in self.control.poll(strat, ex):
                    print(line, flush=True)
        self._competition_changed()
        if ex.reopened:
            print('market (re)opened: warm-up', flush=True)
            strat.on_round(ex)
            ex.reopened = False
        for message, received_at in events:
            kind = message.get('type')
            if kind == 'quote':
                if received_at < ex.quotes_valid_after or not 0 <= ex.t - received_at <= 5:
                    continue
                q = quote_from_frame(message)
                if q and q[0] in ex.symbols and all(math.isfinite(p) and p > 0 for p in q[1:]) and q[1] <= q[2]:
                    ex.quotes[q[0]] = (q[1], q[2])
                    ex.mid[q[0]] = (q[1] + q[2]) / 2
                    ex.quote_times[q[0]] = received_at
            elif kind == 'news' and isinstance(message.get('message'), dict):
                self._news(message['message'])
            elif kind == 'disconnected':
                ex.quotes.clear()
                ex.mid.clear()
                ex.quote_times.clear()
                self.feed_current = False
                self.reconnect_warmup_pending = True
        if self.reconnect_warmup_pending and self.history_block_reason() is None:
            # Contiguous news may restore readiness before a reconnect snapshot.
            strat.on_round(ex)
            self.reconnect_warmup_pending = False
        # Cached quotes cannot stay executable because other symbols/news tick.
        now = ex.t
        for symbol in list(ex.quotes):
            if not 0 <= now - ex.quote_times.get(symbol, -math.inf) <= 5:
                ex.quotes.pop(symbol, None)
                ex.mid.pop(symbol, None)
                ex.quote_times.pop(symbol, None)
        blocked = self.history_block_reason()
        if blocked != self.last_block_reason:
            print(f'TRADING BLOCKED: {blocked}' if blocked else 'history complete: trading eligible', flush=True)
            self.last_block_reason = blocked
        if blocked:
            # Keep existing holdings for explicit operator management. Remove
            # resting orders whose rationale can no longer be verified.
            if ex.open_orders:
                ex.cancel_all()
        else:
            for symbol in sorted({o['symbol'] for o in ex.open_orders if self.symbol_paused(o['symbol'])}):
                ex.cancel_all(symbol)
        if not blocked and events and ex.quotes and len(ex.quotes) >= len(ex.symbols) // 2:
            strat.on_quotes(ex)
        elif not blocked and strat.basket is not None and strat.basket.targets is not None:
            # No fresh data is needed to cancel an expired leg. The overlay
            # itself requires fresh quotes before any replacement is priced.
            strat.basket.on_quotes(ex, strat.paused)
        self._competition_changed()  # A nested cancel/conversion can refresh.
        now = ex.t
        if now - self.last_log > 10 and strat.fair:
            print(f't={now:7.0f} r{strat.model.round} pnl {ex.pnl_now:+.0f} ' + ' '.join(
                f'{s}:{ex.mid.get(s, 0):.2f}/{strat.fair.get(s, 0):.2f}/{ex.position[s]:+d}' for s in SYMS), flush=True)
            self.last_log = now


def repeat_prefix_options(args):
    """Return the single evaluated blend configuration after validating intent."""
    enabled = getattr(args, 'repeat_prefix_blend', False)
    if not isinstance(enabled, bool):
        raise ValueError('repeat_prefix_blend must be a bool')
    if enabled and getattr(args, 'nowcast', False):
        raise ValueError('repeat-prefix blend requires the analog model')
    return {'repeat_prefix': True, 'repeat_weight': .5} if enabled else {}


async def run(args: argparse.Namespace) -> None:
    repeat_prefix_options(args)
    ex = LiveExchange(args.url, args.key, args.dry_run, rate_limit=args.rate,
                      reuse_http=getattr(args, 'reuse_http', False))
    try:
        await run_exchange(args, ex)
    finally:
        ex.close()


async def run_exchange(args: argparse.Namespace, ex: LiveExchange) -> None:
    repeat_options = repeat_prefix_options(args)
    print(f"HTTP connection reuse={ex.http_reuse_enabled}", flush=True)
    ex.refresh()
    if not ex.state_ready or not isinstance(ex.competition_id, str) or not ex.competition_id.strip():
        raise RuntimeError('initial account snapshot is unavailable or missing competition identity')
    # Initialize against the confirmed identity before ingesting any history.
    # Otherwise the first quote callback resets the model from None to this CID.
    if args.nowcast:
        strat = S.FairValueTrader(min_edge=args.min_edge, edge_full=args.edge_full, project=True)
    else:   # the analog ensemble, same parameters as scripts/backtest.py --strategy analog
        strat = S.FairValueTrader(min_edge=args.min_edge, edge_full=args.edge_full, analog=True, sd_mult=args.sd_mult,
                                  basket_edge=args.basket_edge, basket_participation=args.basket_participation,
                                  final_exact=args.final_exact, final_edge=args.final_edge, final_edge_full=args.final_edge_full,
                                  sigma=args.sigma, k=args.k, passive=args.passive, warmup=args.warmup, max_cross=args.max_cross,
                                  carry=args.carry, ent_cut=args.ent_cut, cone_w=args.cone_w, cone_s0=args.cone_s0, cone_nu=args.cone_nu, isl_w=args.isl_w,
                                  announce_wait=args.announce_wait, **repeat_options)
    print(f'repeat-prefix blend={bool(repeat_options)} weight={repeat_options.get("repeat_weight")}', flush=True)
    print(f"strategy {'nowcast' if args.nowcast else 'analog'} min_edge {args.min_edge} edge_full {args.edge_full} sd_mult {args.sd_mult} sigma {args.sigma} k {args.k} passive {args.passive} warmup {args.warmup} max_cross {args.max_cross} carry {args.carry} ent_cut {args.ent_cut} cone_w {args.cone_w} cone_s0 {args.cone_s0} cone_nu {args.cone_nu} isl_w {args.isl_w}", flush=True)
    strat.on_start(ex)
    print(f"final phase exact={strat.final_exact} entry={strat.final_edge} full={strat.final_edge_full}", flush=True)
    print(f"basket edge={strat.basket_edge} participation={strat.basket_participation} max_lot=10", flush=True)
    print(f"announcements: pause named symbols, re-anchor to the house mid after {args.announce_wait:.0f} s; commands from {args.control}", flush=True)
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
    inbox = MarketInbox()
    session = LiveSession(ex, strat, args.sync, season_year, last_round, seen_seq, control=ControlFile(args.control))

    async def receive_forever():
        while True:
            try:
                async with websockets.connect(ws_url, additional_headers={'X-API-Key': ex.key}) as ws:
                    await ws.send(json.dumps(subscribe))
                    print('connected', flush=True)
                    await receive_market_data(ws, inbox, lambda: ex.t)
            except (OSError, websockets.WebSocketException) as exc:
                print(f'disconnected ({exc}); reconnecting', flush=True)
            inbox.put({'type': 'disconnected'}, ex.t)
            await asyncio.sleep(2)

    receiver = asyncio.create_task(receive_forever())
    try:
        await drive_market_data(session, inbox, receiver)
    finally:
        receiver.cancel()
        await asyncio.gather(receiver, return_exceptions=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="https://cornelltradingcompetition.org")
    ap.add_argument("--key", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reuse-http", action="store_true",
                    help="reuse HTTP connections (experimental; falls back to urllib when a proxy is configured)")
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
    ap.add_argument('--repeat-prefix-blend', action='store_true',
                    help='enable the evaluated 50/50 blend for uniquely matching complete weather prefixes')
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
    ap.add_argument("--announce-wait", type=float, default=60.0, help="seconds after a live announcement before a paused symbol's fair is re-anchored to the house mid and trading resumes (0 = wait for a human command)")
    ap.add_argument("--control", default="recordings/control.txt", help="command file polled every --sync seconds: 'HAVEN -6%%', 'PORT =61.5', 'resume GEN', 'pause MAT', 'status' (see bot/control.py)")
    args = ap.parse_args()
    try:
        repeat_prefix_options(args)
    except ValueError as exc:
        ap.error(str(exc))
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
