"""Strategies for the offline simulator and (later) the live bot. Each keeps a SeasonModel and trades fair vs quotes."""
from __future__ import annotations
import math
from typing import Any
from .valuation import SeasonModel, SYMS
from .analog import AnalogEnsemble


class Strategy:
    def on_start(self, sim) -> None: ...
    def on_round(self, sim) -> None: ...
    def on_news(self, sim, m: dict[str, Any]) -> None: ...
    def on_quotes(self, sim) -> None: ...
    def on_end(self, sim) -> None: ...


class DoNothing(Strategy):
    pass


class FairValueTrader(Strategy):
    """Trades toward a target position proportional to the edge between fair value and the house quotes.

    edge_full: edge (fraction of mid) at which the target is the full position limit.
    min_edge:  below this edge we do not add (covers spread and model noise); per-symbol floors from the valuation residual.
    The edge is scaled by `confidence` in [0, 1], which rises as the storm resolves.
    """

    def __init__(self, min_edge: float = 0.01, edge_full: float = 0.05, rebalance_every: float = 15.0,
                 symbols: list[str] | None = None, project: bool = True, analog: bool = False,
                 sd_mult: float = 1.0, loss_limit: float | None = None, prior_mode: str = "sample",
                 passive: float = 0.0, warmup: float = 0.0, future_sd: float = 0.0, fair_jump: float = 0.0, max_cross: float = 0.0, **analog_kw):
        self.prior_mode = prior_mode
        self.max_cross = max_cross      # >0: an aggressive order never pays more than this fraction through the touch
                                        # (live, the house's book empties for a few seconds while it re-prices after a report)
        self.fair_jump = fair_jump      # >0: do not trade a symbol in a cycle where its fair moved by more than this
                                        # fraction since the previous cycle (model still catching up after a (re)connect)
        self.future_sd = future_sd      # multiple of the future-storm valuation sd added to the edge floor
        self.warmup = warmup            # seconds after a round opens during which we do not trade (opening prices settle)
        self.passive = passive          # >0: when the edge is below the floor, rest an order inside the spread at the
                                        # price where the edge equals passive * floor (a passive fill does not pay the spread)
        self.min_edge, self.edge_full, self.every = min_edge, edge_full, rebalance_every
        self.loss_limit = loss_limit                        # per symbol per round: stop adding once this much is lost
        self.symbols = symbols or SYMS
        self.project, self.analog, self.sd_mult, self.analog_kw = project, analog, sd_mult, analog_kw
        self.exit_slip = 0.01                               # how far through the book we go to exit a wrong position
        self.paused: set[str] = set()

    def on_start(self, sim) -> None:
        self.model = SeasonModel(sim.case)
        self.model.prior_mode = self.prior_mode
        self.model.future_sd_mult = self.future_sd
        if self.analog:
            self.model.ensemble = AnalogEnsemble(sim.case, **self.analog_kw)
        self.last_trade_t = -1e9
        self.fair: dict[str, float] = {}
        self.paused = set()
        self.cell_pnl: dict[tuple[str, int], float] = {}    # mark-to-mid pnl per (symbol, round), approximating fills at mid
        self.last_mid: dict[str, float] = {}
        self.prev_fair: dict[str, float] = {}
        self.passive_order: dict[str, tuple[str, float, float]] = {}   # symbol -> (side, price, t) of our resting quote
        self.round_open_t = -1e9

    def on_round(self, sim) -> None:
        self.round_open_t = sim.t

    def pause(self, symbols: list[str]) -> None:
        """Stop trading symbols named in a live announcement until a human clears them (model has not seen announcements)."""
        self.paused |= set(symbols)

    def compute_fair(self) -> dict[str, float]:
        return self.model.fair_analog() if self.analog else self.model.fair(self.project)

    def on_news(self, sim, m: dict[str, Any]) -> None:
        self.model.on_message(m)
        if m["type"] in ("damage_report", "advisory", "storm_formed", "storm_dissipated"):
            self.fair = self.compute_fair()
            self.last_trade_t = -1e9   # react immediately

    def confidence(self, sim) -> float:
        """How much of the fair-mid gap to believe. 1 after the final report; decays with storm uncertainty before.
        With the analog ensemble the uncertainty is in the edge floor instead, so confidence is 1 once a storm exists."""
        md = self.model
        if md.round == 0:
            return 0.0
        if self.analog:
            return 1.0 if md.last_obs is not None or md.storm_reported else 0.0
        if md.storm_reported:
            return 1.0 if md.round == 3 else 0.7
        if not md.storm_active and md.last_obs is not None:
            return 0.6 if md.round == 3 else 0.45
        if md.last_obs is None:
            return 0.1
        age = md.last_obs["age"]
        return 0.15 + 0.45 * min(1.0, age / sim.case["timing"]["storm"])

    def min_edge_for(self, sim, s: str) -> float:
        """Per-symbol edge floor: the global floor, or twice the model's residual sd for symbols still uncertain."""
        sd = self.model.resid_sd(s)
        if self.analog:
            sd = math.hypot(sd, self.sd_mult * self.model.fair_sd.get(s, 0.0))
        return max(self.min_edge, 2.0 * sd / max(1e-9, sim.mid[s]))

    def on_quotes(self, sim) -> None:
        if sim.t - self.last_trade_t < self.every or sim.t - self.round_open_t < self.warmup:
            return
        self.last_trade_t = sim.t
        if self.model.storm_active:
            self.fair = self.compute_fair()
        if not self.fair:
            return
        rnd = getattr(sim, "round", 1)
        for s in self.symbols:
            if s in sim.mid:
                if s in self.last_mid:
                    self.cell_pnl[(s, rnd)] = self.cell_pnl.get((s, rnd), 0.0) + sim.position[s] * (sim.mid[s] - self.last_mid[s])
                self.last_mid[s] = sim.mid[s]
        conf = self.confidence(sim)
        if conf <= 0:
            return                      # no view: hold whatever we have
        unsettled: set[str] = set()
        if self.fair_jump > 0:
            for s in self.symbols:
                f, pf = self.fair.get(s), self.prev_fair.get(s)
                if f is not None and (pf is None or abs(f - pf) / max(1e-9, sim.mid.get(s, f)) > self.fair_jump):
                    unsettled.add(s)
                if f is not None:
                    self.prev_fair[s] = f
        for s in self.symbols:
            if s in self.paused or s not in sim.quotes or s in unsettled:
                continue
            bid, ask = sim.quotes[s]
            mid = sim.mid[s]
            f = self.fair[s]
            edge = (f - mid) / mid * conf
            lim = sim.limits[s]
            floor = self.min_edge_for(sim, s)
            pos = sim.position[s]
            stopped = self.loss_limit is not None and self.cell_pnl.get((s, rnd), 0.0) < -self.loss_limit
            if abs(edge) >= floor:
                frac = min(1.0, (abs(edge) - floor) / max(1e-9, self.edge_full - floor))
                target = int(round(lim * frac)) * (1 if edge > 0 else -1)
                if stopped:                                 # this symbol has lost its budget this round: reduce only
                    target = 0 if target * pos <= 0 else (min(target, pos) if pos > 0 else max(target, pos))
                    if target == pos:
                        continue
            elif pos and ((pos > 0 and edge < -floor * 0.5) or (pos < 0 and edge > floor * 0.5)):
                target = 0                                  # we are now on the wrong side: get out
            else:
                if self.passive > 0:
                    self.quote_passive(sim, s, f, bid, ask, conf, floor, lim, pos)
                continue                                    # small edge: hold; settlement converges for free
            self.passive_order.pop(s, None)
            resting_net = sim.resting(s, "buy") - sim.resting(s, "sell")
            delta = target - pos - resting_net
            if delta == 0:
                continue
            if resting_net != 0:
                sim.cancel_all(s)                           # replace stale resting orders rather than stack more
                delta = target - pos
                if delta == 0:
                    continue
            # pay up to the price at which the remaining edge equals the floor (liquidity-aware limit)
            keep = floor / max(conf, 1e-9)
            if delta > 0:
                limit = max(ask, f / (1 + keep)) if target != 0 else ask * (1 + self.exit_slip)
                if limit < ask and target != 0:
                    continue
                if self.max_cross > 0:
                    limit = min(limit, ask * (1 + self.max_cross))
                sim.place(s, "buy", delta, limit)
            else:
                limit = min(bid, f / (1 - keep)) if target != 0 else bid * (1 - self.exit_slip)
                if limit > bid and target != 0:
                    continue
                if self.max_cross > 0:
                    limit = max(limit, bid * (1 - self.max_cross))
                sim.place(s, "sell", -delta, limit)


    def quote_passive(self, sim, s: str, f: float, bid: float, ask: float, conf: float, floor: float, lim: int, pos: int) -> None:
        """Rest one order inside the spread where the edge (after confidence) equals passive * floor; replace it only when
        the price moves. Fills come from the house re-quoting through us or other participants crossing."""
        keep = self.passive * floor / max(conf, 1e-9)
        tick = 0.01
        if f > bid:                                   # fair above the bid: bid inside the spread
            side, px = "buy", min(f / (1 + keep), ask - tick)
            if px <= bid:
                side = None
        elif f < ask:
            side, px = "sell", max(f / (1 - keep), bid + tick)
            if px >= ask:
                side = None
        else:
            side = None
        if side is None:
            if s in self.passive_order:
                sim.cancel_all(s); self.passive_order.pop(s, None)
            return
        px = round(px, 2)
        edge_at = abs(f - px) / px * conf
        frac = min(1.0, (edge_at - self.passive * floor) / max(1e-9, self.edge_full - self.passive * floor))
        target = int(round(lim * frac)) * (1 if side == "buy" else -1)
        qty = (target - pos) if side == "buy" else (pos - target)
        if qty <= 0:
            if s in self.passive_order:
                sim.cancel_all(s); self.passive_order.pop(s, None)
            return
        old = self.passive_order.get(s)
        if old and old[0] == side and abs(old[1] - px) / px < 0.001 and sim.t - old[2] < 120:
            return                                    # our quote is still where we want it
        if old or sim.resting(s, "buy") or sim.resting(s, "sell"):
            sim.cancel_all(s)
        if sim.place(s, side, qty, px) is not None:
            self.passive_order[s] = (side, px, sim.t)
        else:
            self.passive_order.pop(s, None)


class FinalReportOnly(FairValueTrader):
    """Only trades after the round-3 final damage report, when settlement is known exactly: validates the pipeline
    and measures the end-of-round tactic on its own."""

    def confidence(self, sim) -> float:
        md = self.model
        return 1.0 if (md.storm_reported and md.round == 3) else 0.0
