"""Offline replay simulator for one research season.

Replays feed.jsonl and market.csv on the real-time axis of the round (780 s per round, 30x market clock),
quotes a synthetic house market around the house consensus price, fills the strategy's orders, enforces
position and rate limits, and settles at settlement.json.

Strategy interface (see strategies.py): on_start(sim), on_news(sim, message), on_quotes(sim).
Order API: sim.place(symbol, side, qty, price=None) -> order id | None; sim.cancel(oid); sim.cancel_all(symbol=None);
           sim.create(etf, qty); sim.redeem(etf, qty).
"""
from __future__ import annotations
import collections, csv, json, math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from .ladder import Ladder

ROUND_SECS = 780.0
CLOCK = 30.0


def real_time(ts: str, rnd: int) -> float:
    """Market-clock timestamp -> real seconds since the start of round 1 (rounds glued together)."""
    d = datetime.fromisoformat(ts)
    secs = (d.hour - 9) * 3600 + (d.minute - 30) * 60 + d.second
    return (rnd - 1) * ROUND_SECS + secs / CLOCK


@dataclass
class Order:
    id: int
    symbol: str
    side: str
    qty: int
    price: float | None
    t: float
    exec_t: float
    filled: int = 0


@dataclass
class Fill:
    t: float
    symbol: str
    side: str
    qty: int
    price: float
    passive: bool


