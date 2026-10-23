"""Offline-only basket execution probe; not a live strategy or PnL promise."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ctc.ladder import Ladder
from ctc.sim import Sim


class BasketProbe:
    def on_start(self, sim):
        self.started = None
        self.last_attempt = -1e9
        self.cycles = 0
        self.timeouts = 0

    def on_round(self, sim):
        self.opened = sim.t

    def on_news(self, sim, message):
        pass

    def on_end(self, sim):
        pass

    def on_quotes(self, sim):
        if self.started is not None:
            if any(sim.position.values()) or sim.pending or sim.orders:
                if sim.t - self.started >= 10:
                    sim.cancel_all()
                    for symbol, quantity in sim.position.items():
                        if quantity:
                            sim.place(symbol, 'sell' if quantity > 0 else 'buy', abs(quantity))
                    self.timeouts += 1
                    self.started = sim.t
                return
            self.started = None
        if sim.t - self.opened < 20 or sim.t - self.opened > 750 or sim.t - self.last_attempt < 15:
            return
        for etf, meta in sim.case['etfs'].items():
            basket = meta['basket']
            nav = sum(sim.mid[s] * n for s, n in basket.items())
            cheap = sum(sim.quotes[s][0] * n for s, n in basket.items()) - sim.quotes[etf][1]
            rich = sim.quotes[etf][0] - sum(sim.quotes[s][1] * n for s, n in basket.items())
            if max(cheap, rich) < .005 * nav:
                continue
            create = rich > cheap
            legs = [(etf, 'sell' if create else 'buy', 1)] + [
                (s, 'buy' if create else 'sell', n) for s, n in basket.items()]
            size = min([10] + [int(sim.ladder.table[s]['bid' if side == 'sell' else 'ask'][0]
                                   * sim.ladder.scale / n) for s, side, n in legs])
            if size <= 0:
                continue
            self.last_attempt = sim.t
            if not (sim.create(etf, size) if create else sim.redeem(etf, size)):
                continue
            self.cycles += 1
            self.started = sim.t
            for symbol, side, n in legs:
                limit = sim.quotes[symbol][0] * .999 if side == 'sell' else sim.quotes[symbol][1] * 1.001
                sim.place(symbol, side, size * n, limit)
            return


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    case = json.loads((ROOT / 'data/case.json').read_text())
    seasons = json.loads((ROOT / 'data/history/manifest.json').read_text())['seasons']
    for name, refill, scale, latency in [('deep', 10, 1, .25), ('severe_delay', 60, .25, 3)]:
        rows = []
        for n in range(301, 451):
            sim = Sim(ROOT / 'data/history' / seasons[n - 1]['dir'], case,
                      rate_limit=120, latency=latency, ladder=Ladder(refill_secs=refill, scale=scale))
            strategy = BasketProbe()
            pnl = sim.run(strategy)
            rows.append(dict(season=n, pnl=pnl, cycles=strategy.cycles, timeouts=strategy.timeouts,
                             fills=len(sim.fills), rejected=sim.rejected))
        p = np.array([r['pnl'] for r in rows])
        summary = dict(mean=float(p.mean()), p10=float(np.percentile(p, 10)),
                       minimum=float(p.min()), losing=int((p < 0).sum()),
                       cycles=float(np.mean([r['cycles'] for r in rows])),
                       timeouts=sum(r['timeouts'] for r in rows), rejected=sum(r['rejected'] for r in rows))
        (a.out / f'{name}.json').write_text(json.dumps(dict(seasons=[301,450], summary=summary, rows=rows), indent=2) + '\n')
        print(json.dumps(dict(regime=name, **summary)), flush=True)


if __name__ == '__main__':
    main()
