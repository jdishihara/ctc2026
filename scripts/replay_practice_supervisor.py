"""Offline production-supervisor diagnostic; never connects to an exchange.

Uses complete closed captures and the fixed protocol in supervised-replay-plan.
Production ownership, loss, settlement and cleanup code runs through a local
transport. All module patches are scoped to this single-threaded diagnostic.
"""
from __future__ import annotations

import collections
import contextlib
import copy
from dataclasses import asdict
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot import live, practice
from ctc.strategies import FairValueTrader
from scripts import replay_serialized_client as core
from scripts.experiment_execution_costs import PARAMETERS
from scripts.replay_captured_market import ReplayExchange


class AverageCostBook:
    def __init__(self, symbols):
        self.position = dict.fromkeys(symbols, 0)
        self.average = dict.fromkeys(symbols, None)
        self.realized = dict.fromkeys(symbols, 0.)

    @property
    def cash(self):
        return sum(self.realized[s] - q * (self.average[s] or 0.)
                   for s, q in self.position.items())

    def trade(self, symbol, quantity, price):
        if (symbol not in self.position or type(quantity) is not int or not quantity
                or not practice.finite(price) or price <= 0):
            raise ValueError('finite positive price and nonzero integer quantity required')
        old, basis = self.position[symbol], self.average[symbol]
        new = old + quantity
        if not old or old * quantity > 0:
            self.average[symbol] = (abs(old) * (basis or 0.) + abs(quantity) * price) / abs(new)
        else:
            closed = min(abs(old), abs(quantity))
            self.realized[symbol] += closed * (1 if old > 0 else -1) * (price - basis)
            if not new:
                self.average[symbol] = None
            elif new * old < 0:
                self.average[symbol] = float(price)
        self.position[symbol] = new

    def rows(self, marks):
        rows = []
        for s, q in self.position.items():
            if q and (s not in marks or not practice.finite(marks[s]) or marks[s] <= 0):
                raise ValueError(f'held symbol lacks a finite positive mark: {s}')
            rows.append(dict(symbol=s, quantity=q, average_price=self.average[s],
                realized_pnl=self.realized[s],
                unrealized_pnl=q * (marks[s] - self.average[s]) if q else 0.))
        return rows


class AccountingReplayExchange(ReplayExchange):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.book = AverageCostBook(self.symbols)
        self.order_history = {}
        self.maximum_positions = dict.fromkeys(self.symbols, 0)
        self.diagnostic_limits = None

    def assert_practice_exposure(self):
        if self.diagnostic_limits is None:
            return
        for symbol, cap in self.diagnostic_limits.items():
            q = self.position[symbol]
            orders = [o for o in (*self.orders.values(), *self.pending) if o.symbol == symbol]
            buys = sum(o.qty - o.filled for o in orders if o.side == 'buy')
            sells = sum(o.qty - o.filled for o in orders if o.side == 'sell')
            if abs(q) > cap or q + buys > cap or q - sells < -cap:
                raise ValueError(f'practice exposure exceeds independent cap: {symbol}')

    def assert_accounting(self):
        if self.position != self.book.position or not math.isclose(self.cash, self.book.cash, rel_tol=1e-10, abs_tol=1e-7):
            raise ValueError('average-cost ledger disagrees with server quantities/cash')
        rows = self.book.rows(self.last_mid)
        marked = sum(r['realized_pnl'] + r['unrealized_pnl'] for r in rows)
        if not math.isclose(self.pnl(), marked, rel_tol=1e-10, abs_tol=1e-7):
            raise ValueError('average-cost mark disagrees with server cash plus holdings')
        for s, q in self.position.items():
            self.maximum_positions[s] = max(self.maximum_positions[s], abs(q))
        self.assert_practice_exposure()

    def place(self, *args, **kwargs):
        oid = super().place(*args, **kwargs)
        if oid is not None:
            self.order_history[oid] = next(o for o in self.pending if o.id == oid)
            self.assert_practice_exposure()
        return oid

    def _fill(self, order, qty, price, passive):
        super()._fill(order, qty, price, passive)
        self.book.trade(order.symbol, qty if order.side == 'buy' else -qty, price)
        self.assert_accounting()

    def _etf(self, etf, qty, sign):
        basket = self.case['etfs'][etf]['basket']
        if any(s not in self.last_mid or not practice.finite(self.last_mid[s]) or self.last_mid[s] <= 0 for s in basket):
            raise ValueError('conversion requires finite component marks for accounting')
        price = sum(self.last_mid[s] * n for s, n in basket.items())
        accepted = super()._etf(etf, qty, sign)
        if accepted:
            self.book.trade(etf, sign * qty, price)
            for s, n in basket.items():
                self.book.trade(s, -sign * n * qty, self.last_mid[s])
            self.assert_accounting()
        return accepted


