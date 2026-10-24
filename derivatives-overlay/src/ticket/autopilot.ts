// Auto-pilot: runs the ticket queue without a human. Each step picks the next ticket (edge tickets during an event,
// flatten tickets after the snap), prefills the form through the same path as Alt+N, re-reads the form, and clicks the
// submit button through safeSubmit(), which refuses unless armed, verified and inside the rate budget.
import { ExchangeApi, OrderBody, PATHS } from '../core/api';
import { Config } from '../core/config';
import { textOf } from '../core/dom-readers';
import { Ticket, ticketStillValid } from '../engine/tickets';
import { Store } from '../state/store';
import { apiSubmitRefusal, safeSubmit, safeTabClick } from './guard';
import { PrefillResult } from './prefill';
import { findOrderPanel, OrderPanel } from './selectors';

export interface AutopilotDeps {
  store: Store;
  doc: Document;
  prefill: (t: Ticket) => Promise<PrefillResult>;
  symbolRe: () => RegExp;
  skip: (el: Element) => boolean;
  /** find the product tab button for an underlying (null = none visible) */
  findTab?: (underlying: string) => Element | null;
  /** cookie-authenticated REST client; with auto.submitVia = 'api' tickets are POSTed instead of typed and clicked */
  api?: ExchangeApi;
  /** an order POST answered 429: the REST poller yields for a while so the orders get through */
  onRateLimit?: () => void;
  now?: () => number;
}

export interface StepResult {
  action: 'idle' | 'skipped' | 'prefill-failed' | 'tab-switched' | 'refused' | 'submitted' | 'cancelled';
  detail: string;
  ticket?: Ticket;
}

export class Autopilot {
  private busy = false;
  /** contract:side -> { t, pos } of the last submission, to avoid re-sending while positions catch up */
  private sent = new Map<string, { t: number; pos: number }>();
  /** symbol -> until when it is left alone after the exchange said "Trading halted" / "not found" (no retries into a wall) */
  private halted = new Map<string, number>();
  private tabSwitchAt = 0;
  /** phase key (event:phase) at which resting orders were last cancelled, so cancel-all runs once per boundary */
  private cancelledAt: string | null = null;
  /** HTTP 429 back-off */
  backoffUntil = 0;
  last: StepResult = { action: 'idle', detail: 'not started' };

  constructor(private deps: AutopilotDeps) {}

  private get cfg(): Config {
    return this.deps.store.cfg;
  }
  private now(): number {
    return this.deps.now ? this.deps.now() : Date.now();
  }

  /** What the queue should be working on right now, or null. */
  mode(): 'edge' | 'flatten' | null {
    const d = this.deps.store.d;
    const ph = d.phase?.phase;
    if (!d.autoArmed) return null;
    if (ph === 'NEWS' || ph === 'UNDERLYING_MOVED') return 'edge';
    // after the snap, and in the open minutes before a day's first news, work the book back to flat: a position carried
    // past a close (the snap-to-close window is 30 real seconds) would otherwise sit through the next event un-hedged
    if (ph === 'SNAPPED' || ph === 'WAITING') return 'flatten';
    return null;
  }

  private positionOf(sym: string): number {
    const s = this.deps.store.s;
    return (s.manualPositions ?? s.positions)[sym] ?? 0;
  }

