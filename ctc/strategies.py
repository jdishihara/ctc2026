"""Strategies for the offline simulator and (later) the live bot. Each keeps a SeasonModel and trades fair vs quotes."""
from __future__ import annotations
from typing import Any
from .valuation import SeasonModel, SYMS


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

    def __init__(self, min_edge: float = 0.01, edge_full: float = 0.05, rebalance_every: float = 6.0,
                 symbols: list[str] | None = None, project: bool = True):
        self.min_edge, self.edge_full, self.every = min_edge, edge_full, rebalance_every
        self.symbols = symbols or SYMS
        self.project = project

    def on_start(self, sim) -> None:
        self.model = SeasonModel(sim.case)
        self.last_trade_t = -1e9
        self.fair: dict[str, float] = {}

    def on_news(self, sim, m: dict[str, Any]) -> None:
        self.model.on_message(m)
        if m["type"] in ("damage_report", "advisory", "storm_formed", "storm_dissipated"):
            self.fair = self.model.fair(self.project)
            self.last_trade_t = -1e9   # react immediately

    def confidence(self, sim) -> float:
        """How much of the fair-mid gap to believe. 1 after the final report; decays with storm uncertainty before."""
        md = self.model
        if md.round == 0:
            return 0.0
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
        return max(self.min_edge, 2.0 * sd / max(1e-9, sim.mid[s]))

    def on_quotes(self, sim) -> None:
        if sim.t - self.last_trade_t < self.every:
            return
        self.last_trade_t = sim.t
        if self.model.storm_active:
            self.fair = self.model.fair(self.project)
        if not self.fair:
            return
        conf = self.confidence(sim)
        if conf <= 0:
            return                      # no view: hold whatever we have
        for s in self.symbols:
            bid, ask = sim.quotes[s]
            mid = sim.mid[s]
            f = self.fair[s]
            edge = (f - mid) / mid * conf
            lim = sim.limits[s]
            floor = self.min_edge_for(sim, s)
            if abs(edge) >= floor:
                frac = min(1.0, (abs(edge) - floor) / max(1e-9, self.edge_full - floor))
                target = int(round(lim * frac)) * (1 if edge > 0 else -1)
            elif abs(edge) < floor * 0.5:
                target = 0              # fair has converged to the market: take profit
            else:
                continue                # in between: hold
            delta = target - sim.position[s]
            if delta == 0:
                continue
            if target == 0 or (delta > 0 and f > ask) or (delta < 0 and f < bid):
                sim.place(s, "buy" if delta > 0 else "sell", abs(delta), ask if delta > 0 else bid)


class FinalReportOnly(FairValueTrader):
    """Only trades after the round-3 final damage report, when settlement is known exactly: validates the pipeline
    and measures the end-of-round tactic on its own."""

    def confidence(self, sim) -> float:
        md = self.model
        return 1.0 if (md.storm_reported and md.round == 3) else 0.0
