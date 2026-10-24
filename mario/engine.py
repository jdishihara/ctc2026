"""Mario Markets decision engine: fair values (mario/pricer.py) + live books + positions -> ranked actions.

Two kinds of recommendation, both sized to the position limits and to what is actually in the book:
  1. model-free (riskless at settlement): the four race-winner contracts of one race sum to exactly 100, the four
     series-winner contracts together pay between 100 and 200 (each tied winner pays 50), top-2 total = #1 + #2, and every score
     contract is bounded by the points already banked and the points still available. When the book violates one of
     these, the engine prints the legs and the locked-in profit.
  2. model edges: buy below fair minus a margin, sell above fair plus a margin. The margin is wider early in a series
     (the skill posterior is weak) and scales with the score contracts' posterior sd.
Everything is a suggestion: the humans click (the packet allows bots to assist; orders go through the UI).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from mario.contracts import LIMITS, RACERS, role_label, series_of

BIN_KINDS = ("race", "swin")


@dataclass
class Params:
    margin_bin: tuple = (6.0, 4.0, 3.0, 2.5)   # binaries: by races completed in that contract's series (0, 1, 2, 3)
    margin_score_pts: float = 2.0              # score contracts: at least this many points of edge
    margin_score_sd: float = 0.35              # ... and at least this fraction of the posterior sd
    risk_pts: float = 1500.0                   # score contracts: size * sd <= risk_pts
    clip: int = 50                             # never recommend more than this many contracts per action
    min_profit: float = 5.0                    # do not list actions worth less than this (contract points)
    model_sd_k: float = 1.0                    # margin >= k x sd of the fair across the parameter ensemble (mario/robustness.py); 0 disables
    edge_pos_frac: float = 0.5                 # model-edge positions use at most this fraction of the exchange limit; riskless arbs use all of it


@dataclass
class Action:
    kind: str                                  # "edge" or "arb"
    legs: list = field(default_factory=list)   # [(symbol, side, qty, price)]
    profit: float = 0.0                        # expected (edge) or locked (arb) profit in contract points
    note: str = ""


def _walk(levels: list, limit_px: float, side: str, max_qty: int) -> tuple[int, float]:
    """Quantity available at prices no worse than limit_px (asks when buying, bids when selling) and the worst price."""
    qty, worst = 0, None
    for px, q in levels:
        if (side == "buy" and px > limit_px) or (side == "sell" and px < limit_px):
            break
        take = min(int(q), max_qty - qty)
        if take <= 0:
            break
        qty += take; worst = px
    return qty, worst


class Engine:
    def __init__(self, roles: dict[str, tuple], params: Params | None = None):
        self.roles = roles
        self.p = params or Params()
        self.by_role = {r: s for s, r in roles.items()}

    # ---- fair per symbol from the pricer's role-keyed fairs ----
    def fair_table(self, fairs: dict) -> dict[str, tuple[float, float]]:
        out = {}
        for sym, role in self.roles.items():
            kind = role[0]
            if kind in BIN_KINDS:
                arr = fairs.get((kind, role[1]))
                if arr is None or role[2] not in RACERS:
                    continue
                v = float(arr[RACERS.index(role[2])])
                v = v * 100.0 if kind == "race" else v
                out[sym] = (v, (v * (100 - v)) ** 0.5 / 10)         # sd in points of a 100-settling binary, scaled down
            else:
                ms = fairs.get((kind, role[1]))
                if ms is not None:
                    out[sym] = (float(ms[0]), float(ms[1]))
        return out

    def bounds(self, fairs: dict, n_done: int) -> dict[str, tuple[float, float]]:
        """Hard settlement bounds of the score contracts from banked points and races left in the series."""
        out = {}
        for sym, role in self.roles.items():
            if role[0] in BIN_KINDS:
                continue
            s = role[1]; pts = sorted(fairs["points"][s - 1], reverse=True)
            rem = 4 - max(0, min(4, n_done - (s - 1) * 4))
            if role[0] == "s1":
                out[sym] = (pts[0], pts[0] + 15 * rem)
            elif role[0] == "s2":
                out[sym] = (pts[1], min(pts[1] + 15 * rem, (pts[0] + pts[1] + 27 * rem) / 2))
            else:
                out[sym] = (pts[0] + pts[1], pts[0] + pts[1] + 27 * rem)
        return out

    def _room(self, sym: str, side: str, positions: dict, frac: float = 1.0) -> int:
        lim = int(LIMITS[self.roles[sym][0]] * frac); pos = int(positions.get(sym, {}).get("qty", 0) or 0)
        return max(0, lim - pos) if side == "buy" else max(0, lim + pos)

    # ---- the evaluation ----
    def evaluate(self, fairs: dict, books: dict, positions: dict, n_done: int, tradable: set | None = None,
                 model_sd: dict | None = None) -> dict:
        """model_sd: symbol -> sd of the fair across the parameter ensemble (points); widens the edge margin."""
        ft = self.fair_table(fairs); bd = self.bounds(fairs, n_done); model_sd = model_sd or {}
        rows, actions = [], []
        for sym, role in sorted(self.roles.items(), key=lambda kv: (series_of(kv[1]), kv[1])):
            book = books.get(sym) or {}
            bids = [(float(b["price"]), int(b["quantity"])) for b in book.get("bids", [])]
            asks = [(float(a["price"]), int(a["quantity"])) for a in book.get("asks", [])]
            fv, sd = ft.get(sym, (None, None))
            pos = positions.get(sym, {})
            row = {"symbol": sym, "role": role_label(role), "kind": role[0], "series": series_of(role), "fair": fv, "sd": sd,
                   "bid": bids[0][0] if bids else None, "bid_qty": bids[0][1] if bids else 0,
                   "ask": asks[0][0] if asks else None, "ask_qty": asks[0][1] if asks else 0,
                   "pos": int(pos.get("qty", 0) or 0), "avg": pos.get("avg"), "lo": bd.get(sym, (None, None))[0], "hi": bd.get(sym, (None, None))[1],
                   "edge_buy": None, "edge_sell": None, "action": "", "model_sd": model_sd.get(sym)}
            if fv is not None:
                if asks: row["edge_buy"] = round(fv - asks[0][0], 2)
                if bids: row["edge_sell"] = round(bids[0][0] - fv, 2)
                live = tradable is None or sym in tradable
                if live:
                    actions += self._edge_actions(sym, role, fv, sd, bids, asks, positions, n_done, model_sd.get(sym))
            rows.append(row)
        actions += self._arbs(books, positions, bd, tradable)
        actions = [a for a in actions if a.profit >= self.p.min_profit]
        actions.sort(key=lambda a: -a.profit)
        for a in actions:
            for sym, side, qty, px in a.legs:
                r = next(r for r in rows if r["symbol"] == sym)
                if not r["action"]:
                    r["action"] = f"{side.upper()} {qty} @ {px}"
        pnl = self._pnl(ft, positions)
        return {"rows": rows, "actions": actions, "pnl": pnl}

    def _edge_actions(self, sym, role, fv, sd, bids, asks, positions, n_done, msd: float | None = None) -> list[Action]:
        out = []
        if role[0] in BIN_KINDS:
            k = max(0, min(3, n_done - (series_of(role) - 1) * 4))
            margin = self.p.margin_bin[k]
            max_qty = self.p.clip
        else:
            margin = max(self.p.margin_score_pts, self.p.margin_score_sd * sd)
            max_qty = min(self.p.clip, int(self.p.risk_pts / max(sd, 0.5)))
        note_sd = ""
        if msd is not None and self.p.model_sd_k > 0 and self.p.model_sd_k * msd > margin:
            margin = self.p.model_sd_k * msd            # the parameterisations disagree by more than the margin: demand that much edge
            note_sd = f", model sd {msd:.1f}"
        for side, levels, limit_px in (("buy", asks, fv - margin), ("sell", bids, fv + margin)):
            qty, worst = _walk(levels, limit_px, side, min(max_qty, self._room(sym, side, positions, self.p.edge_pos_frac)))
            if qty > 0:
                exp = sum((fv - px if side == "buy" else px - fv) * q for px, q in self._taken(levels, qty))
                out.append(Action("edge", [(sym, side, qty, worst)], round(exp, 1), f"{role_label(role)}: fair {fv:.1f} (sd {sd:.1f}), margin {margin:.1f}{note_sd}"))
        return out

    @staticmethod
    def _taken(levels, qty):
        out, left = [], qty
        for px, q in levels:
            t = min(q, left); out.append((px, t)); left -= t
            if left <= 0:
                break
        return out

    def _arbs(self, books, positions, bd, tradable) -> list[Action]:
        out = []
        def touch(sym, side):
            b = books.get(sym) or {}
            lv = b.get("asks" if side == "buy" else "bids") or []
            if not lv or (tradable is not None and sym not in tradable):
                return None
            return float(lv[0]["price"]), int(lv[0]["quantity"])
        # complete sets of binaries
        groups: dict[tuple, list[str]] = {}
        for sym, role in self.roles.items():
            if role[0] in BIN_KINDS:
                groups.setdefault((role[0], role[1]), []).append(sym)
        for key, syms in groups.items():
            if len(syms) != 4:
                continue
            for side, sign in (("buy", 1), ("sell", -1)):
                ts = [touch(s, side) for s in syms]
                if any(t is None for t in ts):
                    continue
                total = sum(t[0] for t in ts)
                # The packet pays each tied series winner 50, including three-
                # and four-way ties. Only race sets always settle to 100.
                bound = 200 if key[0] == "swin" and side == "sell" else 100
                gain = (bound - total) if side == "buy" else (total - bound)
                if gain <= 0:
                    continue
                qty = min(min(t[1] for t in ts), self.p.clip, *(self._room(s, side, positions) for s in syms))
                if qty > 0:
                    out.append(Action("arb", [(s, side, qty, t[0]) for s, t in zip(syms, ts)], round(gain * qty, 1),
                                      f"{'race' if key[0] == 'race' else 'series'} {key[1]} set {side}s {total:.1f} vs {bound}"))
        # top2 = s1 + s2
        for s in (1, 2):
            s1, s2, t2 = self.by_role.get(("s1", s)), self.by_role.get(("s2", s)), self.by_role.get(("top2", s))
            if not (s1 and s2 and t2):
                continue
            for legs, label in ((((t2, "buy"), (s1, "sell"), (s2, "sell")), "top-2 cheap vs #1+#2"),
                                (((t2, "sell"), (s1, "buy"), (s2, "buy")), "top-2 rich vs #1+#2")):
                ts = [touch(sym, side) for sym, side in legs]
                if any(t is None for t in ts):
                    continue
                cash = sum((t[0] if side == "sell" else -t[0]) for (sym, side), t in zip(legs, ts))
                if cash <= 0:
                    continue
                qty = min(min(t[1] for t in ts), self.p.clip, *(self._room(sym, side, positions) for sym, side in legs))
                if qty > 0:
                    out.append(Action("arb", [(sym, side, qty, t[0]) for (sym, side), t in zip(legs, ts)], round(cash * qty, 1), f"series {s} {label}: {cash:.1f}/contract"))
        # hard bounds of the score contracts
        for sym, (lo, hi) in bd.items():
            for side, bound in (("buy", lo), ("sell", hi)):
                t = touch(sym, side)
                if t is None:
                    continue
                gain = (bound - t[0]) if side == "buy" else (t[0] - bound)
                if gain > 0:
                    qty = min(t[1], self.p.clip, self._room(sym, side, positions))
                    if qty > 0:
                        out.append(Action("arb", [(sym, side, qty, t[0])], round(gain * qty, 1), f"{role_label(self.roles[sym])} outside its hard bound [{lo:.0f}, {hi:.0f}]"))
        return out

    def _pnl(self, ft, positions) -> dict:
        mtf = realized = 0.0
        for sym, p in positions.items():
            q = int(p.get("qty", 0) or 0); avg = p.get("avg"); fv = ft.get(sym, (None,))[0]
            if q and avg is not None and fv is not None:
                mtf += q * (fv - float(avg))
            realized += float(p.get("realized", 0) or 0)
        return {"realized": round(realized, 1), "mark_to_fair": round(mtf, 1), "total": round(realized + mtf, 1)}