  /** tickets the trader skipped (confirmEach), per event: symbol:side:source -> event number */
  private skipped = new Map<string, number | null>();
  private eventN(): number | null {
    return this.deps.store.d.phase?.event?.n ?? null;
  }
  private clearPending(): void {
    const store = this.deps.store;
    if (store.s.auto.pending) {
      store.s.auto.pending = null;
      store.changed(true);
    }
  }
  /** confirmEach: the trader pressed Send on the proposed order */
  async confirmPending(): Promise<StepResult | null> {
    const store = this.deps.store;
    const p = store.s.auto.pending;
    if (!p) return null;
    if (this.busy) return { action: 'idle', detail: 'busy; press again' };
    this.busy = true;
    try {
      store.s.auto.pending = null;
      store.changed(true);
      const t = p.ticket;
      const now = this.now();
      const c = store.d.contracts[t.symbol];
      const fair = t.source === 'edge' ? store.d.edges[t.underlying]?.find((r) => r.contract.symbol === t.symbol)?.fair ?? null : null;
      if (!ticketStillValid(t, c, fair, 0)) {
        store.toast(`${t.side} ${t.qty} ${t.symbol}: the touch moved; not sent (the next proposal follows)`, 'warn');
        this.last = { action: 'skipped', detail: `${t.side} ${t.qty} ${t.symbol}: the touch moved`, ticket: t };
        return this.last;
      }
      this.last = await this.send(t, now);
      return this.last;
    } finally {
      this.busy = false;
    }
  }
  /** confirmEach: the trader pressed Skip; that contract/side is not proposed again this event */
  skipPending(): void {
    const store = this.deps.store;
    const p = store.s.auto.pending;
    if (!p) return;
    this.skipped.set(`${p.ticket.symbol}:${p.ticket.side}:${p.ticket.source}`, this.eventN());
    store.s.auto.pending = null;
    store.toast(`skipped ${p.ticket.side} ${p.ticket.qty} ${p.ticket.symbol} for this event`, 'info');
    store.changed(true);
  }

  private excluded(t: Ticket): boolean {
    if (this.skipped.size && this.skipped.get(`${t.symbol}:${t.side}:${t.source}`) === this.eventN()) return true;
    const h = this.halted.get(t.symbol);
    if (h != null) {
      if (this.now() < h) return true;
      this.halted.delete(t.symbol);
    }
    const k = `${t.symbol}:${t.side}`;
    const e = this.sent.get(k);
    if (!e) return false;
    // flatten tickets are re-sized from the position (less same-side resting orders) on every recompute, so they may be
    // re-sent sooner than edge tickets: the snap-to-next-news window is 30 s
    const window = t.source === 'flatten' ? Math.min(this.cfg.auto.resubmitAfterMs, this.cfg.auto.flattenResubmitMs ?? this.cfg.auto.resubmitAfterMs) : this.cfg.auto.resubmitAfterMs;
    if (this.now() - e.t > window) return false;
    // the position moved since we sent: the exchange has processed it, a new ticket is a new decision
    return this.positionOf(t.symbol) === e.pos;
  }

  /** One iteration; safe to call on a timer. Never throws. */
  async step(): Promise<StepResult> {
    if (this.busy) return this.last;
    this.busy = true;
    try {
      this.last = await this.run();
      return this.last;
    } catch (e) {
      this.last = { action: 'skipped', detail: `error: ${e instanceof Error ? e.message : String(e)}` };
      return this.last;
    } finally {
      this.busy = false;
    }
  }

