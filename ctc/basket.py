"""Small, coordinated ETF basket overlay."""
import math


class BasketOverlay:
    def __init__(self, edge, lot=10, participation=0):
        if not math.isfinite(edge) or edge < 0 or not isinstance(lot, int) or lot <= 0:
            raise ValueError('basket edge must be finite/nonnegative and lot a positive integer')
        if not 0 <= participation <= 1:
            raise ValueError('basket participation must be between zero and one')
        self.edge, self.lot = edge, lot
        self.participation = participation
        self.targets = None
        self.competition_id = None
        self.round_start = None
        self.last_attempt = self.last_submit = self.last_cancel = -math.inf
        self.leg_submit = {}
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

    def _same_competition(self, sim, competition_id):
        if getattr(sim, 'competition_id', None) == competition_id:
            return True
        # A refreshed account can roll over inside any blocking operation.
        # Inventory from the settled season must never become next season's target.
        self.targets = None
        self.round_start = None
        self.submitted = False
        self.last_attempt = self.last_submit = self.last_cancel = -math.inf
        self.leg_submit.clear()
        self.competition_id = getattr(sim, 'competition_id', None)
        return False

    def _cancel(self, sim, symbols, competition_id):
        for symbol in symbols:
            if not self._same_competition(sim, competition_id) or not self._ready(sim):
                return False
            cancelled = not self._resting(sim, symbol) or sim.cancel_all(symbol)
            if not self._same_competition(sim, competition_id) or not self._ready(sim):
                return False
            if not cancelled:
                return False
        return not any(self._resting(sim, s) for s in symbols)

    def _complete(self, sim):
        if (all(sim.position[s] == target for s, target in self.targets.items())
                and not any(self._resting(sim, s) for s in self.targets)):
            self.targets = None
            self.leg_submit.clear()
            return True
        return False

    def _drive(self, sim, paused):
        competition_id = self.competition_id
        if not self._same_competition(sim, competition_id):
            return False
        symbols = list(self.targets)
        if not self._ready(sim):
            return True
        if self._complete(sim):
            return False
        if set(symbols) & set(paused):
            if sim.t - self.last_cancel >= 1 and self._headroom(sim, len(symbols)):
                self.last_cancel = sim.t
                if not self._cancel(sim, symbols, competition_id):
                    return self.targets is not None
                if self._complete(sim):
                    return False
            return True
        # Cancellation needs no quote. Remove expired legs even during a feed
        # outage or when the remaining action budget cannot also replace them.
        expired = [s for s in symbols if self._resting(sim, s)
                   and sim.t - self.leg_submit.get(s, -math.inf) >= 10]
        if expired:
            if sim.t - self.last_cancel < 1 or not self._headroom(sim, len(expired)):
                return True
            self.last_cancel = sim.t
            if not self._cancel(sim, expired, competition_id):
                return self.targets is not None
            if self._complete(sim):
                return False
        # A stale quote or pending news can interrupt a submission batch after
        # one leg. Unsent legs must not inherit that leg's retry delay.
        due = [s for s in symbols if not self._resting(sim, s)
               and sim.t - self.leg_submit.get(s, -math.inf) >= 10]
        if not due or not self._fresh(sim, symbols) or not self._headroom(sim, len(due)):
            return True
        counted_retry = False
        for symbol in due:
            if not self._same_competition(sim, competition_id):
                return False
            if not self._ready(sim) or not self._fresh(sim, symbols):
                break
            delta = self.targets[symbol] - sim.position[symbol]
            if not delta:
                continue
            retry = symbol in self.leg_submit
            crossing = .02 if retry else .001
            side = 'buy' if delta > 0 else 'sell'
            limit = self._limit(sim, symbol, side, crossing)
            submitted_at = sim.t
            order = sim.place(symbol, side, abs(delta), limit)
            if not self._same_competition(sim, competition_id):
                return False
            if order is not None or not getattr(sim, 'state_ready', True):
                # An uncertain acknowledgement must also await reconciliation.
                self.leg_submit[symbol] = self.last_submit = submitted_at
                self.submitted = True
                if retry and not counted_retry:
                    self.timeouts += 1
                    counted_retry = True
            if order is None:
                break
        return self._same_competition(sim, competition_id)

    @staticmethod
    def _limit(sim, symbol, side, crossing):
        price = sim.quotes[symbol][1] * (1 + crossing) if side == 'buy' else sim.quotes[symbol][0] * (1 - crossing)
        ticks = math.floor(price * 100 + 1e-9) if side == 'buy' else math.ceil(price * 100 - 1e-9)
        return round(ticks / 100, 2)

    def _execution_size(self, sim, changes, size, competition_id):
        if not self.participation:
            return size
        for symbol, delta in changes.items():
            if (not self._same_competition(sim, competition_id)
                    or not self._ready(sim) or not self._fresh(sim, changes)):
                return 0
            side = 'sell' if delta > 0 else 'buy'  # Closing the converted inventory.
            quantity = sim.liquidity(symbol, side, self._limit(sim, symbol, side, .001))
            if not self._same_competition(sim, competition_id) or not self._ready(sim):
                return 0
            if quantity is None or not math.isfinite(quantity) or quantity < 0:
                return 0
            size = min(size, int(quantity * self.participation // abs(delta)))
        return size

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
            competition_id = getattr(sim, 'competition_id', None)
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
            if not self._cancel(sim, symbols, competition_id):
                self._same_competition(sim, competition_id)
                return False
            if not self._fresh(sim, symbols):
                return False
            # Cancellations may race fills and perform blocking account refreshes.
            size = self._size(sim, changes)
            size = self._execution_size(sim, changes, size, competition_id)
            if (not self._same_competition(sim, competition_id) or not self._ready(sim)
                    or not size or not self._fresh(sim, symbols)
                    or self._opportunity(sim, etf, basket) != create):
                return False
            self.targets = {s: sim.position[s] for s in symbols}
            self.competition_id = competition_id
            self.submitted = False
            self.leg_submit.clear()
            self.cycles += 1
            (sim.create if create else sim.redeem)(etf, size)
            if not getattr(sim, 'state_ready', True) and hasattr(sim, 'refresh'):
                sim.refresh()
            return self._drive(sim, paused)
        return False
