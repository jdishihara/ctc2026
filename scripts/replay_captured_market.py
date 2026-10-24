"""Offline diagnostic using a completed season's recorded live quotes and news.

Virtual fills consume displayed top-of-book size, require a crossing price, and
wait for configurable order latency. This cannot recreate queue priority, market
impact, HTTP serialization, cancellation races, or the response to our orders.
It never connects to the exchange and never reads historical season outcomes.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import copy
import io
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot.live import LiveSession
from ctc.sim import Sim
from ctc.strategies import FairValueTrader


class ReplayExchange(Sim):
    """Reuse virtual order accounting; initialize without any historical files."""
    def __init__(self, case, fraction=.1, latency=.25, depth_scale=1):
        if not (0 < fraction <= 1 and math.isfinite(latency) and latency >= 0
                and 0 < depth_scale <= 1):
            raise ValueError('invalid replay bounds')
        self.case = copy.deepcopy(case)
        self.limits = {s: max(1, math.floor(n * fraction)) for s, n in case['limits'].items()}
        self.symbols = list(self.limits)
        self.latency, self.depth_scale = latency, depth_scale
        self.rate_limit, self.verbose, self.ladder, self.depth = 90, False, None, None
        self.t, self.round = 0., 0
        self.position = {s: 0 for s in self.symbols}
        self.cash, self.cash_by = 0., {s: 0. for s in self.symbols}
        self.quotes, self.mid, self.quote_times, self.last_mid, self.available = {}, {}, {}, {}, {}
        self.quotes_valid_after = -math.inf
        self.orders, self.pending, self.fills = {}, [], []
        self.actions, self.rejected, self.next_id = collections.deque(), 0, 1
        self.market_open, self.state_ready, self.reopened = False, True, False
        self.competition_id, self.season_year = 'offline-replay', ''
        self.submission_guard = None
        self.conversions = 0
        self.unusable_quotes = 0

    @property
    def open_orders(self):
        return [{'order_id': o.id, 'symbol': o.symbol, 'side': o.side,
                 'quantity': o.qty, 'filled_quantity': o.filled, 'price': o.price}
                for o in (*self.orders.values(), *self.pending)]

    @property
    def pnl_now(self):
        return self.pnl()

    def pnl(self):
        return self.cash + sum(q * self.last_mid.get(s, 0) for s, q in self.position.items())

    def pnl_by_symbol(self):
        return {s: self.cash_by[s] + q * self.last_mid.get(s, 0) for s, q in self.position.items()}

    def refresh(self):
        # Account state is local virtual accounting. No REST request is made.
        self.state_ready = True

    def place(self, symbol, side, qty, price=None):
        if not self.state_ready or (self.submission_guard and not self.submission_guard((symbol,))):
            return None
        return super().place(symbol, side, qty, price)

    def _etf(self, etf, qty, sign):
        symbols = (etf, *self.case['etfs'][etf]['basket'])
        if not self.state_ready or (self.submission_guard and not self.submission_guard(symbols)):
            return False
        accepted = super()._etf(etf, qty, sign)
        self.conversions += int(accepted)
        return accepted

    def liquidity(self, symbol, side, limit):
        if symbol not in self.quotes or not 0 <= self.t - self.quote_times.get(symbol, -math.inf) <= 5:
            return 0
        touch = self.quotes[symbol][1 if side == 'buy' else 0]
        if (side == 'buy' and touch > limit) or (side == 'sell' and touch < limit):
            return 0
        return self.available.get((symbol, side), 0)

    def _try_match(self, order, passive):
        if not self.market_open or order.symbol not in self.quotes:
            return
        touch = self.quotes[order.symbol][1 if order.side == 'buy' else 0]
        limit = order.price if order.price is not None else touch
        qty = min(order.qty - order.filled, self.liquidity(order.symbol, order.side, limit))
        if qty:
            price = order.price if passive and order.price is not None else touch
            self._fill(order, qty, price, passive)
            self.available[(order.symbol, order.side)] -= qty

    def advance(self, timestamp, match=True):
        """Process due orders on their own clock; match controls only the boundary.

        Incoming market data wins ties at the same timestamp when match=False.
        Older activations always occur before that new information is available.
        """
        if timestamp < self.t:
            raise ValueError('recorded time moved backwards')
        while self.pending:
            due = min(order.exec_t for order in self.pending)
            if due > timestamp or (due == timestamp and not match):
                break
            self.t = due
            self._activate_pending()
        self.t = timestamp

    def update_quote(self, frame):
        symbol = frame.get('symbol')
        if symbol not in self.limits:
            return
        bid, ask, bs, az = (frame.get(k) for k in ('bid', 'ask', 'bid_size', 'ask_size'))
        if (not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
                    for x in (bid, ask, bs, az)) or not 0 < bid <= ask or min(bs, az) < 0):
            self.unusable_quotes += 1
            self.quotes.pop(symbol, None)
            self.mid.pop(symbol, None)
            self.quote_times.pop(symbol, None)
            self.available[(symbol, 'buy')] = self.available[(symbol, 'sell')] = 0
            return
        if not self.market_open:
            self.market_open = self.reopened = True
        self.quotes[symbol] = bid, ask
        self.mid[symbol] = self.last_mid[symbol] = (bid + ask) / 2
        self.quote_times[symbol] = self.t
        self.available[(symbol, 'buy')] = math.floor(az * self.depth_scale)
        self.available[(symbol, 'sell')] = math.floor(bs * self.depth_scale)
        for oid, order in list(self.orders.items()):
            if order.symbol == symbol:
                self._try_match(order, passive=True)
                if order.filled == order.qty:
                    del self.orders[oid]

    def close_market(self):
        self.market_open = False
        self.orders.clear()
        self.pending.clear()
        self.quotes.clear()
        self.mid.clear()
        self.quote_times.clear()
        self.available.clear()
        self.quotes_valid_after = self.t


class ReplaySession(LiveSession):
    def __init__(self, *args, reset_each_snapshot=False, **kwargs):
        self.reset_each_snapshot = reset_each_snapshot
        super().__init__(*args, **kwargs)

    def _news(self, message):
        super()._news(message)
        if self.reset_each_snapshot and message.get('type') == 'snapshot':
            # Controlled ablation of the old warm-up reset, not a full old-runtime replay.
            self.strat.last_trade_t = -1e9
            self.strat.on_round(self.ex)


def completed_capture(batch, feed, cid, symbols):
    status = json.loads((Path(batch) / 'status.json').read_text())
    trial = status.get('trials', {}).get(cid, {})
    if not trial.get('completed') or trial.get('invalid'):
        raise ValueError('a completed, uncontaminated trial is required')
    receipt = next((row for line in (Path(batch) / 'actions.jsonl').open()
                    if (row := json.loads(line)).get('kind') == 'settlement'
                    and row.get('competition_id') == cid), None)
    if (receipt is None or receipt.get('clock', {}).get('competition_id') != cid
            or receipt.get('clock', {}).get('state') == 'running'
            or not str(receipt.get('clock', {}).get('fictional_time', '')).startswith(trial['year'] + '-')):
        raise ValueError('matching closed settlement receipt required')
    prices = receipt.get('prices', {})
    if set(prices) != set(symbols) or not all(isinstance(p, (int, float)) and math.isfinite(p) and p > 0
                                           for p in prices.values()):
        raise ValueError('complete finite official settlement prices required')
    frames, active, sequences = [], False, set()
    for line in Path(feed).open():
        frame = json.loads(line)
        timestamp = frame.get('received_at')
        if timestamp is None or timestamp < trial['started_at'] - 120:
            continue
        if timestamp > trial['completed_at']:
            break
        if frame.get('type') == 'news':
            message = frame.get('message', {})
            active = str(message.get('time', '')).startswith(trial['year'] + '-')
            if active and 'seq' in message:
                sequences.add(message['seq'])
        if active and frame.get('type') in ('quote', 'news', 'disconnected'):
            frames.append(frame)
    if not sequences or sequences != set(range(max(sequences) + 1)):
        raise ValueError('captured news must contain the full contiguous sequence from zero')
    return status, trial, receipt, frames, len(sequences)


def replay(case, frames, year, settlement, fraction, latency, depth_scale, basket, reset_each_snapshot):
    ex = ReplayExchange(case, fraction, latency, depth_scale)
    ex.season_year = year
    strat = FairValueTrader(analog=True, min_edge=.025, edge_full=.03, sd_mult=.7,
        sigma=15, k=100, passive=.75, warmup=20, max_cross=.02, carry=.5, ent_cut=1.2,
        cone_w=1, cone_s0=20, cone_nu=0, isl_w=0, final_exact=True, final_edge=.005,
        final_edge_full=.005, basket_edge=.01 if basket else 0,
        basket_participation=.5, announce_wait=60)
    strat.on_start(ex)
    session = ReplaySession(ex, strat, sync=3, season_year=year,
                            reset_each_snapshot=reset_each_snapshot)
    start, previous_round, trough = frames[0]['received_at'], 0, 0.
    with contextlib.redirect_stdout(io.StringIO()):
        for frame in frames:
            ex.advance(frame['received_at'] - start, match=False)
            if frame['type'] == 'news':
                message = frame['message']
                rnd = message.get('round', previous_round)
                if rnd != previous_round or message.get('phase') == 'closed':
                    ex.close_market()
                previous_round = rnd
            elif frame['type'] == 'quote':
                ex.update_quote(frame)
            ex._activate_pending()
            session.step([(frame, ex.t)])
            trough = min(trough, ex.pnl())
    if session.history_block_reason() or len(strat.model.reported_rounds) != 3:
        raise ValueError('replay ended without complete three-round model history')
    ex.close_market()
    pnl = ex.cash + sum(q * settlement[s] for s, q in ex.position.items())
    return {'latency_seconds': latency, 'displayed_depth_fraction': depth_scale,
            'basket_enabled': basket, 'reset_warmup_each_snapshot': reset_each_snapshot,
            'simulated_settlement_pnl': pnl, 'fills': len(ex.fills),
            'orders': ex.next_id - 1, 'conversions': ex.conversions,
            'basket_cycles': strat.basket.cycles if strat.basket else 0,
            'lowest_marked_pnl': trough, 'rate_rejections': ex.rejected,
            'unusable_quotes': ex.unusable_quotes,
            'final_positions': ex.position}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--feed', type=Path, required=True)
    parser.add_argument('--competition-id', required=True)
    parser.add_argument('--latencies', default='.25,1,3')
    parser.add_argument('--depth-scale', type=float, default=1)
    args = parser.parse_args()
    case = json.loads((ROOT / 'data/case.json').read_text())
    status, trial, receipt, frames, news_count = completed_capture(
        args.batch, args.feed, args.competition_id, case['limits'])
    results = [replay(case, frames, trial['year'], receipt['prices'], status['fraction'],
                      latency, args.depth_scale, basket, reset)
               for latency in map(float, args.latencies.split(','))
               for basket in (False, True) for reset in (True, False)]
    print(json.dumps({'competition_id': args.competition_id, 'year': trial['year'],
        'live_settlement_pnl': receipt['pnl'], 'news_count': news_count,
        'quote_count': sum(f['type'] == 'quote' for f in frames), 'results': results,
        'limitations': ['Virtual fills are not actual or guaranteed counterfactual profits.',
            'Each recorded quote replenishes modeled displayed top-of-book size; own market impact is omitted.',
            'Orders share configurable latency; HTTP serialization and cancellation races are omitted.',
            'Resting orders fill only when recorded quotes cross their limit, at the resting limit price.',
            'Conversions are immediate and cash neutral; fees outside recorded prices are omitted.',
            'Market closes are inferred from closed news snapshots; round changes cancel virtual orders.',
            'The warm-up ablation changes snapshot resets only, not the entire earlier runtime.',
            'A completed previously observed season is diagnostic data, not an untouched holdout.']}, indent=2))


if __name__ == '__main__':
    main()
