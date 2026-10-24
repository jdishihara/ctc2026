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
                 passive: float = 0.0, warmup: float = 0.0, future_sd: float = 0.0, fair_jump: float = 0.0, max_cross: float = 0.0,
                 carry: float = 1.0, ent_cut: float = 0.0, rebuild_min_edge: float = 0.0, late_cut: float = 0.0,
                 edge_ramp: float = 0.0, final_exact: bool = False, final_edge: float = 0.0,
                 final_edge_full: float = 0.0, price_gate: float = 0.0,
                 price_drift: float = 0.0, basket_edge: float = 0.0,
                 basket_participation: float = 0.0, announce_wait: float = 60.0, **analog_kw):
        for name, value in (("price_gate", price_gate), ("price_drift", price_drift), ("basket_edge", basket_edge)):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        self.price_gate, self.price_drift = price_gate, price_drift
        self.basket_edge = basket_edge
        if not 0 <= basket_participation <= 1:
            raise ValueError('basket_participation must be between zero and one')
        self.basket_participation = basket_participation
        if not math.isfinite(edge_ramp) or edge_ramp < 0:
            raise ValueError("edge_ramp must be finite and nonnegative")
        self.edge_ramp = edge_ramp      # minimum excess edge from the floor to full size (0 preserves the old rule)
        self.final_exact = final_exact
        if not math.isfinite(final_edge) or final_edge < 0:
            raise ValueError("final_edge must be finite and nonnegative")
        self.final_edge = final_edge  # optional entry floor only after all final reports and exact valuations
        if not math.isfinite(final_edge_full) or final_edge_full < 0:
            raise ValueError("final_edge_full must be finite and nonnegative")
        self.final_edge_full = final_edge_full
        self.prior_mode = prior_mode
        self.carry = carry              # <1: between storms (after a final report, before the next storm forms) the position
                                        # limit is carry x the exchange limit, so less rides on the next storm's path
        self.ent_cut = ent_cut          # >0: do not add to a position while the pattern posterior's entropy exceeds this (nats)
        self.rebuild_min_edge = rebuild_min_edge   # >0: edge floor for RECON/MAT/GEN (with the exact settlement rules their residual is ~0)
        self.late_cut = late_cut        # >0: do not add to a position once the storm is older than this many seconds (late fills earn nothing)
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
        self.announce_wait = announce_wait  # >0: a symbol paused by a live announcement resumes after this many seconds with its
                                            # fair re-anchored to the house mid (the house reprices in ~45 s); 0 = wait for a human
        self.adjust: dict[str, tuple[float, float]] = {}    # symbol -> (mult, add) applied to the model's fair (announcements)
        self.announce_t: dict[str, float] = {}
        self.log = print

    def on_start(self, sim) -> None:
        self.competition_id = getattr(sim, 'competition_id', None)
        self.basket = None
        if self.basket_edge:
            from .basket import BasketOverlay
            self.basket = BasketOverlay(self.basket_edge, participation=self.basket_participation)
        self.price_signal = None
        if self.price_gate or self.price_drift:
            from .price_signal import PriceSignal
            self.price_signal = PriceSignal()
        self._price_round_start = None  # Anchor only to observed storm age, including after reconnect.
        self._price_round = getattr(sim, 'round', 0)
        self.model = SeasonModel(sim.case, final_exact=self.final_exact)
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
        self.pause_cancel_t: dict[str, float] = {}
        self.pause_pending: set[str] = set()
        self.adjust = {}
        self.announce_t = {}

    def on_round(self, sim) -> None:
        self.round_open_t = sim.t
        if self.basket is not None:
            self.basket.on_round(sim)
        self._price_round_start = None
        self._price_round = getattr(sim, 'round', 0)
        if self.price_signal is not None:
            self.price_signal.reset()

    def pause(self, symbols: list[str]) -> None:
        """Stop trading symbols until resume(): cancel their orders, place none (the model has not seen announcements)."""
        self.paused |= set(symbols)
        self.pause_pending.update(symbols)

    def announce(self, symbols: list[str], t: float) -> None:
        """A live announcement named these symbols: pause them; after announce_wait seconds on_quotes re-anchors each one's
        fair to the house mid and resumes (the house consensus adjusts within ~45 s). A human can act sooner via set_adjust."""
        self.pause(symbols)
        for s in symbols:
            self.announce_t[s] = t

    def resume(self, symbols: list[str]) -> None:
        for s in symbols:
            self.paused.discard(s)
            self.pause_pending.discard(s)
            self.announce_t.pop(s, None)
        self.last_trade_t = -1e9

    def set_adjust(self, symbol: str, mult: float = 1.0, add: float = 0.0) -> None:
        """fair[symbol] = model fair * mult + add from now on (ETF fairs follow their baskets); resumes the symbol."""
        if not (math.isfinite(mult) and math.isfinite(add)):
            raise ValueError("adjustment must be finite")
        if mult == 1.0 and add == 0.0:
            self.adjust.pop(symbol, None)
        else:
            self.adjust[symbol] = (mult, add)
        if self.fair:
            self.fair = self.compute_fair()
        self.resume([symbol])

    def anchor(self, symbol: str, price: float) -> float | None:
        """Shift fair[symbol] so that it equals price now; the model keeps moving it from there. Returns the offset."""
        self.adjust.pop(symbol, None)
        base = self.compute_fair().get(symbol)
        if base is None or not math.isfinite(price):
            return None
        self.set_adjust(symbol, 1.0, price - base)
        return price - base

    def compute_fair(self) -> dict[str, float]:
        f = self.model.fair_analog() if self.analog else self.model.fair(self.project)
        return self.apply_adjust(f) if self.adjust else f

    def apply_adjust(self, f: dict[str, float]) -> dict[str, float]:
        f = dict(f)
        etfs = self.model.case.get("etfs", {})
        for s, (mult, add) in self.adjust.items():
            if s in f and s not in etfs:
                f[s] = f[s] * mult + add
        for etf, spec in etfs.items():
            if all(s in f for s in spec["basket"]):
                f[etf] = sum(n * f[s] for s, n in spec["basket"].items())
            if etf in self.adjust:
                mult, add = self.adjust[etf]
                f[etf] = f.get(etf, 0.0) * mult + add
        return f

    def on_news(self, sim, m: dict[str, Any]) -> None:
        if self.basket is not None:
            self.basket.on_news(sim, m)
        if self.price_signal is not None and m['type'] in ('storm', 'storm_formed'):
            if self._price_round != m['round']:
                self.price_signal.reset()
                self._price_round = m['round']
            # A reconnect's warm-up time is not the true round-open clock.
            self._price_round_start = sim.t - sim.case['timing']['pre_storm'] - m.get('age', 0)
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
        entry = self.final_edge if self.final_edge and self.model.final_exact_ready else self.min_edge
        floor = max(entry, 2.0 * sd / max(1e-9, sim.mid[s]))
        if self.rebuild_min_edge > 0 and s in ("RECON", "MAT", "GEN"):
            floor = max(floor, self.rebuild_min_edge)
        return floor

    def full_edge_for_phase(self) -> float:
        return self.final_edge_full if self.final_edge_full and self.model.final_exact_ready else self.edge_full

    def price_prediction(self, sim, symbol: str) -> float | None:
        if self.price_signal is None or self._price_round_start is None or self.model.final_exact_ready:
            return None
        return self.price_signal.predict(symbol, sim.t, sim.t - self._price_round_start)

    def price_target(self, sim, symbol: str, target: int, position: int) -> int:
        """An adverse price signal may block additions, never necessary reductions."""
        prediction = self.price_prediction(sim, symbol) if self.price_gate and target else None
        if prediction is None or prediction * (1 if target > 0 else -1) > -self.price_gate:
            return target
        if target * position <= 0:
            return 0
        return min(target, position) if target > 0 else max(target, position)

    def _same_competition(self, sim) -> bool:
        if self.competition_id == getattr(sim, 'competition_id', None):
            return True
        self.on_start(sim)
        self.on_round(sim)
        return False

    def on_quotes(self, sim) -> None:
        if not self._same_competition(sim):
            return
        if self.price_signal is not None:
            now = sim.t
            prices = sim.mid
            quote_times = getattr(sim, 'quote_times', None)
            if quote_times is not None:
                prices = {symbol: price for symbol, price in prices.items()
                          if symbol in quote_times and 0 <= now - quote_times[symbol] <= 10
                          and quote_times[symbol] > self.price_signal.symbol_received_at.get(symbol, -math.inf)}
            self.price_signal.observe(now, prices)
        if self.announce_wait > 0 and self.announce_t:
            for s in [s for s in self.paused if s in self.announce_t and sim.t - self.announce_t[s] >= self.announce_wait]:
                if s in sim.mid and s not in self.pause_pending:
                    off = self.anchor(s, sim.mid[s])
                    if off is not None:
                        self.log(f"announcement wait over: {s} fair anchored to house mid {sim.mid[s]:.2f} (offset {off:+.2f}); trading resumes", flush=True)
        # Pausing additions alone leaves old quotes executable at obsolete fair
        # values. Cancel immediately, even during warm-up; retry at most once/s.
        for s in list(self.paused):
            if (s in self.pause_pending or sim.resting(s, "buy") or sim.resting(s, "sell")) and sim.t - self.pause_cancel_t.get(s, -1e9) >= 1:
                self.pause_cancel_t[s] = sim.t
                if sim.cancel_all(s):
                    self.pause_pending.discard(s)
                    self.passive_order.pop(s, None)
                if not self._same_competition(sim):
                    return
        if not getattr(sim, "state_ready", True):
            return
        if self.basket is not None and (self.basket.targets is not None or sim.t - self.round_open_t >= self.warmup):
            active = self.basket.on_quotes(sim, self.paused)
            if not self._same_competition(sim) or active:
                return
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
        between = self.model.storm_reported and self.model.round < 3    # no storm in the air: only future-storm risk
        post = self.model.posterior
        ent = -sum(p * math.log(p) for p in post.values() if p > 0) if post else 0.0
        for s in self.symbols:
            if not self._same_competition(sim):
                return
            if s in self.paused or s not in sim.quotes or s in unsettled:
                continue
            bid, ask = sim.quotes[s]
            mid = sim.mid[s]
            f = self.fair[s]
            prediction = self.price_prediction(sim, s) if self.price_drift else None
            if prediction is not None:
                f += self.price_drift * prediction * mid
            edge = (f - mid) / mid * conf
            lim = sim.limits[s]
            if between and self.carry < 1.0:
                lim = int(round(lim * self.carry))
            floor = self.min_edge_for(sim, s)
            pos = sim.position[s]
            stopped = self.loss_limit is not None and self.cell_pnl.get((s, rnd), 0.0) < -self.loss_limit
            reduce = False
            if abs(edge) >= floor:
                frac = min(1.0, (abs(edge) - floor) / max(1e-9, self.edge_ramp, self.full_edge_for_phase() - floor))
                target = int(round(lim * frac)) * (1 if edge > 0 else -1)
                if self.ent_cut > 0 and self.model.storm_active and ent > self.ent_cut and abs(target) > abs(pos) and target * pos >= 0:
                    continue                                # pattern still ambiguous: do not add
                if self.late_cut > 0 and self.model.storm_active and self.model.last_obs is not None and self.model.last_obs["age"] > self.late_cut \
                        and abs(target) > abs(pos) and target * pos >= 0:
                    continue                                # late in the storm: do not add
                if stopped:                                 # this symbol has lost its budget this round: reduce only
                    target = 0 if target * pos <= 0 else (min(target, pos) if pos > 0 else max(target, pos))
                    if target == pos:
                        continue
            elif pos and ((pos > 0 and edge < -floor * 0.5) or (pos < 0 and edge > floor * 0.5)):
                target = 0                                  # we are now on the wrong side: get out
            elif abs(pos) > lim:
                target = lim if pos > 0 else -lim           # over the between-storm cap: reduce, paying the spread
                reduce = True
            else:
                if self.passive > 0:
                    self.quote_passive(sim, s, f, bid, ask, conf, floor, lim, pos)
                continue                                    # small edge: hold; settlement converges for free
            target = self.price_target(sim, s, target, pos)
            self.passive_order.pop(s, None)
            resting_net = sim.resting(s, "buy") - sim.resting(s, "sell")
            delta = target - pos - resting_net
            if delta == 0:
                continue
            if resting_net != 0:
                if not sim.cancel_all(s):                   # never replace an unconfirmed cancellation
                    continue
                if not self._same_competition(sim):
                    return
                pos = sim.position[s]                      # fills may have beaten the cancellation
                target = self.price_target(sim, s, target, pos)
                delta = target - pos
                if delta == 0:
                    continue
            # pay up to the price at which the remaining edge equals the floor (liquidity-aware limit)
            keep = floor / max(conf, 1e-9)
            if delta > 0:
                limit = max(ask, f / (1 + keep)) if target != 0 and not reduce else ask * (1 + self.exit_slip)
                if limit < ask and target != 0:
                    continue
                if self.max_cross > 0:
                    limit = min(limit, ask * (1 + self.max_cross))
                sim.place(s, "buy", delta, limit)
            else:
                limit = min(bid, f / (1 - keep)) if target != 0 and not reduce else bid * (1 - self.exit_slip)
                if limit > bid and target != 0:
                    continue
                if self.max_cross > 0:
                    limit = max(limit, bid * (1 - self.max_cross))
                sim.place(s, "sell", -delta, limit)


    def quote_passive(self, sim, s: str, f: float, bid: float, ask: float, conf: float, floor: float, lim: int, pos: int) -> None:
        """Rest one order inside the spread where the edge (after confidence) equals passive * floor; replace it only when
        the price moves. Fills come from the house re-quoting through us or other participants crossing."""
        competition_id = getattr(sim, 'competition_id', None)
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
                if sim.cancel_all(s):
                    self.passive_order.pop(s, None)
            return
        px = round(px, 2)
        edge_at = abs(f - px) / px * conf
        frac = min(1.0, (edge_at - self.passive * floor) / max(1e-9, self.edge_ramp, self.full_edge_for_phase() - self.passive * floor))
        target = int(round(lim * frac)) * (1 if side == "buy" else -1)
        target = self.price_target(sim, s, target, pos)
        qty = (target - pos) if side == "buy" else (pos - target)
        if qty <= 0:
            if s in self.passive_order or (self.price_gate and (sim.resting(s, 'buy') or sim.resting(s, 'sell'))):
                if sim.cancel_all(s):
                    self.passive_order.pop(s, None)
            return
        old = self.passive_order.get(s)
        if (old and sim.resting(s, side) and old[0] == side
                and (not self.price_gate or sim.resting(s, side) <= qty)
                and abs(old[1] - px) / px < 0.001 and sim.t - old[2] < 120):
            return                                    # our quote is still where we want it
        if sim.resting(s, "buy") or sim.resting(s, "sell"):
            if not sim.cancel_all(s):
                return
            if competition_id != getattr(sim, 'competition_id', None):
                return
            pos = sim.position[s]
            target = self.price_target(sim, s, target, pos)
            qty = (target - pos) if side == "buy" else (pos - target)
            if qty <= 0:
                self.passive_order.pop(s, None)
                return
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
