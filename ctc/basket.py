"""Small, coordinated ETF basket overlay."""
import math


class BasketOverlay:
    def __init__(self, edge, lot=10):
        if not math.isfinite(edge) or edge < 0 or not isinstance(lot, int) or lot <= 0:
            raise ValueError('basket edge must be finite/nonnegative and lot a positive integer')
        self.edge, self.lot = edge, lot
        self.targets = None
        self.round_start = None
        self.last_attempt = self.last_submit = self.last_cancel = -math.inf
        self.submitted = False
        self.cycles = self.timeouts = 0

    def on_round(self, sim):
        # Resting orders disappear at a round close, but partial inventory remains.
        self.round_start = None

    def on_news(self, sim, message):
        if message['type'] in ('storm', 'storm_formed'):
            self.round_start = sim.t - sim.case['timing']['pre_storm'] - message.get('age', 0)

    @staticmethod
    def _ready(sim):
        return sim.market_open and getattr(sim, 'state_ready', True)

    @staticmethod
    def _headroom(sim, actions):
        used = sum(t >= sim.t - 60 for t in sim.actions)
        return used + actions <= sim.rate_limit

    @staticmethod
    def _fresh(sim, symbols):
        times = getattr(sim, 'quote_times', None)
        now = sim.t
        for symbol in symbols:
            quote = sim.quotes.get(symbol)
            if (quote is None or not all(math.isfinite(p) and p > 0 for p in quote)
                    or quote[0] > quote[1]):
                return False
            if times is not None and (symbol not in times or not 0 <= now - times[symbol] <= 5):
                return False
        return True

    @staticmethod
    def _resting(sim, symbol):
        return sim.resting(symbol, 'buy') + sim.resting(symbol, 'sell')

    def _cancel(self, sim, symbols):
        for symbol in symbols:
            if self._resting(sim, symbol) and not sim.cancel_all(symbol):
                return False
            if not self._ready(sim):
                return False
        return not any(self._resting(sim, s) for s in symbols)

    def _drive(self, sim, paused):
        symbols = list(self.targets)
        if not self._ready(sim):
            return True
        if set(symbols) & set(paused):
            if sim.t - self.last_cancel >= 1 and self._headroom(sim, len(symbols)):
                self.last_cancel = sim.t
                self._cancel(sim, symbols)
            return True
        if (all(sim.position[s] == target for s, target in self.targets.items())
                and not any(self._resting(sim, s) for s in symbols)):
            self.targets = None
            return False
        if self.submitted and sim.t - self.last_submit < 10:
            return True
        if not self._fresh(sim, symbols) or not self._headroom(sim, 2 * len(symbols)):
            return True
        if not self._cancel(sim, symbols):
            return True
        crossing = .02 if self.submitted else .001
        if self.submitted:
            self.timeouts += 1
        self.last_submit = sim.t
        self.submitted = True
        for symbol, target in self.targets.items():
            if not self._ready(sim):
                break
            delta = target - sim.position[symbol]
            if not delta:
                continue
            side = 'buy' if delta > 0 else 'sell'
            limit = sim.quotes[symbol][1] * (1 + crossing) if delta > 0 else sim.quotes[symbol][0] * (1 - crossing)
            sim.place(symbol, side, abs(delta), limit)
        return True

    def _size(self, sim, changes):
        size = self.lot
        for symbol, delta in changes.items():
            sign = 1 if delta > 0 else -1
            side = 'buy' if delta > 0 else 'sell'
            room = sim.limits[symbol] - sign * sim.position[symbol] - sim.resting(symbol, side)
            size = min(size, max(0, int(room // abs(delta))))
        return size

    def _opportunity(self, sim, etf, basket):
        nav = sum(sum(sim.quotes[s]) * .5 * n for s, n in basket.items())
        cheap = sum(sim.quotes[s][0] * n for s, n in basket.items()) - sim.quotes[etf][1]
        rich = sim.quotes[etf][0] - sum(sim.quotes[s][1] * n for s, n in basket.items())
        return (rich > cheap) if max(cheap, rich) >= self.edge * nav else None

    def on_quotes(self, sim, paused=()):
        if self.targets is not None:
            return self._drive(sim, paused)
        if (not self.edge or not self._ready(sim) or self.round_start is None
                or not 20 <= sim.t - self.round_start <= 740 or sim.t - self.last_attempt < 15):
            return False
        for etf, meta in sim.case['etfs'].items():
            basket = meta['basket']
            symbols = [etf, *basket]
            if (set(symbols) & set(paused) or not self._fresh(sim, symbols)
                    or not self._headroom(sim, 4 * len(symbols) + 1)):
                continue
            create = self._opportunity(sim, etf, basket)
            if create is None:
                continue
            sign = 1 if create else -1
            changes = {etf: sign, **{s: -sign * n for s, n in basket.items()}}
            if not self._size(sim, changes):
                continue
            self.last_attempt = sim.t
            if not self._cancel(sim, symbols):
                return False
            # Cancellations may race fills and perform blocking account refreshes.
            size = self._size(sim, changes)
            if not size or not self._fresh(sim, symbols) or self._opportunity(sim, etf, basket) != create:
                return False
            self.targets = {s: sim.position[s] for s in symbols}
            self.submitted = False
            self.cycles += 1
            (sim.create if create else sim.redeem)(etf, size)
            if not getattr(sim, 'state_ready', True) and hasattr(sim, 'refresh'):
                sim.refresh()
            return self._drive(sim, paused)
        return False