class PracticeReplayServer(core.ReplayServer):
    def __init__(self, *args, settlement=None, settlement_available_at=None,
                 fraction=.1, **kwargs):
        # The server has full exchange limits; the adapters scale client limits.
        super().__init__(*args, fraction=1., market_factory=AccountingReplayExchange, **kwargs)
        self.settlement = settlement
        self.settlement_available_at = settlement_available_at
        if settlement_available_at is not None and (not practice.finite(settlement_available_at)
                or self.end_at is None or settlement_available_at < self.end_at):
            raise ValueError('official receipt must follow terminal close')
        self.monitor = None

    def latch(self, exc):
        value = f'{type(exc).__name__}: {exc}'
        if value not in self.fatal_errors:
            self.fatal_errors.append(value)

    def advance(self, timestamp, *, interruptible=False):
        try:
            while self.monitor is not None and not self.monitor.cancelled and self.monitor.next_tick <= timestamp:
                super().advance(self.monitor.next_tick)
                self.monitor.poll()
                if interruptible and self.monitor.cancelled:
                    self.market.assert_accounting()
                    return
            super().advance(timestamp)
            self.market.assert_accounting()
        except Exception as exc:
            self.latch(exc)
            raise

    def request(self, method, path, body=None):
        try:
            return super().request(method, path, body)
        except Exception as exc:
            self.latch(exc)
            raise

    def _operation(self, method, path, body):
        endpoint = urlsplit(path).path
        if method == 'GET':
            if endpoint == '/positions':
                self.market.assert_accounting()
                return {'positions': self.market.book.rows(self.market.last_mid)}
            if endpoint == '/competitions/current':
                return {'competition_id': self.competition_id, 'name': 'Hurricane Season'}
            if endpoint == '/system/bot-trading':
                return {'mode': 'full'}
            if endpoint == '/orders':
                return {'orders': [dict(order_id=o.id, symbol=o.symbol, side=o.side,
                    quantity=o.qty, filled_quantity=o.filled, price=o.price)
                    for o in self.market.order_history.values()]}
            if endpoint == '/symbols':
                active = (self.terminal and self.settlement_available_at is not None
                          and self.now >= self.settlement_available_at)
                return {'symbols': [dict(symbol=s, settlement_active=active,
                    settlement_price=self.settlement[s] if active else None)
                    for s in self.market.symbols]}
        if method == 'DELETE' and endpoint.startswith('/orders/') and endpoint != '/orders/all':
            try:
                oid = int(endpoint[len('/orders/'):])
            except ValueError as exc:
                raise ValueError('invalid offline cancellation ID') from exc
            return {'cancelled': True} if self.market.cancel(oid) else None
        return super()._operation(method, path, body)


class ServerTransport(live.LiveExchange):
    @property
    def t(self):
        return self.server.now

    def get(self, path, api=True):
        response = self.server.request('GET', path)
        if urlsplit(path).path == '/positions':
            self.positions_request = self.server.requests[-1]
        return response

    def send(self, method, path, body=None):
        response = self.server.request(method, path, body)
        if response is None:
            self.rejected += 1
            self.state_ready = False
        return response


class OfflinePracticeExchange(practice.PracticeExchange, ServerTransport):
    def __init__(self, server, journal):
        self.server = server
        super().__init__('https://offline.invalid', 'offline-dummy-key', False,
                         rate_limit=90, journal=journal)


class OfflineCleanupExchange(practice.CleanupExchange, ServerTransport):
    def __init__(self, original, journal):
        self.server = original.server
        super().__init__(original, journal)


class OfflineBaselineExchange(ServerTransport):
    def __init__(self, server):
        self.server = server
        super().__init__('https://offline.invalid', 'offline-dummy-key', False, rate_limit=90)
        self.limits = {s: max(1, math.floor(n * .1)) for s, n in self.limits.items()}


class VirtualTime:
    def __init__(self, server):
        self.server = server

    def time(self):
        return self.server.start + self.server.now

    def monotonic(self):
        return self.server.now

    def sleep(self, seconds):
        self.server.advance(self.server.now + seconds)


class AuditedJournal(practice.Journal):
    def __init__(self, *args, server, **kwargs):
        self.server, self.observations, self.stop_at = server, [], None
        self.stop_market_open = None
        super().__init__(*args, **kwargs)

    def stop(self, reason):
        if self.stop_reason is None:
            self.stop_at = self.server.now
            self.stop_market_open = self.server.market.market_open
        super().stop(reason)

    def observe(self, ex):
        super().observe(ex)
        request = getattr(ex, 'positions_request', {})
        self.observations.append(dict(observed_at=self.server.now,
            positions_started_at=request.get('started_at'),
            positions_executed_at=request.get('executed_at'),
            positions_completed_at=request.get('completed_at'),
            pnl=self.latest.get('pnl'), server_pnl=self.server.market.pnl(),
            stop_reason=self.stop_reason))