  private async run(): Promise<StepResult> {
    const store = this.deps.store;
    const mode = this.mode();
    if (!mode) {
      this.clearPending();
      return { action: 'idle', detail: store.d.autoArmed ? `phase ${store.d.phase?.phase ?? '—'}: nothing to do` : 'auto-submit off or paused' };
    }
    const now = this.now();
    const cancelled = await this.cancelAtBoundary(now);
    if (cancelled) return cancelled;
    const interval = mode === 'flatten' ? Math.min(this.cfg.auto.submitIntervalMs, this.cfg.auto.flattenIntervalMs ?? this.cfg.auto.submitIntervalMs) : this.cfg.auto.submitIntervalMs;
    if (now - store.s.auto.lastSubmitAt < interval) return { action: 'idle', detail: 'spacing submissions' };
    const rate = store.rate.count(now);
    if (!(rate < this.cfg.auto.submitRateCap)) return { action: 'idle', detail: `rate budget ${rate}/${this.cfg.auto.submitRateCap}` };
    if (store.d.quoteAge == null || store.d.quoteAge > this.cfg.thresholds.staleQuoteSec) return { action: 'idle', detail: 'quotes stale' };
    if (mode === 'edge' && !store.d.targetsConfirmed && !Object.entries(store.d.confirmedUnderlyings).some(([u, ok]) => ok && store.s.targets[u])) {
      return { action: 'idle', detail: 'targets not confirmed' };
    }

    // keep `flattenReserve` orders of the rolling minute for closing tickets: an edge ticket that leaves no budget to
    // flatten after the snap is a position carried into the next event
    const edgeCap = this.cfg.auto.submitRateCap - (this.cfg.auto.flattenReserve ?? 0);
    const edgeBlocked = (x: Ticket) => x.source !== 'flatten' && rate >= edgeCap;
    let t = store.pickNext(mode, { quiet: true, exclude: (x) => this.excluded(x) || !x.withinRateBudget || edgeBlocked(x) });
    // during an event with a risk cap breached (a book carried in from the last event), nothing clears the edge filter
    // because every ticket that adds risk is red: work the risk-reducing flatten tickets instead of sitting idle
    if (!t && mode === 'edge' && store.d.breaches.length) {
      t = store.pickNext('flatten', { quiet: true, exclude: (x) => this.excluded(x) || !x.withinRateBudget });
      if (t) t = { ...t, reason: `${t.reason} · cap breached: reducing risk during the event` };
    }
    if (!t) this.clearPending();
    if (!t) return { action: 'idle', detail: mode === 'edge' ? (rate >= edgeCap ? `edge budget used (${rate}/${edgeCap}; ${this.cfg.auto.flattenReserve} kept for the flatten)` : 'no ticket clears the edge threshold') : 'flat' };
    const c = store.d.contracts[t.symbol];
    const fair = t.source === 'edge' ? store.d.edges[t.underlying]?.find((r) => r.contract.symbol === t.symbol)?.fair ?? null : null;
    if (!ticketStillValid(t, c, fair, 0)) {
      this.sent.set(`${t.symbol}:${t.side}`, { t: now, pos: this.positionOf(t.symbol) }); // skip it this cycle
      if (store.s.auto.pending?.ticket.symbol === t.symbol && store.s.auto.pending.ticket.side === t.side) this.clearPending();
      return { action: 'skipped', detail: `${t.side} ${t.qty} ${t.symbol}: the touch moved`, ticket: t };
    }

    // confirmEach: propose instead of sending; the proposal follows the plan (price/qty refresh, a new best ticket replaces it)
    if (this.cfg.auto.confirmEach) {
      const p = store.s.auto.pending;
      if (p && p.ticket.symbol === t.symbol && p.ticket.side === t.side) {
        if (p.ticket.price !== t.price || p.ticket.qty !== t.qty) {
          p.ticket = t;
          store.changed(true);
        }
        return { action: 'idle', detail: `awaiting your OK: ${t.side} ${t.qty} ${t.symbol} @ ${t.price} (Alt+Y send, Alt+X skip)`, ticket: t };
      }
      store.s.auto.pending = { ticket: t, since: now, mode: t.source === 'flatten' ? 'flatten' : 'edge' };
      store.changed(true);
      return { action: 'idle', detail: `asking: ${t.side} ${t.qty} ${t.symbol} @ ${t.price}`, ticket: t };
    }
    return this.send(t, now);
  }

