"""Causal short-horizon public-price signal."""
from bisect import bisect_right
from collections import deque
import json
import math
from pathlib import Path


class PriceSignal:
    def __init__(self, path=None):
        data = json.loads(Path(path or Path(__file__).with_suffix('.json')).read_text())
        self.lags = data['lags']
        self.coefficients = data['coefficients']
        self.phase_boundary = data['phase_boundary']
        self.active_interval = data['active_interval']
        if (data['version'] != 1 or not self.lags
                or any(isinstance(lag, bool) or lag <= 0 or not math.isfinite(lag) for lag in self.lags)):
            raise ValueError('invalid price signal metadata')
        for phases in self.coefficients.values():
            for phase in ('storm', 'aftermath'):
                coefficients = phases[phase]
                if len(coefficients) != len(self.lags) + 1 or not all(map(math.isfinite, coefficients)):
                    raise ValueError('invalid price signal coefficients')
        self.reset()

    def reset(self):
        self.history = {symbol: deque() for symbol in self.coefficients}
        self.symbol_received_at = {}
        self.received_at = None

    def observe(self, t, prices):
        if not math.isfinite(t):
            self.reset()
            return
        if self.received_at is not None and (t < self.received_at or t - self.received_at > 10):
            self.reset()
        self.received_at = t
        for symbol, price in prices.items():
            if symbol not in self.history:
                continue
            history = self.history[symbol]
            last = self.symbol_received_at.get(symbol)
            if last is not None and t - last > 10:
                history.clear()
            self.symbol_received_at[symbol] = t
            if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
                history.clear()
                continue
            if not history or history[-1][1] != price:
                history.append((t, price))
            # Retain a predecessor and a 10s margin for asynchronous quote frames.
            while len(history) > 1 and history[1][0] <= t - max(self.lags) - 10:
                history.popleft()

    def predict(self, symbol, t, elapsed):
        if (symbol not in self.history or not math.isfinite(t) or not math.isfinite(elapsed)
                or not self.active_interval[0] <= elapsed <= self.active_interval[1]
                or symbol not in self.symbol_received_at
                or t - self.symbol_received_at[symbol] > 10):
            return None
        points = list(self.history[symbol])
        if not points or points[0][0] > t - max(self.lags):
            return None
        current_index = bisect_right(points, t, key=lambda point: point[0]) - 1
        if current_index < 0:
            return None
        current = points[current_index][1]
        features = [1.0]
        for lag in self.lags:
            index = bisect_right(points, t - lag, key=lambda point: point[0]) - 1
            if index < 0:
                return None
            features.append((current - points[index][1]) / current)
        phase = 'storm' if elapsed < self.phase_boundary else 'aftermath'
        result = sum(x * w for x, w in zip(features, self.coefficients[symbol][phase]))
        return result if math.isfinite(result) else None
