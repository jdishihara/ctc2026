"""Bounded simulated-exchange practice. Reads .botkey locally; never accepts a raw key in argv.

Records every attempt, limits exposure, and waits for complete live season history.
The existing live submission/history guards remain in force.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot import live
from ctc.strategies import FairValueTrader


def order_id(order):
    return order.get('order_id', order.get('id'))


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def valid_order_id(value):
    return ((isinstance(value, str) and bool(value.strip()))
            or (type(value) is int and value > 0))


def check_order_history(journal, cid, payload, symbols):
    """Detect observed foreign orders; the API offers no exclusive-account lock.

    Require a fresh season with no pre-run orders. Never infer ownership from
    matching prices or quantities, or absorb old IDs as a rollover baseline.
    """
    if cid in journal.ownership_blocks:
        return False
    try:
        if not isinstance(payload, dict) or set(payload) != {'orders'}:
            raise ValueError('unrecognized order-history envelope or pagination')
        rows = payload['orders']
        if not isinstance(rows, list) or len(rows) >= 500:
            raise ValueError('order history is unavailable or saturated')
        ids = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('invalid order-history row')
            oid, qty, filled = order_id(row), row.get('quantity'), row.get('filled_quantity')
            if (not valid_order_id(oid) or oid in ids or row.get('symbol') not in symbols
                    or row.get('side') not in ('buy', 'sell') or not finite(qty)
                    or int(qty) != qty or qty <= 0 or not finite(filled)
                    or int(filled) != filled or not 0 <= filled <= qty):
                raise ValueError('invalid or duplicate order-history entry')
            ids.add(oid)
        owned = journal.owned.get(cid, set())
        foreign = ids - owned
        if foreign:
            journal.block_ownership(cid, 'unrecognized order history on shared account',
                                    order_ids=sorted(foreign, key=str))
            return False
        if (owned | journal.history_seen.get(cid, set())) - ids:
            raise ValueError('acknowledged or previously observed orders missing from history')
        journal.history_seen[cid] = ids
        return True
    except (TypeError, ValueError) as exc:
        journal.block_ownership(cid, str(exc))
        return False


def audit_order_history(ex, journal, cid):
    payload = ex.get('/orders?limit=500')
    clock = ex.get('/competitions/time')
    if clock.get('competition_id') != cid:
        raise ValueError('competition changed during order-history audit')
    return check_order_history(journal, cid, payload, ex.symbols), clock


def settlement_score(rows, prices, expected):
    """Do not invent cost basis or silently omit an account holding."""
    quantities, score = {}, 0.
    for row in rows:
        symbol, quantity, realized = row.get('symbol'), row.get('quantity'), row.get('realized_pnl')
        if (symbol not in prices or symbol in quantities or not finite(quantity)
                or int(quantity) != quantity or not finite(realized)):
            raise ValueError('incomplete settlement position receipt')
        quantities[symbol] = quantity
        score += realized
        if quantity:
            basis = row.get('average_price')
            if not finite(basis):
                raise ValueError('missing finite cost basis')
            score += quantity * (prices[symbol] - basis)
    if any(quantities.get(s, 0) != q for s, q in expected.items()) or not finite(score):
        raise ValueError('settlement holdings do not match reconciled account')
    return score


class Journal:
    def __init__(self, out, fraction=.1, loss_trigger=250., seasons=3, hours=3.):
        if (not all(math.isfinite(x) and x > 0 for x in (fraction, loss_trigger, hours))
                or fraction > 1 or type(seasons) is not int or seasons < 1):
            raise ValueError('practice bounds must be positive and finite; fraction <= 1')
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        if any((self.out / name).exists() for name in ('actions.jsonl', 'status.json', 'run.lock')):
            raise FileExistsError('use a new run directory; prior practice bounds cannot be reset')
        with (self.out / 'run.lock').open('x') as f:
            f.write(f'{time.time()}\n')
        self.fraction, self.loss_trigger, self.seasons = fraction, loss_trigger, seasons
        self.deadline = time.monotonic() + hours * 3600
        self.expires_at = time.time() + hours * 3600
        self.stop_reason = None
        self.owned = {}
        self.history_seen = {}
        self.ownership_blocks = {}
        self.activity = {}
        self.trials = {}
        self.latest = {}
        self.last_write = 0.

    def stop(self, reason):
        if self.stop_reason is None:
            self.stop_reason = reason
            print(f'PRACTICE STOP: {reason}', flush=True)

    def allowed(self):
        if time.monotonic() >= self.deadline:
            self.stop('maximum practice duration reached')
        return self.stop_reason is None

    def block_ownership(self, cid, reason, **details):
        if cid not in self.ownership_blocks:
            self.ownership_blocks[cid] = reason
            self.event('ownership_blocked', competition_id=cid, reason=reason, **details)
        trial = self.trials.get(cid)
        if trial and not trial['completed']:
            trial.update(invalid=reason, attributable=False)
        self.stop(reason)

    def event(self, kind, **data):
        with (self.out / 'actions.jsonl').open('a') as f:
            f.write(json.dumps({'at': time.time(), 'kind': kind, **data}) + '\n')

    def observe(self, ex):
        rows = ex.raw_positions.get('positions', []) if isinstance(ex.raw_positions, dict) else ex.raw_positions
        pnl = sum((p.get('realized_pnl') or 0) + (p.get('unrealized_pnl') or 0) for p in rows)
        self.latest = {'competition_id': ex.competition_id, 'year': ex.season_year,
                       'clock': ex.raw_clock, 'pnl': pnl, 'position': dict(ex.position),
                       'open_orders': len(ex.open_orders)}
        if ex.competition_id in self.trials:
            trial = self.trials[ex.competition_id]
            if not trial['completed']:
                trial['last_pnl'] = pnl
                trial['worst_pnl'] = min(trial['worst_pnl'], pnl)
        self.check_loss()

    def check_loss(self):
        total = sum(t['settlement_pnl'] if t['completed'] else t.get('last_pnl', 0)
                    for t in self.trials.values())
        if not finite(total):
            self.stop('invalid practice P&L receipt')
        if total <= -self.loss_trigger:
            self.stop(f'cumulative simulated P&L reached loss trigger ({total:.2f})')

    def start_trial(self, ex):
        if ex.competition_id not in self.trials:
            self.trials[ex.competition_id] = {'year': ex.season_year, 'started_at': time.time(),
                'last_pnl': 0., 'worst_pnl': 0., 'completed': False, 'order_count': 0, 'attempt_count': 0}
            self.event('trial_started', competition_id=ex.competition_id, year=ex.season_year)

    def write(self, force=False):
        now = time.monotonic()
        if not force and now - self.last_write < 5:
            return
        self.last_write = now
        data = {'updated_at': time.time(), 'fraction': self.fraction,
                'loss_trigger': self.loss_trigger, 'target_seasons': self.seasons,
                'expires_at': self.expires_at,
                'stop_reason': self.stop_reason, 'latest': self.latest,
                'trials': self.trials, 'activity': self.activity,
                'ownership_blocks': self.ownership_blocks,
                'observed_history_counts': {cid: len(ids) for cid, ids in self.history_seen.items()},
                'owned_order_count': sum(map(len, self.owned.values()))}
        temporary = self.out / 'status.tmp'
        temporary.write_text(json.dumps(data, indent=2) + '\n')
        temporary.replace(self.out / 'status.json')


class PracticeExchange(live.LiveExchange):
    def __init__(self, *args, journal, **kwargs):
        self.journal = journal
        self.raw_clock, self.raw_positions = {}, []
        self.verified_competition_id = None
        super().__init__(*args, **kwargs)
        # Copy rather than change the valuation case or the normal bot defaults.
        self.limits = {s: max(1, math.floor(n * journal.fraction)) for s, n in self.limits.items()}

    def get(self, path, api=True):
        result = super().get(path, api)
        if path == '/competitions/time':
            self.raw_clock = result
        elif path == '/positions?include_zero=true':
            self.raw_positions = result
        return result

    def refresh(self):
        super().refresh()
        if self.state_ready:
            try:
                clock = self.get('/competitions/time')
                if clock.get('competition_id') != self.competition_id:
                    raise ValueError('season changed during account refresh')
                if self.verified_competition_id != self.competition_id:
                    current = self.get('/competitions/current')
                    if current.get('competition_id') != self.competition_id or current.get('name') != 'Hurricane Season':
                        self.journal.stop('practice requires the Hurricane Season competition')
                        raise ValueError('unexpected competition identity')
                history_ok, clock = audit_order_history(self, self.journal, self.competition_id)
                if not history_ok:
                    self.journal.observe(self)
                    self.state_ready = self.market_open = False
                    return
                self.market_open = clock.get('state') == 'running'
                self.verified_competition_id = self.competition_id
            except Exception as exc:
                self.state_ready = self.market_open = False
                self.journal.latest['refresh_error'] = str(exc)
                return
            for cid, prior in self.journal.trials.items():
                if cid != self.competition_id and not prior['completed']:
                    prior['invalid'] = 'season changed without verified settlement receipt'
                    self.journal.stop(prior['invalid'])
            self.journal.observe(self)
            owned = self.journal.owned.get(self.competition_id, set())
            if any(o.get('order_id', o.get('id')) not in owned for o in self.open_orders):
                self.journal.block_ownership(self.competition_id, 'unrecognized open order on shared account')
                self.state_ready = False
            if any(abs(q) > self.limits[s] for s, q in self.position.items()):
                self.journal.stop('reconciled position exceeds practice limit')

    def send(self, method, path, body=None):
        if method == 'POST' and not self.journal.allowed():
            return None
        cid = self.competition_id
        if method == 'POST':
            self.journal.start_trial(self)
            self.journal.activity[cid] = self.journal.activity.get(cid, 0) + 1
            self.journal.trials[cid]['attempt_count'] += 1
            self.journal.event('request_attempt', competition_id=cid, path=path, body=body)
        response = super().send(method, path, body)
        if method == 'POST' and path == '/orders':
            oid = order_id(response) if isinstance(response, dict) else None
            if valid_order_id(oid):
                self.journal.owned.setdefault(cid, set()).add(oid)
                self.journal.trials[cid]['order_count'] += 1
            else:
                self.journal.block_ownership(cid, 'order acknowledgement lacks a trustworthy ID')
        if method == 'POST' and response is None:
            self.journal.block_ownership(cid, 'uncertain mutation response; ownership unresolved')
        self.journal.event('request', competition_id=cid,
                           method=method, path=path, body=body, response=response)
        return response

    def cancel_all(self, symbol=None):
        cid = self.competition_id
        owned = self.journal.owned.get(cid, set())
        if any(order_id(o) not in owned for o in self.open_orders
               if symbol is None or o.get('symbol') == symbol):
            self.journal.block_ownership(cid, 'unrecognized order prevents cancellation')
            return False
        targets = [order_id(o) for o in self.open_orders if symbol is None or o.get('symbol') == symbol]
        for oid in targets:
            if not self._action_ok() or self.get('/competitions/time').get('competition_id') != cid:
                self.state_ready = False
                return False
            if self.send('DELETE', f'/orders/{oid}') is None:
                return False
        if targets:
            self.refresh()
        return (self.state_ready and self.competition_id == cid and self.journal.stop_reason is None
                and not any(symbol is None or o.get('symbol') == symbol for o in self.open_orders))

    def _convert(self, etf, qty, action):
        sign = 1 if action == 'create' else -1
        changes = {etf: sign * qty, **{s: -sign * qty * n for s, n in self.case['etfs'][etf]['basket'].items()}}
        if any(abs(self.position[s] + delta) > self.limits[s] for s, delta in changes.items()):
            return False
        return super()._convert(etf, qty, action)


class PracticeSession(live.LiveSession):
    def __init__(self, *args, journal, **kwargs):
        super().__init__(*args, **kwargs)
        self.journal = journal
        self.last_settlement_check = 0.

    def submission_allowed(self, symbols=()):
        trial = self.journal.trials.get(self.ex.competition_id)
        return (self.journal.allowed() and trial is not None and not trial['completed']
                and not trial.get('invalid') and super().submission_allowed(symbols))

    def step(self, events):
        super().step(events)
        ex, journal = self.ex, self.journal
        trial = journal.trials.get(ex.competition_id)
        if (trial is None and ex.state_ready and journal.allowed() and self.history_block_reason() is None
                and self.strat.model.round == 1 and self.strat.model.last_obs['age'] <= 40):
            if any(ex.position.values()) or ex.open_orders:
                journal.block_ownership(ex.competition_id, 'new practice trial requires a flat unused account')
            else:
                journal.start_trial(ex)
                self.strat.last_trade_t = -1e9
                trial = journal.trials[ex.competition_id]
        if trial and not trial['completed']:
            if trial['attempt_count'] and (not self.news_complete or not self.strat.model.live_history_ready):
                journal.stop('history became incomplete after trading began')
            if (self.strat.model.round == 3 and self.strat.model.storm_reported
                    and not ex.market_open and ex.t - self.last_settlement_check >= 5):
                self.last_settlement_check = ex.t
                self.record_settlement(trial)
        journal.latest.update(history_block_reason=self.history_block_reason(), round=self.strat.model.round,
                              last_seq=self.latest_seq, market_open=ex.market_open)
        journal.write()

    def record_settlement(self, trial):
        ex, journal, cid = self.ex, self.journal, self.ex.competition_id
        ex.refresh()
        if (not ex.state_ready or ex.competition_id != cid or ex.market_open or ex.open_orders
                or trial.get('invalid') or cid in journal.ownership_blocks):
            return
        rows = ex.get('/symbols')['symbols']
        settlement = {s['symbol']: s.get('settlement_price') for s in rows if s.get('settlement_active')}
        clock = ex.get('/competitions/time')
        if clock.get('competition_id') != cid or clock.get('state') == 'running':
            return
        if not set(ex.symbols) <= settlement.keys() or not all(finite(settlement[s]) for s in ex.symbols):
            return
        positions = ex.raw_positions.get('positions', []) if isinstance(ex.raw_positions, dict) else ex.raw_positions
        try:
            score = settlement_score(positions, settlement, ex.position)
        except ValueError as exc:
            trial['settlement_error'] = str(exc)
            return
        trial.update(completed=True, settlement_pnl=score, last_pnl=score, completed_at=time.time())
        journal.event('settlement', competition_id=cid, pnl=score, prices=settlement, positions=positions, clock=clock)
        journal.check_loss()
        if sum(t['completed'] for t in journal.trials.values()) >= journal.seasons:
            journal.stop('requested complete practice seasons recorded')


async def practice(args, journal):
    key = Path(args.key_file).read_text().strip()
    ex = PracticeExchange(args.url, key, False, rate_limit=90, journal=journal,
                          reuse_http=getattr(args, 'reuse_http', False))
    journal.exchange = ex
    journal.event('http_transport', reuse_enabled=ex.http_reuse_enabled)
    ex.refresh()
    if not ex.state_ready or ex.open_orders or any(ex.position.values()):
        raise RuntimeError('Practice requires a reconciled flat account with no open orders')
    if ex.get('/system/bot-trading').get('mode') != 'full':
        raise RuntimeError('Bot trading mode is not full')
    strat = FairValueTrader(analog=True, min_edge=.025, edge_full=.03, sd_mult=.7,
        sigma=15., k=100, passive=.75, warmup=20., max_cross=.02, carry=.5, ent_cut=1.2,
        cone_w=1., cone_s0=20., cone_nu=0., isl_w=0., final_exact=True, final_edge=.005,
        final_edge_full=.005, basket_edge=.01, basket_participation=.5, announce_wait=60.)
    strat.on_start(ex)
    seen = set()
    year, rnd, count = live.replay_feed_log(args.feed_log, ex, strat, seen)
    if count:
        strat.fair = strat.compute_fair()
        ex.round = rnd
    session = PracticeSession(ex, strat, sync=3., season_year=year, last_round=rnd,
                              seen_seq=seen, journal=journal)
    inbox = live.MarketInbox()
    ws_url = ex.url.replace('https://', 'wss://', 1).replace('http://', 'ws://', 1) + '/ws/v1/market-data'

    async def receive():
        while journal.allowed():
            try:
                async with live.websockets.connect(ws_url, additional_headers={'X-API-Key': key}) as ws:
                    await ws.send(json.dumps({'action': 'subscribe', 'symbols': ex.symbols, 'channels': ['news', 'quotes']}))
                    print('PRACTICE connected; awaiting complete history', flush=True)
                    await live.receive_market_data(ws, inbox, lambda: ex.t)
            except (OSError, live.websockets.WebSocketException) as exc:
                print(f'PRACTICE disconnected: {exc}', flush=True)
            inbox.put({'type': 'disconnected'}, ex.t)
            await asyncio.sleep(2)

    receiver = asyncio.create_task(receive())
    driver = asyncio.create_task(live.drive_market_data(session, inbox, receiver))
    try:
        while journal.allowed() and not driver.done():
            await asyncio.sleep(.5)
        if driver.done():
            await driver
    finally:
        session.stop()
        driver.cancel()
        receiver.cancel()
        await asyncio.gather(driver, receiver, return_exceptions=True)
    return journal, ex


def cleanup_status(journal, state, **data):
    journal.latest['cleanup'] = {'state': state, 'observed_at': time.time(), **data}
    journal.event('cleanup_' + state, **data)


class CleanupExchange(live.LiveExchange):
    """A separate, reduction-only adapter, fenced to the original competition."""
    def __init__(self, original, journal):
        self.expected_id, self.journal = original.competition_id, journal
        self.owned = journal.owned.setdefault(self.expected_id, set())
        super().__init__(original.url, original.key, False, rate_limit=90)

    def scope_ok(self):
        reason = None
        if not self.state_ready:
            reason = 'account reconciliation failed'
        elif self.competition_id != self.expected_id:
            reason = 'competition changed; cleanup cannot trade the new account'
        elif self.expected_id in self.journal.ownership_blocks:
            reason = self.journal.ownership_blocks[self.expected_id]
        elif any(order_id(o) not in self.owned for o in self.open_orders):
            reason = 'unrecognized orders; shared account requires inspection'
            self.journal.block_ownership(self.expected_id, reason)
        else:
            try:
                history_ok, clock = audit_order_history(self, self.journal, self.expected_id)
                if not history_ok:
                    reason = self.journal.ownership_blocks[self.expected_id]
                self.market_open = clock.get('state') == 'running'
            except Exception as exc:
                reason = f'cleanup ownership audit failed: {exc}'
        if reason:
            self.state_ready = False
            cleanup_status(self.journal, 'attention', reason=reason)
            return False
        return True

    def send(self, method, path, body=None):
        if not self.scope_ok():
            return None
        if method == 'DELETE':
            if path not in {f'/orders/{oid}' for oid in self.owned}:
                return None
        elif method == 'POST' and path == '/orders':
            quantity = self.position.get(body.get('symbol'), 0)
            if (not self.market_open or self.open_orders or not quantity
                    or body.get('side') != ('sell' if quantity > 0 else 'buy')
                    or not 0 < body.get('quantity', 0) <= abs(quantity)):
                cleanup_status(self.journal, 'attention', reason='cleanup order would not strictly reduce reconciled exposure')
                return None
        else:
            return None
        response = super().send(method, path, body)
        if method == 'POST':
            if isinstance(response, dict) and valid_order_id(order_id(response)):
                # Register before LiveExchange.place can refresh a status-only fill.
                self.owned.add(order_id(response))
            else:
                self.journal.block_ownership(self.expected_id, 'cleanup acknowledgement leaves ownership unresolved')
        return response


def reconcile_stop(journal, original):
    """Runs after asyncio.run has joined its HTTP worker; close only this run's exposure."""
    if original is None:
        return
    if not journal.activity.get(original.competition_id):
        cleanup_status(journal, 'skipped', reason='no exposure-changing attempts in this competition')
        return
    ex = CleanupExchange(original, journal)
    for attempt in range(5):
        ex.refresh()
        if not ex.scope_ok():
            return
        for order in list(ex.open_orders):
            oid = order_id(order)
            result = ex.send('DELETE', f'/orders/{oid}')
            journal.event('cleanup_cancel', order_id=oid, response=result)
            if result is None:
                break
        ex.refresh()
        if not ex.scope_ok():
            return
        if ex.open_orders:
            # A timeout is not proof of cancellation. Never replace these orders.
            time.sleep(1)
            continue
        if not any(ex.position.values()):
            cleanup_status(journal, 'flat', competition_id=ex.competition_id)
            return
        if not ex.market_open:
            rows = ex.get('/symbols')['symbols']
            if not ex.scope_ok():
                return
            settled = {s['symbol'] for s in rows if s.get('settlement_active') and finite(s.get('settlement_price'))}
            all_settled = all(s in settled for s, q in ex.position.items() if q)
            journal.event('cleanup_closed', positions=ex.position, all_holdings_settled=all_settled)
            cleanup_status(journal, 'settled' if all_settled else 'attention',
                           reason='market closed', positions=ex.position)
            return
        for symbol in ex.symbols:
            if not ex.position[symbol]:
                continue
            book = ex.get(f'/orderbook/{symbol}?depth=1')
            ex.refresh()
            if not ex.scope_ok():
                return
            if ex.open_orders or not ex.market_open:
                break
            quantity = ex.position[symbol]
            if not quantity:
                continue
            side = 'sell' if quantity > 0 else 'buy'
            levels = book['bids' if quantity > 0 else 'asks']
            if not levels or not finite(levels[0].get('price')) or levels[0]['price'] <= 0:
                continue
            price = max(.01, levels[0]['price'] * (.99 if quantity > 0 else 1.01))
            oid = ex.place(symbol, side, abs(quantity), price)
            journal.event('cleanup_order', symbol=symbol, side=side, quantity=abs(quantity), order_id=oid)
            ex.refresh()
            if not ex.scope_ok():
                return
        time.sleep(1)
    ex.refresh()
    if ex.scope_ok() and not ex.open_orders and not any(ex.position.values()):
        cleanup_status(journal, 'flat', competition_id=ex.competition_id)
    else:
        cleanup_status(journal, 'attention', reason='cleanup retry limit', positions=ex.position, open_orders=ex.open_orders)