  /** send a ticket the auto-pilot (or, with confirmEach, the trader) decided on: API POST or the page form */
  private async send(t: Ticket, now: number): Promise<StepResult> {
    const store = this.deps.store;
    if (this.cfg.auto.submitVia === 'api' && this.deps.api) return this.submitViaApi(t, now);

    const r = await this.deps.prefill(t);
    if (!r.ok) {
      if (r.step === 'chain' && /switch the product tab/i.test(r.message) && this.cfg.auto.switchTabs && now - this.tabSwitchAt > 1500) {
        const tab = this.deps.findTab?.(t.underlying) ?? null;
        if (tab && safeTabClick(tab, this.cfg.underlyings, store.d.autoArmed)) {
          this.tabSwitchAt = now;
          store.markLoaded(t, null, `switched the product tab to ${t.underlying}; retrying`);
          return { action: 'tab-switched', detail: t.underlying, ticket: t };
        }
        store.markLoaded(t, false, `${r.message} (no ${t.underlying} tab found: switch it by hand)`);
        return { action: 'prefill-failed', detail: r.message, ticket: t };
      }
      store.markLoaded(t, false, r.message);
      return { action: 'prefill-failed', detail: r.message, ticket: t };
    }

    // re-read the form and let the guard decide
    const panel: OrderPanel | null = findOrderPanel(this.deps.doc, this.cfg.dom, this.deps.symbolRe(), this.deps.skip);
    const form = {
      symbol: panel?.symbol ?? null,
      qty: panel?.qtyInput?.value ?? null,
      price: panel?.priceInput?.value ?? null,
      submitText: panel?.submit ? textOf(panel.submit) : '',
    };
    const res = safeSubmit(panel?.submit ?? null, {
      armed: store.d.autoArmed, ticket: { symbol: t.symbol, side: t.side, qty: t.qty, price: t.price }, form,
      rateUsed: store.rate.count(this.now()), rateCap: this.cfg.auto.submitRateCap,
    });
    if (!res.ok) {
      store.markLoaded(t, false, `auto-submit refused: ${res.reason}`);
      return { action: 'refused', detail: res.reason, ticket: t };
    }
    this.sent.set(`${t.symbol}:${t.side}`, { t: this.now(), pos: this.positionOf(t.symbol) });
    store.logAutoSubmit(t, 'clicked');
    store.markLoaded(t, true, `AUTO: submitted ${t.side} ${t.qty} ${t.symbol} @ ${t.price}`);
    return { action: 'submitted', detail: `${t.side} ${t.qty} ${t.symbol} @ ${t.price}`, ticket: t };
  }

  /** POST the ticket as the Buy/Sell button would. The guard decides; the request and the exchange's answer go through the
   *  store's bridge so the rate meter, the Capture tab and the auto log see them exactly like the page's own orders. */
  private async submitViaApi(t: Ticket, now: number): Promise<StepResult> {
    const store = this.deps.store;
    const api = this.deps.api as ExchangeApi;
    const th = this.cfg.thresholds;
    const pos = this.positionOf(t.symbol);
    const resting = store.s.resting[t.symbol];
    const sameSide = t.side === 'BUY' ? resting?.buy ?? 0 : resting?.sell ?? 0;
    const after = t.side === 'BUY' ? pos + sameSide + t.qty : pos - sameSide - t.qty;
    const refusal = apiSubmitRefusal({
      armed: store.d.autoArmed, ticket: { symbol: t.symbol, side: t.side, qty: t.qty, price: t.price }, known: !!store.d.contracts[t.symbol],
      tick: store.d.tick, perTicketCap: store.d.perTicketCap ?? th.perTicketCap, positionLimit: store.d.positionLimit ?? th.positionLimit, positionAfter: after,
      rateUsed: store.rate.count(now), rateCap: this.cfg.auto.submitRateCap, backoffLeftMs: Math.max(0, this.backoffUntil - now),
    });
    if (refusal) {
      store.markLoaded(t, false, `auto-submit refused: ${refusal}`);
      return { action: 'refused', detail: refusal, ticket: t };
    }
    const body: OrderBody = { symbol: t.symbol, side: t.side === 'BUY' ? 'buy' : 'sell', order_type: 'limit', quantity: t.qty, price: t.price };
    const url = (api.base || '') + PATHS.orders;
    this.sent.set(`${t.symbol}:${t.side}`, { t: now, pos });
    store.handleBridge('http-req', { method: 'POST', url, body: JSON.stringify(body), json: body, t: now });
    store.logAutoSubmit(t, 'posted');
    store.markLoaded(t, true, `AUTO: posted ${t.side} ${t.qty} ${t.symbol} @ ${t.price}`);
    const res = await api.post(PATHS.orders, body);
    store.handleBridge('http', { method: 'POST', url, status: res.status, json: res.json, body: res.text, t: res.t });
    if (res.status === 429) {
      this.backoffUntil = this.now() + this.cfg.auto.backoffMs;
      this.deps.onRateLimit?.();
    }
    if (!res.ok) {
      const detail = (res.json && typeof res.json === 'object' && typeof (res.json as { detail?: unknown }).detail === 'string' ? (res.json as { detail: string }).detail : res.text.slice(0, 120)) || `HTTP ${res.status}`;
      // live messages (testnet 2026-10-24): 403 "Trading halted"; 404 "Symbol X not found". Leave that contract alone for a while.
      if (/halted|not found|settled/i.test(detail) || res.status === 404) this.halted.set(t.symbol, this.now() + (this.cfg.auto.haltedPauseMs ?? 30_000));
      store.markLoaded(t, false, `exchange rejected ${t.side} ${t.qty} ${t.symbol}: ${detail}`);
      return { action: 'submitted', detail: `${t.side} ${t.qty} ${t.symbol} @ ${t.price} -> HTTP ${res.status} ${detail}`, ticket: t };
    }
    return { action: 'submitted', detail: `${t.side} ${t.qty} ${t.symbol} @ ${t.price} -> HTTP ${res.status}`, ticket: t };
  }