class Sim:
    def __init__(self, folder: Path, case: dict[str, Any], half_spread: float = 0.0015, latency: float = 0.25,
                 depth: int | None = None, rate_limit: int = 300, verbose: bool = False, ladder: Ladder | None = None):
        self.folder, self.case = Path(folder), case
        self.ladder = ladder
        self.half_spread, self.latency, self.depth, self.rate_limit, self.verbose = half_spread, latency, depth, rate_limit, verbose
        self.limits = case["limits"]
        self.symbols = list(self.limits)
        self.settlement = json.loads((self.folder / "settlement.json").read_text())
        self.events: list[tuple[float, int, str, Any]] = []
        with (self.folder / "market.csv").open() as f:
            for row in csv.DictReader(f):
                t = real_time(row["time"], int(row["round"]))
                self.events.append((t, 0, "price", {s: float(row[s]) for s in self.symbols}))
        with (self.folder / "feed.jsonl").open() as f:
            for line in f:
                m = json.loads(line)
                self.events.append((real_time(m["time"], m["round"]), 1, "news", m))
        self.events.sort(key=lambda e: (e[0], e[1]))
        self.t = 0.0
        self.round = 1
        self.mid: dict[str, float] = {}
        self.quotes: dict[str, tuple[float, float]] = {}
        self.position: dict[str, int] = {s: 0 for s in self.symbols}
        self.cash = 0.0
        self.cash_by: dict[str, float] = {s: 0.0 for s in self.symbols}
        self.round_pnl: dict[int, float] = {}
        self.orders: dict[int, Order] = {}
        self.pending: list[Order] = []
        self.fills: list[Fill] = []
        self.actions: collections.deque[float] = collections.deque()
        self.rejected = 0
        self.next_id = 1
        self.pnl_path: list[tuple[float, float]] = []
        self.market_open = False

    # ---------- public API for strategies ----------
    def liquidity(self, symbol: str, side: str, limit: float) -> int:
        """External displayed quantity executable at the current limit; does not consume it."""
        if self.ladder is None or not self.ladder.has(symbol):
            touch = self.quotes[symbol][1 if side == 'buy' else 0]
            if (side == 'buy' and touch > limit) or (side == 'sell' and touch < limit):
                return 0
            return self.depth if self.depth is not None else 2 * self.limits[symbol]
        row = self.ladder.table[symbol]
        available = self.ladder._avail(symbol, side, self.t)
        total = 0
        for i, quantity in enumerate(available):
            distance = row['spread'] / 2 if i == 0 else row['bands'][i]
            price = self.mid[symbol] * (1 + distance if side == 'buy' else 1 - distance)
            if (side == 'buy' and price <= limit) or (side == 'sell' and price >= limit):
                total += int(quantity)
        return total

    def resting(self, symbol: str, side: str) -> int:
        return sum(o.qty - o.filled for o in (*self.orders.values(), *self.pending)
                   if o.symbol == symbol and o.side == side)

    def _action_ok(self) -> bool:
        while self.actions and self.actions[0] < self.t - 60:
            self.actions.popleft()
        if len(self.actions) >= self.rate_limit:
            self.rejected += 1
            return False
        self.actions.append(self.t)
        return True

    def place(self, symbol: str, side: str, qty: int, price: float | None = None) -> int | None:
        if not self.market_open or qty <= 0 or symbol not in self.limits or not self._action_ok():
            return None
        sign = 1 if side == "buy" else -1
        room = self.limits[symbol] - sign * self.position[symbol] - self.resting(symbol, side)
        qty = min(int(qty), room)
        if qty <= 0:
            self.rejected += 1
            return None
        if price is not None:                      # exchange tick is 0.01; buys round down, sells round up
            price = round((math.floor(price * 100 + 1e-9) if side == "buy" else math.ceil(price * 100 - 1e-9)) / 100, 2)
        o = Order(self.next_id, symbol, side, qty, price, self.t, self.t + self.latency)
        self.next_id += 1
        self.pending.append(o)
        return o.id

    def cancel(self, oid: int) -> bool:
        if not self._action_ok():
            return False
        o = self.orders.pop(oid, None)
        if o is None:
            self.pending = [p for p in self.pending if p.id != oid]
        return True

    def cancel_all(self, symbol: str | None = None) -> bool:
        if not self._action_ok():
            return False
        self.orders = {k: o for k, o in self.orders.items() if symbol is not None and o.symbol != symbol}
        self.pending = [p for p in self.pending if symbol is not None and p.symbol != symbol]
        return True

    def create(self, etf: str, qty: int) -> bool:
        return self._etf(etf, qty, +1)

    def redeem(self, etf: str, qty: int) -> bool:
        return self._etf(etf, qty, -1)

    def _etf(self, etf: str, qty: int, sign: int) -> bool:
        if not self.market_open or not self._action_ok():
            return False
        basket = self.case["etfs"][etf]["basket"]
        new = {etf: self.position[etf] + sign * qty}
        for s, n in basket.items():
            new[s] = self.position[s] - sign * n * qty
        if any(abs(v) > self.limits[s] for s, v in new.items()):
            self.rejected += 1
            return False
        self.position.update(new)  # booked at marks: cash neutral
        return True

    def pnl_by_symbol(self) -> dict[str, float]:
        return {s: self.cash_by[s] + self.position[s] * self.mid.get(s, 0.0) for s in self.symbols}

    def pnl(self) -> float:
        return self.cash + sum(self.position[s] * self.mid.get(s, 0.0) for s in self.symbols)

    # ---------- engine ----------
    def _fill(self, o: Order, qty: int, price: float, passive: bool) -> None:
        sign = 1 if o.side == "buy" else -1
        self.position[o.symbol] += sign * qty
        self.cash -= sign * qty * price
        self.cash_by[o.symbol] -= sign * qty * price
        o.filled += qty
        self.fills.append(Fill(self.t, o.symbol, o.side, qty, price, passive))
        if self.verbose:
            print(f"t={self.t:7.1f} fill {o.side:4s} {qty:4d} {o.symbol:5s} @ {price:.3f} {'passive' if passive else 'active'} pos={self.position[o.symbol]}")

    def _try_match(self, o: Order, passive: bool) -> None:
        if o.symbol not in self.quotes:
            return
        bid, ask = self.quotes[o.symbol]
        remaining = o.qty - o.filled
        if self.ladder is not None and self.ladder.has(o.symbol):
            if passive:
                # resting order: fills when the house re-quotes through our price, for the size the house posts at or
                # beyond our price (ladder walk with our price as the limit), at our price
                if (o.side == "buy" and o.price >= ask) or (o.side == "sell" and o.price <= bid):
                    got = sum(q for q, _ in self.ladder.fill(o.symbol, o.side, remaining, self.mid[o.symbol], self.t, o.price))
                    if got > 0:
                        self._fill(o, got, o.price, True)
                return
            for q, px in self.ladder.fill(o.symbol, o.side, remaining, self.mid[o.symbol], self.t, o.price):
                self._fill(o, q, px, False)
            return
        if self.depth:
            remaining = min(remaining, self.depth)
        if o.side == "buy" and (o.price is None or o.price >= ask):
            self._fill(o, remaining, ask, passive)
        elif o.side == "sell" and (o.price is None or o.price <= bid):
            self._fill(o, remaining, bid, passive)

    def _activate_pending(self) -> None:
        still = []
        for o in self.pending:
            if o.exec_t <= self.t:
                self._try_match(o, passive=False)
                if o.price is not None and o.filled < o.qty:
                    self.orders[o.id] = o
            else:
                still.append(o)
        self.pending = still

    def _advance_pending_before(self, timestamp: float) -> None:
        """Execute deadlines strictly before the next event or round close.

        Incoming market data wins timestamp ties, and orders due exactly at
        the close expire. Prices stay at the latest observed quote in between
        events; no strategy callback is synthesized for an order activation.
        """
        while self.pending:
            due = min(o.exec_t for o in self.pending)
            if due >= timestamp:
                break
            self.t = due
            self._activate_pending()

    def _on_price(self, prices: dict[str, float]) -> None:
        self.mid = prices
        if self.ladder is not None:
            self.quotes = {s: (self.ladder.best(s, "sell", p), self.ladder.best(s, "buy", p)) if self.ladder.has(s)
                           else (p * (1 - self.half_spread), p * (1 + self.half_spread)) for s, p in prices.items()}
        else:
            self.quotes = {s: (p * (1 - self.half_spread), p * (1 + self.half_spread)) for s, p in prices.items()}
        for oid in list(self.orders):
            o = self.orders[oid]
            self._try_match(o, passive=True)
            if o.filled >= o.qty:
                del self.orders[oid]

    def run(self, strategy: Any) -> float:
        strategy.on_start(self)
        last_round = 0
        for t, _, kind, payload in self.events:
            if t >= 3 * ROUND_SECS:
                break  # terminal frames cannot open a fourth trading round
            if last_round:
                self._advance_pending_before(min(t, last_round * ROUND_SECS))
            self.t = t
            rnd = int(t // ROUND_SECS) + 1
            if rnd != last_round:
                if last_round:
                    self.round_pnl[last_round] = self.pnl()
                self.round, last_round = rnd, rnd
                self.market_open = True
                self.orders.clear(); self.pending.clear()   # resting orders do not survive the close
                strategy.on_round(self)
            if kind == "price":
                self._on_price(payload)
                self._activate_pending()
                strategy.on_quotes(self)
                self.pnl_path.append((t, self.pnl()))
            else:
                self._activate_pending()
                strategy.on_news(self, payload)
        if last_round:
            close = last_round * ROUND_SECS
            self._advance_pending_before(close)
            self.t = close
        self.market_open = False
        self.orders.clear()
        self.pending.clear()
        self.mid = dict(self.settlement)
        self.round_pnl[3] = self.pnl()
        strategy.on_end(self)
        return self.pnl()