class VirtualMonitor:
    def __init__(self, server, journal, session):
        self.server, self.journal, self.session = server, journal, session
        self.started_at = server.now
        self.next_tick, self.cancelled, self.detected_at = server.now, False, None
        self.poll()

    def poll(self):
        if not self.journal.allowed():
            self.cancelled, self.detected_at = True, self.server.now
            self.session.stop()
        self.next_tick += .5


def trace_hashes(server):
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()
    requests = [{k: v for k, v in r.items() if k != 'response' or r['method'] != 'GET'}
                for r in server.requests]
    return dict(request_trace_sha256=digest(requests),
                fill_trace_sha256=digest([asdict(f) for f in server.market.fills]))


def replay_baseline(case, frames, year, cid, settlement, **kwargs):
    if kwargs.get('fraction', .1) != .1:
        raise ValueError('the fixed baseline comparison requires 10% client limits')
    created = []

    class RecordingServer(PracticeReplayServer):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            created.append(self)

    with patch.object(core, 'ReplayServer', RecordingServer), patch.object(core, 'OfflineExchange', OfflineBaselineExchange):
        result = core.replay_client(case, frames, year, cid, settlement, **kwargs)
    return result, trace_hashes(created[0])


def startup_prefix(exchange, trader, server, out):
    # Perform the real feed loader's clock request once, then snapshot only data
    # received by this virtual read time. Its subsequent cached GET costs no
    # second request; CPU and file IO are instantaneous in this diagnostic.
    clock = exchange.get('/competitions/time')
    prefix = [f for f, at in zip(server.frames, server.times) if at <= server.now and f.get('type') == 'news']
    path = Path(out) / 'startup-feed.jsonl'
    path.write_text(''.join(json.dumps(f) + '\n' for f in prefix))
    seen, original_get = set(), exchange.get
    with patch.object(exchange, 'get', lambda path, api=True: clock if path == '/competitions/time' else original_get(path, api)):
        year, rnd, count = live.replay_feed_log(str(path), exchange, trader, seen)
    if count:
        trader.fair = trader.compute_fair()
        exchange.round = rnd
    return year, rnd, count, seen


def wait_for_driver(server):
    """A healthy monitor tick never restarts the driver's 0.25-second wait."""
    arrival = server.times[server.index] if server.index < len(server.times) else math.inf
    server.advance(min(arrival, server.now + .25), interruptible=True)


