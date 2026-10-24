"""Runtime commands for the live bot, one per line, appended to a text file the bot polls (default recordings/control.txt).

    echo "HAVEN -6%"      >> recordings/control.txt   # fair = model fair x 0.94 from now on; HAVEN resumes trading
    echo "GEN +3"         >> recordings/control.txt   # fair = model fair + 3 points
    echo "PORT =61.5"     >> recordings/control.txt   # shift PORT's fair so it is 61.5 now; the model keeps moving it
    echo "resume HAVEN"   >> recordings/control.txt   # trade on the unadjusted model again (announcement judged irrelevant)
    echo "clear HAVEN"    >> recordings/control.txt   # drop the adjustment and resume
    echo "pause GEN MAT"  >> recordings/control.txt   # stop trading these (cancels their orders)
    echo "status"         >> recordings/control.txt   # print paused symbols and adjustments to the log

Why: a live announcement changes a company's economics and the model has never seen one. The bot pauses the named
symbols; after `--announce-wait` seconds it re-anchors each fair to the house mid and resumes on its own. These
commands let a human act sooner or differently. Blank lines and lines starting with # are ignored.
"""
from __future__ import annotations
import math
import os
from typing import Any

from ctc.valuation import SYMS


def parse_control(line: str) -> dict[str, Any] | None:
    """Parse one command line into {'op': ..., ...}; None for blank/comment lines. Raises ValueError on a bad command."""
    text = line.split("#", 1)[0].strip()
    if not text:
        return None
    parts = text.split()
    head = parts[0].lower()
    if head == "status":
        return {"op": "status"}
    if head in ("pause", "resume", "clear"):
        symbols = [p.upper() for p in parts[1:]]
        if not symbols or any(s not in SYMS for s in symbols):
            raise ValueError(f"{head} needs one or more of {' '.join(SYMS)}")
        return {"op": head, "symbols": symbols}
    sym = parts[0].upper()
    if sym not in SYMS:
        raise ValueError(f"unknown symbol or command {parts[0]!r}")
    if len(parts) != 2:
        raise ValueError(f"{sym}: expected one value, e.g. '{sym} -6%', '{sym} +3' or '{sym} =42.5'")
    v = parts[1]
    try:
        if v.startswith("="):
            price = float(v[1:])
            if not math.isfinite(price) or price <= 0:
                raise ValueError
            return {"op": "anchor", "symbol": sym, "price": price}
        if v.endswith("%"):
            pct = float(v[:-1])
            if not math.isfinite(pct) or pct <= -100:
                raise ValueError
            return {"op": "adjust", "symbol": sym, "mult": 1 + pct / 100, "add": 0.0}
        add = float(v)
        if not math.isfinite(add):
            raise ValueError
        return {"op": "adjust", "symbol": sym, "mult": 1.0, "add": add}
    except ValueError:
        raise ValueError(f"{sym}: bad value {v!r} (use -6%, +3 or =42.5)") from None


def apply_control(strat, sim, line: str) -> str | None:
    """Apply one command to the strategy; returns the log line (None for blank lines). Bad commands return an error line."""
    try:
        cmd = parse_control(line)
    except ValueError as exc:
        return f"CONTROL error: {exc}"
    if cmd is None:
        return None
    op = cmd["op"]
    if op == "status":
        adj = ", ".join(f"{s} x{m:.4g}{a:+.2f}" for s, (m, a) in sorted(strat.adjust.items())) or "none"
        return f"CONTROL status: paused {sorted(strat.paused) or 'none'}; adjustments {adj}"
    if op == "pause":
        strat.pause(cmd["symbols"])
        return f"CONTROL paused {' '.join(cmd['symbols'])}"
    if op == "resume":
        strat.resume(cmd["symbols"])
        return f"CONTROL resumed {' '.join(cmd['symbols'])} (adjustments kept)"
    if op == "clear":
        for s in cmd["symbols"]:
            strat.set_adjust(s, 1.0, 0.0)
        return f"CONTROL cleared and resumed {' '.join(cmd['symbols'])}"
    sym = cmd["symbol"]
    if op == "anchor":
        off = strat.anchor(sym, cmd["price"])
        if off is None:
            return f"CONTROL error: no model fair for {sym} yet"
        return f"CONTROL {sym} fair anchored to {cmd['price']:.2f} (offset {off:+.2f}); resumed"
    strat.set_adjust(sym, cmd["mult"], cmd["add"])
    f = strat.fair.get(sym)
    shown = f"; fair now {f:.2f}" if f is not None else ""
    return f"CONTROL {sym} fair = model x{cmd['mult']:.4g} {cmd['add']:+.2f}{shown}; resumed"


class ControlFile:
    """Tails a command file: each poll applies the lines appended since the last one. A missing file is fine."""
    def __init__(self, path: str):
        self.path = path
        self.offset = 0
        marker = path + '.replay'
        if os.path.exists(marker):                 # the bot restarted itself: re-apply this run's commands in order
            try:
                os.remove(marker)
            except OSError:
                pass
            return
        try:
            self.offset = os.path.getsize(path)    # commands already in the file belong to an earlier run
        except OSError:
            pass

    def poll(self, strat, sim) -> list[str]:
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return []
        if size < self.offset:                       # truncated or replaced: start over
            self.offset = 0
        if size == self.offset:
            return []
        with open(self.path, "r", encoding="utf-8", errors="replace") as fh:
            fh.seek(self.offset)
            chunk = fh.read()
        if chunk and not chunk.endswith("\n"):       # a line still being written: wait for its newline
            chunk = chunk[: chunk.rfind("\n") + 1]
        self.offset += len(chunk.encode("utf-8"))
        out = []
        for line in chunk.splitlines():
            msg = apply_control(strat, sim, line)
            if msg:
                out.append(msg)
        return out