  /** At the snap (and at the next news) cancel every resting option order per underlying, once per boundary, so the
   *  flatten tickets are sized from the true position and no stale edge order is picked off after the makers move. */
  private async cancelAtBoundary(now: number): Promise<StepResult | null> {
    const store = this.deps.store;
    const api = this.deps.api;
    if (!api || this.cfg.auto.submitVia !== 'api') return null;
    const ph = store.d.phase;
    if (!ph?.event) return null;
    const want = (ph.phase === 'SNAPPED' && this.cfg.auto.cancelOnSnap) || (ph.phase === 'NEWS' && this.cfg.auto.cancelOnNews);
    if (!want) return null;
    const key = `${ph.event.n}:${ph.phase}`;
    if (this.cancelledAt === key) return null;
    // only when something is resting: a cancel-all is an order action against the 40/min budget
    const resting = Object.values(store.s.resting).reduce((a, r) => a + r.buy + r.sell, 0);
    this.cancelledAt = key;
    if (resting <= 0) return null;
    const unds = this.cfg.underlyings.filter((u) => !this.cfg.focus || this.cfg.focus === u);
    const results: string[] = [];
    for (const u of unds) {
      const path = PATHS.cancelAll(u);
      const url = (api.base || '') + path;
      store.handleBridge('http-req', { method: 'DELETE', url, body: null, t: now });
      const res = await api.del(path);
      store.handleBridge('http', { method: 'DELETE', url, status: res.status, json: res.json, body: res.text, t: res.t });
      // live shape (testnet 2026-10-24): {message: "No open orders", cancelled_count: 0}
      const jo = res.json && typeof res.json === 'object' ? (res.json as { cancelled_count?: unknown; cancelled?: unknown }) : null;
      const n = jo ? jo.cancelled_count ?? jo.cancelled : undefined;
      results.push(`${u}: HTTP ${res.status}${typeof n === 'number' ? ` (${n} cancelled)` : ''}`);
    }
    store.capture.add({ t: now, key: 'auto:cancel-all', dir: 'meta', raw: `${key} ${results.join(', ')}`, highlights: [] });
    store.toast(`cancelled resting orders at ${ph.phase}: ${results.join(', ')}`, 'info');
    return { action: 'cancelled', detail: `${key}: ${results.join(', ')}` };
  }
}
