"""Offline REST timing diagnostic using the production client and a virtual server.

No network fallback or key access. Settlement is deliberately absent from the
server interface. See docs/serialized-replay-plan.md for the fixed assumptions.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot.live import LiveExchange, LiveSession, MarketInbox
from ctc.strategies import FairValueTrader
from scripts.evaluate_observed_season import observed_capture
from scripts.experiment_execution_costs import PARAMETERS
from scripts.replay_captured_market import ReplayExchange, completed_capture


class ReplayServer:
    """Single-threaded server clock; advancing time never runs client strategy."""
    def __init__(self, case, frames, year, competition_id, *, fraction=.1,
                 depth_scale=1, rtt=.25, end_at=None):
        if not math.isfinite(rtt) or rtt < 0 or not frames:
            raise ValueError('finite nonnegative RTT and nonempty frames required')
        if end_at is not None and (not math.isfinite(end_at) or end_at < 0):
            raise ValueError('finite nonnegative terminal time required')
        self.market = ReplayExchange(case, fraction, latency=0, depth_scale=depth_scale)
        self.frames = copy.deepcopy(frames)
        self.start = frames[0]['received_at']
        self.times = [f['received_at'] - self.start for f in frames]
        if any(not math.isfinite(t) for t in self.times) or self.times != sorted(self.times):
            raise ValueError('frames must have finite chronological arrival times')
        self.year, self.competition_id = str(year), competition_id
        self.fictional_time = f'{year}-01-01T00:00:00'
        self.rtt, self.end_at = rtt, end_at
        self.index, self.round, self.phase = 0, 0, None
        self.terminal = False
        self.inbox = MarketInbox()
        self.requests, self.fatal_errors = [], []
        self.ignored_closed_quotes = 0
        self.lowest_mark, self.peak_mark, self.max_drawdown = 0., 0., 0.

    @property
    def now(self):
        return self.market.t

    def mark(self):
        value = self.market.pnl()
        self.lowest_mark = min(self.lowest_mark, value)
        self.peak_mark = max(self.peak_mark, value)
        self.max_drawdown = max(self.max_drawdown, self.peak_mark - value)

    def _close_terminal(self):
        self.terminal = True
        self.market.close_market()

    def _frame(self, frame, at, closed_boundary=False):
        kind = frame.get('type')
        if kind == 'news':
            message = frame.get('message', {})
            self.fictional_time = message.get('time', self.fictional_time)
            rnd = message.get('round', self.round)
            if rnd != self.round:
                self.market.close_market()
                self.round, self.phase = rnd, None
            phase = message.get('phase')
            if phase is not None:
                self.phase = phase
                if phase == 'closed':
                    self.market.close_market()
            self.market.round = self.round
        elif kind == 'quote':
            if self.terminal or closed_boundary or self.phase == 'closed':
                self.ignored_closed_quotes += 1
            else:
                self.market.update_quote(frame)
        self.inbox.put(copy.deepcopy(frame), at)
        self.mark()

    def advance(self, timestamp):
        if not math.isfinite(timestamp) or timestamp < self.now:
            raise ValueError('virtual clock must be finite and monotone')
        while self.index < len(self.frames) and self.times[self.index] <= timestamp:
            at = self.times[self.index]
            if not self.terminal and self.end_at is not None and self.end_at <= at:
                self.market.advance(self.end_at, match=False)
                self._close_terminal()
            self.market.advance(at, match=False)
            end = self.index + 1
            while end < len(self.frames) and self.times[end] == at:
                end += 1
            closed_boundary = any(f.get('type') == 'news' and f.get('message', {}).get('phase') == 'closed'
                                  for f in self.frames[self.index:end])
            if closed_boundary:
                self.market.close_market()
            for frame in self.frames[self.index:end]:
                self._frame(frame, at, closed_boundary)
            self.index = end
        if not self.terminal and self.end_at is not None and self.end_at <= timestamp:
            self.market.advance(self.end_at, match=False)
            self._close_terminal()
        self.market.advance(timestamp)

    def request(self, method, path, body=None):
        started = self.now
        self.advance(started + self.rtt / 2)
        row = {'method': method, 'path': path, 'body': copy.deepcopy(body),
               'started_at': started, 'executed_at': self.now}
        try:
            response = copy.deepcopy(self._operation(method, path, body))
        except Exception as exc:
            row['error'] = str(exc)
            self.fatal_errors.append(f'{type(exc).__name__}: {exc}')
            self.advance(started + self.rtt)
            row['completed_at'] = self.now
            self.requests.append(row)
            raise
        row['response'] = copy.deepcopy(response)
        self.mark()
        self.advance(started + self.rtt)
        row['completed_at'] = self.now
        self.requests.append(row)
        return response

    def _operation(self, method, path, body):
        market = self.market
        parsed = urlsplit(path)
        endpoint = parsed.path
        if method == 'GET':
            if endpoint == '/cases/hurricane.json':
                case = copy.deepcopy(market.case)
                case['limits'] = market.limits.copy()
                return case
            if endpoint == '/competitions/time':
                return {'competition_id': self.competition_id,
                        'state': 'running' if market.market_open and not self.terminal else 'ready',
                        'fictional_time': self.fictional_time}
            if endpoint == '/orders/open':
                return {'orders': market.open_orders}
            if endpoint == '/positions':
                return {'positions': [
                    {'symbol': s, 'quantity': q, 'realized_pnl': 0.,
                     'unrealized_pnl': market.cash_by[s] + q * market.last_mid.get(s, 0.),
                     'average_price': None}
                    for s, q in market.position.items()]}
            if endpoint == '/trades':
                return {'trades': [
                    {'trade_id': f'virtual-{i}', 'symbol': f.symbol, 'side': f.side,
                     'price': f.price, 'quantity': f.qty, 'executed_at': str(f.t)}
                    for i, f in reversed(list(enumerate(market.fills))[-100:])]}
            if endpoint.startswith('/orderbook/') and endpoint[11:] in market.limits:
                symbol = endpoint[11:]
                levels = {'bids': collections.defaultdict(int), 'asks': collections.defaultdict(int)}
                if symbol in market.quotes and 0 <= self.now - market.quote_times.get(symbol, -math.inf) <= 5:
                    bid, ask = market.quotes[symbol]
                    levels['bids'][bid] += market.available.get((symbol, 'sell'), 0)
                    levels['asks'][ask] += market.available.get((symbol, 'buy'), 0)
                for order in market.orders.values():
                    if order.symbol == symbol:
                        side = 'bids' if order.side == 'buy' else 'asks'
                        levels[side][order.price] += order.qty - order.filled
                return {side: [{'price': price, 'quantity': quantity}
                               for price, quantity in sorted(book.items(), reverse=side == 'bids') if quantity > 0]
                        for side, book in levels.items()}
        elif method == 'DELETE' and endpoint == '/orders/all':
            if self.terminal:
                return {'cancelled': True}  # Terminal bookkeeping already removed orders.
            symbol = parse_qs(parsed.query).get('symbol', [None])[0]
            return {'cancelled': True} if market.cancel_all(symbol) else None
        elif method == 'POST' and endpoint == '/orders':
            if self.terminal or not market.market_open:
                return None
            oid = market.place(body['symbol'], body['side'], body['quantity'], body.get('price'))
            if oid is None:
                return None
            order = next(o for o in market.pending if o.id == oid)
            market._activate_pending()
            status = 'filled' if order.filled == order.qty else 'partial' if order.filled else 'pending'
            return {'order_id': oid, 'status': status, 'created_at': str(self.now),
                    'message': 'offline acknowledgement', 'message_type': 'order'}
        elif method == 'POST' and endpoint.startswith('/etf/'):
            parts = endpoint.strip('/').split('/')
            if len(parts) == 3 and parts[1] in market.case['etfs'] and parts[2] in ('create', 'redeem'):
                if self.terminal or not market.market_open:
                    return None
                success = (market.create if parts[2] == 'create' else market.redeem)(parts[1], body['quantity'])
                return {'status': 'created' if parts[2] == 'create' else 'redeemed',
                        'quantity': body['quantity']} if success else None
        error = f'unsupported offline endpoint: {method} {path}'
        raise NotImplementedError(error)


class OfflineExchange(LiveExchange):
    """Production client logic with every network method replaced locally."""
    def __init__(self, server):
        self.server = server
        super().__init__('https://offline.invalid', 'offline-dummy-key', False, rate_limit=90)

    @property
    def t(self):
        return self.server.now

    def get(self, path, api=True):
        return self.server.request('GET', path)

    def send(self, method, path, body=None):
        response = self.server.request(method, path, body)
        if response is None:
            self.rejected += 1
            self.state_ready = False
        return response


class AuditedSession(LiveSession):
    def __init__(self, *args, **kwargs):
        self.blocked_submissions = collections.Counter()
        super().__init__(*args, **kwargs)

    def submission_allowed(self, symbols=()):
        allowed = super().submission_allowed(symbols)
        if not allowed:
            reason = ('stopped' if self.stopped.is_set() else
                      'pending_news' if self.pending_news.is_set() else
                      'identity_or_history_or_quotes_or_pause')
            self.blocked_submissions[reason] += 1
        return allowed


def replay_client(case, frames, year, cid, settlement, *, fraction=.1, rtt=.25,
                  depth_scale=1, basket=False):
    cutoff = frames[-1]['received_at'] - frames[0]['received_at']
    server = ReplayServer(case, frames, year, cid, fraction=fraction,
                          depth_scale=depth_scale, rtt=rtt, end_at=cutoff)
    parameters = {**PARAMETERS, 'basket_edge': .01 if basket else 0}
    steps = 0
    with contextlib.redirect_stdout(io.StringIO()):
        exchange = OfflineExchange(server)
        exchange.refresh()
        if not exchange.state_ready or not isinstance(exchange.competition_id, str) or not exchange.competition_id.strip():
            raise RuntimeError('initial account snapshot is unavailable or missing competition identity')
        trader = FairValueTrader(**parameters)
        trader.on_start(exchange)
        # Like a fresh production session, establish the season from its first
        # observed news rather than pre-populating a partially initialized model.
        session = AuditedSession(exchange, trader, sync=3)
        session.pending_news = server.inbox.pending_news
        while True:
            pending = bool(server.inbox.events or server.inbox.quotes)
            if server.terminal:
                session.stop()
                if not pending:
                    break
            elif not pending:
                arrival = server.times[server.index] if server.index < len(server.times) else cutoff
                server.advance(min(arrival, server.now + .25, cutoff))
                if server.terminal:
                    session.stop()
            session.step(server.inbox.drain())
            steps += 1
        session.stop()
    if server.fatal_errors:
        raise ValueError(f'offline adapter contract failed: {server.fatal_errors}')
    if session.history_block_reason() or trader.model.reported_rounds != {1, 2, 3}:
        raise ValueError('replay ended without complete three-round model history')
    if not server.terminal or server.market.market_open or server.market.open_orders:
        raise ValueError('terminal close was not irrevocable')
    if set(settlement) != set(case['limits']):
        raise ValueError('complete settlement required after close')
    prices = {s: settlement[s] for s in settlement}
    if not all(isinstance(p, (float, int)) and not isinstance(p, bool)
               and math.isfinite(p) and p > 0 for p in prices.values()):
        raise ValueError('finite positive settlement required after close')
    market = server.market
    pnl = market.cash + sum(q * prices[s] for s, q in market.position.items())
    if not all(math.isfinite(v) for v in (pnl, server.lowest_mark, server.max_drawdown)):
        raise ValueError('nonfinite server accounting')
    return {'status': 'ok', 'rtt_seconds': rtt, 'displayed_depth_fraction': depth_scale,
            'basket_enabled': basket, 'simulated_settlement_pnl': pnl,
            'orders': market.next_id - 1, 'fills': len(market.fills),
            'conversions': market.conversions, 'basket_cycles': trader.basket.cycles if trader.basket else 0,
            'lowest_marked_pnl': server.lowest_mark, 'maximum_marked_drawdown': server.max_drawdown,
            'final_positions': market.position.copy(), 'server_rejections': market.rejected,
            'client_request_rejections': exchange.rejected,
            'blocked_submissions': dict(session.blocked_submissions),
            'request_counts': dict(collections.Counter(f"{r['method']} {r['path']}" for r in server.requests)),
            'request_count': len(server.requests), 'client_steps': steps,
            'ignored_closed_quotes': server.ignored_closed_quotes,
            'unusable_quotes': market.unusable_quotes,
            'final_report_rounds': sorted(trader.model.reported_rounds),
            'terminal_closed': server.terminal, 'cutoff_seconds': cutoff,
            'final_client_time': server.now}


def confirmed_completed_capture(batch, feed, cid, symbols):
    """Enforce ready/identity/year/prices before the helper reads any feed bytes."""
    batch = Path(batch)
    status = json.loads((batch / 'status.json').read_text())
    trial = status.get('trials', {}).get(cid, {})
    receipt = next((row for line in (batch / 'actions.jsonl').open()
                    if (row := json.loads(line)).get('kind') == 'settlement'
                    and row.get('competition_id') == cid), None)
    clock = receipt.get('clock', {}) if receipt else {}
    year = str(trial.get('year', ''))
    if (not trial.get('completed') or trial.get('invalid') or clock.get('state') != 'ready'
            or clock.get('competition_id') != cid or len(year) != 4 or not year.isdigit()
            or not str(clock.get('fictional_time', '')).startswith(year + '-')):
        raise ValueError('matching confirmed ready receipt required')
    prices = receipt.get('prices', {})
    if set(prices) != set(symbols) or not all(
            isinstance(p, (float, int)) and not isinstance(p, bool) and math.isfinite(p) and p > 0
            for p in prices.values()):
        raise ValueError('complete finite positive official prices required')
    return completed_capture(batch, feed, cid, symbols)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summary(rows):
    groups = collections.defaultdict(list)
    baseline = {(r['displayed_depth_fraction'], r['basket_enabled']): r
                for r in rows if r['status'] == 'ok' and r['rtt_seconds'] == 0}
    for row in rows:
        groups[row['rtt_seconds']].append(row)
    result = {}
    for rtt, group in groups.items():
        valid = [r for r in group if r['status'] == 'ok']
        pnl = [r['simulated_settlement_pnl'] for r in valid]
        deltas = [r['simulated_settlement_pnl'] - baseline[(r['displayed_depth_fraction'], r['basket_enabled'])]['simulated_settlement_pnl']
                  for r in valid if (r['displayed_depth_fraction'], r['basket_enabled']) in baseline]
        result[str(rtt)] = {'scenarios': len(group), 'errors': len(group) - len(valid),
            'mean_pnl': statistics.mean(pnl) if pnl else None, 'worst_pnl': min(pnl) if pnl else None,
            'best_pnl': max(pnl) if pnl else None, 'negative_scenarios': sum(p < 0 for p in pnl),
            'zero_order_scenarios': sum(r['orders'] == 0 for r in valid),
            'paired_mean_change_from_zero_rtt': statistics.mean(deltas) if deltas else None,
            'paired_scenarios': len(deltas)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('completed', 'observed'), required=True)
    parser.add_argument('--batch', type=Path)
    parser.add_argument('--observations', type=Path)
    parser.add_argument('--feed', type=Path, required=True)
    parser.add_argument('--competition-id', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    case = json.loads((ROOT / 'data/case.json').read_text())
    if args.mode == 'completed':
        if args.batch is None:
            parser.error('--batch is required in completed mode')
        _, trial, receipt, frames, count = confirmed_completed_capture(
            args.batch, args.feed, args.competition_id, case['limits'])
        year, coverage = trial['year'], {'news_count': count, 'quote_path_completeness_proven': False}
    else:
        if args.observations is None:
            parser.error('--observations is required in observed mode')
        receipt, frames, coverage = observed_capture(args.observations, args.feed, args.competition_id, case['limits'])
        year = receipt['year']
    if (not frames or not isinstance(receipt.get('at'), (int, float))
            or isinstance(receipt.get('at'), bool) or not math.isfinite(receipt['at'])
            or receipt['at'] < frames[-1]['received_at']):
        raise ValueError('finite closed receipt must follow the selected captured frames')
    sources = sorted([*ROOT.glob('ctc/*.py'), *ROOT.glob('ctc/*.json'), *ROOT.glob('ctc/*.npz'),
        ROOT / 'data/case.json', ROOT / 'bot/live.py', ROOT / 'bot/http_transport.py', ROOT / 'bot/control.py', Path(__file__),
        ROOT / 'scripts/replay_captured_market.py', ROOT / 'scripts/evaluate_observed_season.py',
        ROOT / 'scripts/observe_market_seasons.py', ROOT / 'scripts/experiment_execution_costs.py',
        ROOT / 'docs/serialized-replay-plan.md', ROOT / 'docs/serialized-forward-plan.md'])
    metadata = {'schema_version': 1, 'mode': args.mode, 'competition_id': args.competition_id,
        'year': year, 'official_receipt': receipt, 'coverage': coverage,
        'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in sources},
        'frames_sha256': hashlib.sha256(json.dumps(frames, sort_keys=True).encode()).hexdigest(),
        'receipt_sha256': hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest(),
        'frame_count': len(frames), 'first_at': frames[0]['received_at'], 'last_at': frames[-1]['received_at'],
        'receipt_at': receipt['at'], 'truncated_tail_seconds': receipt['at'] - frames[-1]['received_at'],
        'terminal_reason': 'last captured frame; close wins ties', 'parameters': PARAMETERS,
        'fraction': .1, 'rtts': [0., .05, .25, 1.], 'depths': [1., .5], 'baskets': [False, True],
        'limitations': ['Offline virtual fills are not actual or guaranteed counterfactual profits.',
            'Reused captures are not untouched validation; zero RTT is the paired timing reference.',
            'Fixed RTT with midpoint execution is a stress assumption, not an empirical latency fit.',
            'CPU computation is instantaneous; queue priority, own market impact, and extra fees are omitted.',
            'Conversions are instantaneous cash-neutral mutations at the request midpoint.',
            'Last-frame tail truncation can help or hurt profit and is not a lower bound.',
            'Quotes cannot reopen observed closed phases; server phase state is inferred from captured news.',
            'Practice-supervisor ownership/history requests are excluded; core production client is used.']}
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    rows, started = [], time.monotonic()
    with (args.out / 'results.jsonl').open('x') as output:
        for rtt in metadata['rtts']:
            for depth in metadata['depths']:
                for basket in metadata['baskets']:
                    try:
                        row = replay_client(case, frames, year, args.competition_id, receipt['prices'],
                                            rtt=rtt, depth_scale=depth, basket=basket)
                    except Exception as exc:
                        row = {'status': 'error', 'rtt_seconds': rtt, 'displayed_depth_fraction': depth,
                               'basket_enabled': basket, 'error': f'{type(exc).__name__}: {exc}'}
                    rows.append(row)
                    output.write(json.dumps(row) + '\n')
                    output.flush()
                    print(json.dumps({'runs': len(rows), 'scenario': [rtt, depth, basket], 'status': row['status']}), flush=True)
    for name, expected in metadata['source_sha256'].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f'source changed during experiment: {name}')
    result = {'runs': len(rows), 'elapsed_seconds': time.monotonic() - started,
              'errors': sum(r['status'] == 'error' for r in rows), 'by_rtt': summary(rows)}
    (args.out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
