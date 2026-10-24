"""Auto-execution for the Mario desk: takes the engine's ranked actions and sends them, so that the only human input is
the race result. OFF unless desk.py runs with --auto-execute (bot submission needs the organisers' approval).

Order of work each poll: riskless arbs first, then model edges, best first. Before every order:
  1. the gate: auto-execution is on (`go`, not `stop`), the symbol map has no UNMAPPED entries, the rolling-minute
     order budget (--max-orders-per-min, default 36 against the packet's 40 browser orders a minute) has room;
  2. the book is re-read and the leg is re-sized to what is still available at prices no worse than its limit
     (the touch moving past the limit skips the leg; an arb with any leg short is skipped whole: it is only riskless
     complete);
  3. the position limit is re-checked against the latest positions.
Every submission is logged as an ORDER line (symbol, side, qty, price, outcome). The outcome comes from the next polls:
new trades in that symbol since the order (filled/partial), a resting order (open), or nothing (unconfirmed).
"""
from __future__ import annotations
import collections
import time
from dataclasses import dataclass, field
from typing import Callable

from mario.contracts import LIMITS
from mario.engine import Action, _walk


class RateLimiter:
    """At most max_per_min events in any rolling 60 s window."""
    def __init__(self, max_per_min: int, window: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.max, self.window, self.clock = int(max_per_min), window, clock
        self.times: collections.deque[float] = collections.deque()

    def _prune(self) -> None:
        now = self.clock()
        while self.times and now - self.times[0] >= self.window:
            self.times.popleft()

    def used(self) -> int:
        self._prune(); return len(self.times)

    def allow(self) -> bool:
        return self.used() < self.max

    def record(self) -> None:
        self.times.append(self.clock())

    def wait_for(self) -> float:
        """Seconds until the next slot (0 if one is free)."""
        self._prune()
        if len(self.times) < self.max:
            return 0.0
        return max(0.0, self.window - (self.clock() - self.times[0]))


def recheck_leg(leg: tuple, book: dict) -> tuple[int, float | None]:
    """Quantity of a leg (symbol, side, qty, limit_px) still available in a fresh normalised book at prices no worse than
    the limit, and the worst price it would pay. (0, None) when the touch has moved past the limit."""
    sym, side, qty, px = leg
    levels = [(float(l["price"]), int(l["quantity"])) for l in (book.get("asks" if side == "buy" else "bids") or [])]
    return _walk(levels, float(px), side, int(qty))


@dataclass
class Submission:
    t: float
    symbol: str
    side: str
    qty: int
    price: float
    kind: str
    response: str = ""
    outcome: str = "pending"
    polls: int = 0
    seen_trades: set = field(default_factory=set)
    filled: int = 0


class Executor:
    def __init__(self, submit: Callable[[str, str, int, float], str], read_book: Callable[[str], dict],
                 roles: dict[str, tuple], say: Callable[[str], None], max_per_min: int = 36, enabled: bool = True,
                 confirm_polls: int = 3, clock: Callable[[], float] = time.monotonic):
        self.submit, self.read_book, self.roles, self.say = submit, read_book, roles, say
        self.limiter = RateLimiter(max_per_min, clock=clock)
        self.enabled = enabled                  # `go` / `stop`
        self.confirm_polls = confirm_polls
        self.clock = clock
        self.pending: list[Submission] = []
        self.history: list[Submission] = []
        self.seen_trade_ids: set = set()
        self.skipped = 0

    # ---- gate ----
    def blocked(self, unmapped: list[str]) -> str | None:
        if not self.enabled:
            return "stopped (type `go` to resume)"
        if unmapped:
            return f"UNMAPPED symbols: {' '.join(unmapped)} (fix mario/contracts.json)"
        if not self.limiter.allow():
            return f"order budget used ({self.limiter.max}/min); next slot in {self.limiter.wait_for():.0f} s"
        return None

    @staticmethod
    def _room(roles: dict, sym: str, side: str, positions: dict) -> int:
        lim = LIMITS[roles[sym][0]]; pos = int((positions.get(sym) or {}).get("qty", 0) or 0)
        return max(0, lim - pos) if side == "buy" else max(0, lim + pos)

    def _sane_price(self, sym: str, px: float) -> bool:
        """Binaries settle in [0, 100], scores in [0, 120]: a limit outside that is a broken book, never an order."""
        hi = 100.0 if self.roles.get(sym, ("",))[0] in ("race", "swin") else 120.0
        return 0.0 < float(px) <= hi

    def _resize(self, action: Action, positions: dict) -> list[tuple] | None:
        """Re-read every leg's book; return the legs re-sized to what is still there, or None to skip the action."""
        legs = []
        for sym, side, qty, px in action.legs:
            if sym not in self.roles or not self._sane_price(sym, px):
                return None
            book = self.read_book(sym)
            avail, worst = recheck_leg((sym, side, qty, px), book)
            avail = min(avail, self._room(self.roles, sym, side, positions))
            if avail <= 0:
                return None
            legs.append((sym, side, int(avail), float(px)))
        if action.kind == "arb":
            q = min(l[2] for l in legs)            # a riskless set is only riskless complete: equal size on every leg
            if q < min(l[2] for l in action.legs):
                # the book thinned since ranking: still fine as long as every leg has q, otherwise skip
                if q <= 0:
                    return None
            legs = [(s, sd, q, px) for s, sd, _, px in legs]
        return legs

    # ---- one pass over the ranked actions ----
    def run(self, actions: list[Action], positions: dict, unmapped: list[str], max_actions: int = 3, max_orders: int = 8) -> int:
        """Execute up to max_actions actions and max_orders orders this pass (arbs first, then by profit), so one poll never
        spends the whole minute's budget. Returns the number of orders sent."""
        sent = 0
        why = self.blocked(unmapped)
        if why:
            return 0
        ordered = sorted(actions, key=lambda a: (0 if a.kind == "arb" else 1, -a.profit))
        done = 0
        for act in ordered:
            if done >= max_actions or sent >= max_orders:
                break
            if len(act.legs) > min(self.limiter.max - self.limiter.used(), max_orders - sent):
                self.skipped += 1
                continue                           # not enough budget for every leg of this action now
            legs = self._resize(act, positions)
            if legs is None:
                self.skipped += 1
                self.say(f"skip {act.kind} {act.note}: book moved past the limit or no room")
                continue
            sent_legs = 0
            for sym, side, qty, px in legs:
                why = self.blocked(unmapped)
                if why:
                    self.say(f"stop sending: {why}")
                    if 0 < sent_legs < len(legs):
                        self.say(f"INCOMPLETE {act.kind.upper()}: {sent_legs}/{len(legs)} legs sent ({act.note}); the rest must go by hand or the position is naked")
                    return sent
                sub = Submission(self.clock(), sym, side, qty, px, act.kind)
                try:
                    sub.response = str(self.submit(sym, side, qty, px))[:160]
                except Exception as exc:
                    sub.response = f"error: {exc}"; sub.outcome = "failed"
                self.limiter.record(); sent += 1
                if sub.outcome == "failed":
                    self.history.append(sub)
                    self.say(f"ORDER {sym} {side} {qty} @ {px:.2f} ({act.kind}) -> FAILED {sub.response}")
                    if len(legs) > 1:
                        self.say(f"INCOMPLETE {act.kind.upper()}: {sent_legs}/{len(legs)} legs sent ({act.note}); the rest must go by hand or the position is naked")
                    return sent                     # a failure means the tap is in trouble: stop this pass, the next poll recovers
                self.pending.append(sub); sent_legs += 1
                self.say(f"ORDER {sym} {side} {qty} @ {px:.2f} ({act.kind}) -> sent: {sub.response}")
                # positions change with the fill; keep the room check honest within this pass
                p = positions.setdefault(sym, {"qty": 0})
                p["qty"] = int(p.get("qty", 0) or 0) + (qty if side == "buy" else -qty)
            done += 1
        return sent

    # ---- confirmation from the next snapshots ----
    def verify(self, snap: dict) -> None:
        trades = snap.get("trades") or []
        open_orders = snap.get("open_orders") or []
        new = [t for t in trades if t.get("trade_id", id(t)) not in self.seen_trade_ids]
        for t in trades:
            self.seen_trade_ids.add(t.get("trade_id", id(t)))
        for sub in list(self.pending):
            sub.polls += 1
            mine = [t for t in new if t.get("symbol") == sub.symbol and str(t.get("side", sub.side)).lower() == sub.side]
            sub.filled += sum(int(t.get("quantity", 0)) for t in mine)
            resting = any(o.get("symbol") == sub.symbol and str(o.get("side", "")).lower() == sub.side for o in open_orders)
            if sub.filled >= sub.qty:
                sub.outcome = "filled"
            elif sub.polls >= self.confirm_polls:
                sub.outcome = f"partial {sub.filled}/{sub.qty}" if sub.filled else ("open (resting)" if resting else "unconfirmed (no fill seen)")
            else:
                continue
            self.pending.remove(sub); self.history.append(sub)
            self.say(f"ORDER {sub.symbol} {sub.side} {sub.qty} @ {sub.price:.2f} ({sub.kind}) -> {sub.outcome}")

    def summary(self) -> dict:
        return {"enabled": self.enabled, "used_min": self.limiter.used(), "max_min": self.limiter.max,
                "sent": len(self.history) + len(self.pending), "pending": len(self.pending), "skipped": self.skipped,
                "filled": sum(1 for s in self.history if s.outcome == "filled"),
                "failed": sum(1 for s in self.history if s.outcome == "failed" or s.outcome.startswith("unconfirmed"))}