def validated_account_rows(positions, orders, symbols):
    if (not isinstance(positions, dict) or set(positions) != {'positions'}
            or not isinstance(positions['positions'], list)
            or not isinstance(orders, dict) or set(orders) != {'orders'}
            or not isinstance(orders['orders'], list)):
        raise ValueError('invalid final account envelope')
    rows, order_rows = positions['positions'], orders['orders']
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid final position row')
        symbol, qty = row.get('symbol'), row.get('quantity')
        unrealized = row.get('unrealized_pnl')
        if (symbol not in symbols or symbol in seen or not finite(qty) or int(qty) != qty
                or not finite(row.get('realized_pnl'))
                or (not finite(unrealized) and not (qty == 0 and unrealized is None))):
            raise ValueError('invalid final position quantity or P&L')
        seen.add(symbol)
    seen.clear()
    for row in order_rows:
        if not isinstance(row, dict):
            raise ValueError('invalid final open-order row')
        oid, qty, filled = order_id(row), row.get('quantity'), row.get('filled_quantity')
        if (not valid_order_id(oid) or oid in seen or row.get('symbol') not in symbols
                or row.get('side') not in ('buy', 'sell') or not finite(qty) or int(qty) != qty
                or qty <= 0 or not finite(filled) or int(filled) != filled or not 0 <= filled <= qty):
            raise ValueError('invalid final open-order quantity or identity')
        seen.add(oid)
    pnl = sum(p['realized_pnl'] + (p.get('unrealized_pnl') or 0) for p in rows)
    if not finite(pnl):
        raise ValueError('non-finite final account P&L')
    return rows, order_rows, pnl