def replay_supervised(case, frames, year, cid, settlement, *, receipt_at, out,
                      fraction=.1, rtt=.25, depth_scale=1, basket=False):
    cutoff = frames[-1]['received_at'] - frames[0]['received_at']
    available = receipt_at - frames[0]['received_at']
    server = PracticeReplayServer(case, frames, year, cid, rtt=rtt, depth_scale=depth_scale,
        end_at=cutoff, settlement=settlement, settlement_available_at=available)
    server.market.diagnostic_limits = {s: max(1, math.floor(n * fraction)) for s, n in case['limits'].items()}
    parameters = {**PARAMETERS, 'basket_edge': .01 if basket else 0}
    monitor, session, trader, steps, prefix_count = None, None, None, 0, 0
    errors = []
    receipt_requests = []
    original_receipt = practice.final_receipt

    def audited_receipt(journal, original):
        start = len(server.requests)
        try:
            return original_receipt(journal, original)
        finally:
            receipt_requests.extend({k: r[k] for k in ('method', 'path', 'started_at', 'executed_at', 'completed_at') if k in r}
                                    for r in server.requests[start:])

    with contextlib.redirect_stdout(io.StringIO()), patch.object(practice, 'time', VirtualTime(server)), \
            patch.object(practice, 'CleanupExchange', OfflineCleanupExchange), \
            patch.object(practice, 'final_receipt', audited_receipt):
        journal = AuditedJournal(out, server=server, fraction=fraction, loss_trigger=250., seasons=1, hours=3.)
        try:
            exchange = OfflinePracticeExchange(server, journal)
            journal.exchange = exchange
            exchange.refresh()
            if not exchange.state_ready or exchange.open_orders or any(exchange.position.values()):
                raise RuntimeError('Practice requires a reconciled flat account with no open orders')
            if exchange.get('/system/bot-trading').get('mode') != 'full':
                raise RuntimeError('Bot trading mode is not full')
            trader = FairValueTrader(**parameters)
            trader.on_start(exchange)
            initial_year, rnd, prefix_count, seen = startup_prefix(exchange, trader, server, out)
            session = practice.PracticeSession(exchange, trader, sync=3., journal=journal,
                season_year=initial_year, last_round=rnd, seen_seq=seen)
            session.pending_news = server.inbox.pending_news
            monitor = VirtualMonitor(server, journal, session)
            server.monitor = monitor
            drain_until = available + max(60., 100. * rtt)
            while not monitor.cancelled:
                if server.now >= drain_until:
                    journal.stop('offline closed-market drain exhausted')
                if not (server.inbox.events or server.inbox.quotes):
                    wait_for_driver(server)
                if monitor.cancelled:
                    break
                session.step(server.inbox.drain())
                steps += 1
        except Exception as exc:
            errors.append(f'{type(exc).__name__}: {exc}')
            journal.stop(f'practice error: {type(exc).__name__}: {exc}')
        finally:
            if session is not None:
                session.stop()
            server.monitor = None
            cleanup_started_at = server.now
            practice.finish(journal)
            cleanup_completed_at = server.now
    # Production code can catch refresh/cleanup exceptions. Any virtual-server
    # contract failure invalidates the diagnostic, even if it returned a receipt.
    if server.fatal_errors:
        raise ValueError(f'offline adapter contract failed: {server.fatal_errors}')
    receipt_positions = copy.deepcopy(server.market.position)
    receipt_orders = copy.deepcopy(server.market.open_orders)
    receipt_path = Path(out, 'final-receipt.json')
    observed_receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    fills_at_receipt = len(server.market.fills)
    server.advance(max(server.now, available, cutoff))
    if server.fatal_errors or not server.terminal or server.market.market_open or server.market.open_orders:
        raise ValueError('invalid terminal account after cleanup')
    prices = {s: settlement[s] for s in settlement}
    if set(prices) != set(case['limits']) or not all(practice.finite(v) and v > 0 for v in prices.values()):
        raise ValueError('complete finite positive settlement required after close')
    market = server.market
    pnl = market.cash + sum(q * prices[s] for s, q in market.position.items())
    scored = practice.settlement_score(market.book.rows(prices), prices, market.position)
    if not math.isclose(pnl, scored, rel_tol=1e-10, abs_tol=1e-7):
        raise ValueError('terminal settlement accounting disagreement')
    trial = journal.trials.get(cid)
    stop_phase = ('captured_interval' if journal.stop_at is not None and journal.stop_at < cutoff else
                  'terminal_to_receipt_gap' if journal.stop_at is not None and journal.stop_at < available else
                  'after_receipt' if journal.stop_at is not None else None)
    result = dict(status='error' if errors else 'ok', errors=errors, rtt_seconds=rtt,
        displayed_depth_fraction=depth_scale, basket_enabled=basket,
        trial_state='completed' if trial and trial['completed'] else 'incomplete_trial' if trial else 'no_trial',
        trial=trial, stop_reason=journal.stop_reason, stop_at=journal.stop_at, stop_phase=stop_phase,
        stop_market_open=journal.stop_market_open,
        monitor_started_at=monitor.started_at if monitor else None,
        monitor_detected_at=monitor.detected_at if monitor else None,
        cleanup_started_at=cleanup_started_at, cleanup_completed_at=cleanup_completed_at,
        cleanup=journal.latest.get('cleanup'), final_receipt=journal.latest.get('final_receipt'),
        server_positions_after_final_receipt=receipt_positions,
        server_orders_after_final_receipt=receipt_orders,
        observed_final_receipt=observed_receipt, final_receipt_requests=receipt_requests,
        terminal_settlement_pnl=pnl, final_positions=market.position.copy(),
        fills_after_final_receipt_requests=len(market.fills) - fills_at_receipt,
        orders=market.next_id - 1, fills=len(market.fills), conversions=market.conversions,
        maximum_absolute_positions=market.maximum_positions,
        lowest_marked_pnl=server.lowest_mark, maximum_marked_drawdown=server.max_drawdown,
        final_report_rounds=sorted(trader.model.reported_rounds) if trader else [],
        history_block_reason=session.history_block_reason() if session else 'startup failed',
        prefix_messages=prefix_count, client_steps=steps,
        request_counts=dict(collections.Counter(f"{r['method']} {r['path']}" for r in server.requests)),
        request_count=len(server.requests), terminal_closed=server.terminal, cutoff_seconds=cutoff,
        settlement_available_at=available, final_client_time=cleanup_completed_at,
        **trace_hashes(server))
    Path(out, 'observations.json').write_text(json.dumps(journal.observations, indent=2) + '\n')
    Path(out, 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result
