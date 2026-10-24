// Auto-pilot: runs the ticket queue without a human. Each step picks the next ticket (edge tickets during an event,
// flatten tickets after the snap), prefills the form through the same path as Alt+N, re-reads the form, and clicks the
// submit button through safeSubmit(), which refuses unless armed, verified and inside the rate budget.
import { Config } from '../core/config';
import { textOf } from '../core/dom-readers';
import { Ticket, ticketStillValid } from '../engine/tickets';
import { Store } from '../state/store';
import { safeSubmit, safeTabClick } from './guard';
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
  now?: () => number;
}

export interface StepResult {
  action: 'idle' | 'skipped' | 'prefill-failed' | 'tab-switched' | 'refused' | 'submitted';
  detail: string;
  ticket?: Ticket;
}

export class Autopilot {
  private busy = false;
  /** contract:side -> { t, pos } of the last submission, to avoid re-sending while positions catch up */
  private sent = new Map<string, { t: number; pos: number }>();
  private tabSwitchAt = 0;
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

  private excluded(t: Ticket): boolean {
    const k = `${t.symbol}:${t.side}`;
    const e = this.sent.get(k);
    if (!e) return false;
    if (this.now() - e.t > this.cfg.auto.resubmitAfterMs) return false;
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
    if (!mode) return { action: 'idle', detail: store.d.autoArmed ? `phase ${store.d.phase?.phase ?? '—'}: nothing to do` : 'auto-submit off or paused' };
    const now = this.now();
    if (now - store.s.auto.lastSubmitAt < this.cfg.auto.submitIntervalMs) return { action: 'idle', detail: 'spacing submissions' };
    const rate = store.rate.count(now);
    if (!(rate < this.cfg.auto.submitRateCap)) return { action: 'idle', detail: `rate budget ${rate}/${this.cfg.auto.submitRateCap}` };
    if (store.d.quoteAge == null || store.d.quoteAge > this.cfg.thresholds.staleQuoteSec) return { action: 'idle', detail: 'quotes stale' };
    if (mode === 'edge' && !store.d.targetsConfirmed) return { action: 'idle', detail: 'targets not confirmed' };

    const t = store.pickNext(mode, { quiet: true, exclude: (x) => this.excluded(x) || !x.withinRateBudget });
    if (!t) return { action: 'idle', detail: mode === 'edge' ? 'no ticket clears the edge threshold' : 'flat' };
    const c = store.d.contracts[t.symbol];
    const fair = t.source === 'edge' ? store.d.edges[t.underlying]?.find((r) => r.contract.symbol === t.symbol)?.fair ?? null : null;
    if (!ticketStillValid(t, c, fair, 0)) {
      this.sent.set(`${t.symbol}:${t.side}`, { t: now, pos: this.positionOf(t.symbol) }); // skip it this cycle
      return { action: 'skipped', detail: `${t.side} ${t.qty} ${t.symbol}: the touch moved`, ticket: t };
    }

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
}
