"""Liquidity ladder fill model, calibrated from testnet order books (scripts/calibrate_book.py -> ladder.json).

For each symbol and side, cumulative size available within relative distance `bands[i]` of the mid. An aggressive
order walks the bands: the first band is filled at mid * (1 +/- spread/2), band i at mid * (1 +/- bands[i]).
Consumed size regenerates linearly over `refill_secs` (the house re-quotes; other teams' orders do not).
"""
from __future__ import annotations
import json
from pathlib import Path

DEFAULT = json.loads((Path(__file__).parent / "ladder.json").read_text()) if (Path(__file__).parent / "ladder.json").exists() else {}


class Ladder:
    def __init__(self, refill_secs: float = 10.0, scale: float = 1.0, table: dict | None = None):
        self.table = table or DEFAULT
        self.refill, self.scale = refill_secs, scale
        self.used: dict[tuple[str, str], list[float]] = {}     # consumed size per band
        self.last_t: dict[tuple[str, str], float] = {}

    def has(self, sym: str) -> bool:
        return sym in self.table

    def _avail(self, sym: str, side: str, t: float) -> list[float]:
        key = (sym, side)
        row = self.table[sym]
        cum = row["ask" if side == "buy" else "bid"]
        sizes = [cum[0]] + [cum[i] - cum[i - 1] for i in range(1, len(cum))]
        sizes = [max(0.0, s * self.scale) for s in sizes]
        used = self.used.setdefault(key, [0.0] * len(sizes))
        dt = t - self.last_t.get(key, t)
        self.last_t[key] = t
        if self.refill > 0 and dt > 0:
            for i, s in enumerate(sizes):
                used[i] = max(0.0, used[i] - s * dt / self.refill)
        return [max(0.0, s - u) for s, u in zip(sizes, used)]

    def best(self, sym: str, side: str, mid: float) -> float:
        sp = self.table[sym]["spread"] / 2
        return mid * (1 + sp) if side == "buy" else mid * (1 - sp)

    def fill(self, sym: str, side: str, qty: int, mid: float, t: float, limit: float | None) -> list[tuple[int, float]]:
        """Walk the ladder for an aggressive order. Returns [(qty, price)] filled (may be empty)."""
        row = self.table[sym]; bands = row["bands"]; sp = row["spread"] / 2
        avail = self._avail(sym, side, t)
        used = self.used[(sym, side)]
        out = []; left = qty
        for i, a in enumerate(avail):
            if left <= 0 or a <= 0:
                continue
            d = sp if i == 0 else bands[i]
            px = mid * (1 + d) if side == "buy" else mid * (1 - d)
            if limit is not None and ((side == "buy" and px > limit) or (side == "sell" and px < limit)):
                break
            q = int(min(left, a))
            if q <= 0:
                continue
            out.append((q, px)); used[i] += q; left -= q
        return out