def final_receipt(journal, original):
    if original is None:
        return
    clock = original.get('/competitions/time')
    positions = original.get('/positions?include_zero=true')
    orders = original.get('/orders/open')
    try:
        history = original.get('/orders?limit=500')
        history_error = None
    except Exception as exc:
        history, history_error = None, str(exc)
    end_clock = original.get('/competitions/time')
    cid = clock.get('competition_id')
    identity_verified = bool(cid) and cid == end_clock.get('competition_id') == original.competition_id
    history_clear = identity_verified and check_order_history(journal, cid, history, original.symbols)
    account_error = None
    try:
        rows, order_rows, pnl = validated_account_rows(positions, orders, original.symbols)
        flat = not order_rows and not any(p['quantity'] for p in rows)
    except (TypeError, ValueError) as exc:
        account_error = str(exc)
        rows, order_rows, pnl, flat = [], [], None, None
        if identity_verified:
            journal.block_ownership(cid, account_error)
        history_clear = False
    if identity_verified and any(order_id(o) not in journal.owned.get(cid, set()) for o in order_rows):
        journal.block_ownership(cid, 'unrecognized open order in final receipt')
        history_clear = False
    cleanup = journal.latest.get('cleanup', {})
    reopened = (identity_verified and cleanup.get('competition_id') == cid
                and cleanup.get('state') == 'flat' and flat is False)
    if reopened:
        journal.block_ownership(cid, 'account reopened after cleanup observed flat')
        history_clear = False
    if not history_clear or reopened:
        cleanup_status(journal, 'attention', reason=journal.ownership_blocks.get(cid,
                       history_error or 'final receipt identity or ownership not verified'))
    verified = identity_verified and history_clear and account_error is None and not reopened
    data = {'clock': clock, 'end_clock': end_clock, 'positions': positions, 'orders': orders,
            'identity_verified': identity_verified, 'history_ownership_clear': history_clear,
            'account_valid': account_error is None, 'account_error': account_error,
            'flat': flat, 'reopened_after_flat': reopened, 'verified': verified}
    (journal.out / 'final-receipt.json').write_text(json.dumps(data, indent=2) + '\n')
    if not identity_verified or account_error:
        journal.latest['final_receipt'] = {'verified': False,
            'reason': account_error or 'competition changed during final receipt'}
        return
    trial = journal.trials.get(clock.get('competition_id'))
    if trial and not trial['completed']:
        trial['last_pnl'] = pnl
        trial['after_cleanup_pnl'] = pnl
        journal.check_loss()
    journal.latest['final_receipt'] = {'competition_id': cid, 'pnl': pnl, 'verified': verified,
        'history_ownership_clear': history_clear, 'flat': flat, 'reopened_after_flat': reopened,
        'nonzero_positions': sum(bool(p.get('quantity')) for p in rows),
        'open_orders': len(order_rows)}


def finish(journal):
    original = getattr(journal, 'exchange', None)
    try:
        reconcile_stop(journal, original)
    except Exception as exc:
        cleanup_status(journal, 'attention', reason=f'{type(exc).__name__}: {exc}')
    try:
        final_receipt(journal, original)
    except Exception as exc:
        journal.latest['final_receipt'] = {'verified': False, 'error': f'{type(exc).__name__}: {exc}'}
        journal.event('receipt_attention', **journal.latest['final_receipt'])
    finally:
        journal.write(force=True)
        if original is not None:
            original.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='https://cornelltradingcompetition.org')
    parser.add_argument('--key-file', default='.botkey')
    parser.add_argument('--reuse-http', action='store_true',
                        help='experimental connection reuse during practice; respects configured proxies')
    parser.add_argument('--out', required=True)
    parser.add_argument('--feed-log', required=True)
    parser.add_argument('--fraction', type=float, default=.1)
    parser.add_argument('--loss-trigger', type=float, default=250.)
    parser.add_argument('--seasons', type=int, default=3)
    parser.add_argument('--hours', type=float, default=3.)
    args = parser.parse_args()
    if not 0 < args.fraction <= 1 or args.loss_trigger <= 0 or args.seasons < 1 or args.hours <= 0:
        parser.error('positive limits required; fraction must be at most 1')
    journal = Journal(args.out, args.fraction, args.loss_trigger, args.seasons, args.hours)
    try:
        asyncio.run(practice(args, journal))
    except KeyboardInterrupt:
        journal.stop('operator interrupt')
    except Exception as exc:
        journal.stop(f'practice error: {type(exc).__name__}: {exc}')
        raise
    finally:
        finish(journal)


if __name__ == '__main__':
    main()
