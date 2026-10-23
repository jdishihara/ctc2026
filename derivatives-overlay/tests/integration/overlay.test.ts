// @vitest-environment jsdom
// Mock page markup + the mock app's own JS, the MAIN-world hooks, a fake exchange (fetch + WebSocket), and the
// overlay itself, all in one jsdom window.
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { cloneDefaults } from '../../src/core/config';
import { price } from '../../src/engine/blackScholes';
import { installHooks } from '../../src/main-world/hooks';
import { OverlayHandle, startOverlay } from '../../src/content/index';
import { loadMockMarkup } from '../helpers/mockPage';

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const T0 = 20 / 252;
const STRIKES: Record<string, number[]> = { OIL: [60, 100, 140], PLANE: [30, 40, 50] };
const und: Record<string, { spot: number; vol: number }> = { OIL: { spot: 100, vol: 0.5 }, PLANE: { spot: 40, vol: 0.7 } };
const options = Object.entries(STRIKES).flatMap(([u, ks]) => ks.flatMap((K) => (['C', 'P'] as const).map((k) => ({ symbol: `${u}_0626_${k}${K}`, u, k, K }))));

// ---- fake exchange ----
const exchange = {
  fictional: '2026-06-01T09:29:50',
  rate: 52,
  orderPosts: 0,
  sockets: [] as FakeWS[],
  sendUnderlying: false,
};

function quoteFrames(): string[] {
  const out: string[] = [];
  for (const o of options) {
    const f = price(o.k, und[o.u].spot, o.K, und[o.u].vol, T0);
    const hs = 0.05 + 0.01 * f;
    const r2 = (x: number) => Math.round(x * 100) / 100;
    out.push(JSON.stringify({ type: 'quote', symbol: o.symbol, bid: Math.max(0.01, r2(f - hs)), ask: Math.max(0.02, r2(f + hs)), bid_size: 40, ask_size: 40, timestamp: '2026-10-23T13:03:20.554930' }));
  }
  if (exchange.sendUnderlying) for (const [u, v] of Object.entries(und)) out.push(JSON.stringify({ type: 'quote', symbol: u, bid: v.spot - 0.01, ask: v.spot + 0.01, bid_size: 10, ask_size: 10, timestamp: '2026-10-23T13:03:20.554930' }));
  return out;
}

class FakeWS extends EventTarget {
  static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;
  readyState = 0;
  sent: string[] = [];
  constructor(public url: string) {
    super();
    exchange.sockets.push(this);
    setTimeout(() => {
      this.readyState = 1;
      this.dispatchEvent(new Event('open'));
    }, 5);
  }
  send(d: string) {
    this.sent.push(d);
    if (this.sent.length === 1) {
      this.emit(JSON.stringify({ type: 'subscription_ack', symbols: JSON.parse(d).symbols, channels: ['news', 'quotes', 'trades'], timestamp: 'x' }));
      for (const q of quoteFrames()) this.emit(q);
    }
  }
  emit(data: string) {
    this.dispatchEvent(Object.assign(new Event('message'), { data }));
  }
  close() {
    this.readyState = 3;
  }
}
const broadcast = (data: string) => exchange.sockets.forEach((s) => s.emit(data));

const json = (o: unknown, status = 200) => new Response(JSON.stringify(o), { status, headers: { 'content-type': 'application/json' } });
async function fakeFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(String(input instanceof Request ? input.url : input), 'http://localhost:5317');
  const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
  const p = url.pathname;
  if (p === '/api/v1/competitions/current') return json({ competition_id: 'it-1', name: 'Newtonia vs Euleria', state: 'running', fictional_time: exchange.fictional, elapsed_active_seconds: 1, clock_rate: exchange.rate });
  if (p === '/api/v1/symbols') return json([...Object.keys(und).map((s) => ({ symbol: s, type: 'underlying' })), ...options.map((o) => ({ symbol: o.symbol, type: 'option', option_type: o.k === 'C' ? 'call' : 'put', strike: o.K, underlying: o.u }))]);
  if (p === '/api/v1/positions') return json(options.map((o) => ({ symbol: o.symbol, quantity: 0 })));
  if (p === '/api/v1/orders/open') return json([]);
  if (p === '/api/v1/trades/market') return json([]);
  if (p === '/api/v1/auth/login') return json({ detail: 'no' }, 401);
  if (p.startsWith('/api/v1/admin')) return json({ detail: 'no' }, 403);
  if (p === '/api/v1/orders' && method === 'POST') {
    exchange.orderPosts++;
    return json({ status: 'filled' });
  }
  return json({ detail: 'not found' }, 404);
}

let h: OverlayHandle;

beforeAll(async () => {
  loadMockMarkup();
  HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement['getContext'];
  const w = window as unknown as Record<string, unknown>;
  w.fetch = fakeFetch;
  w.WebSocket = FakeWS;
  installHooks(window as Window & typeof globalThis);
  // the mock app's own script (an IIFE over the jsdom globals)
  await import('../../mock-exchange/public/app.js');
  await sleep(50);
  const cfg = cloneDefaults();
  h = await startOverlay(window as Window & typeof globalThis, { config: cfg, tickMs: 100 });
  await sleep(1500);
});
afterAll(() => h?.stop());

describe('overlay against the mock page', () => {
  it('detects the case, the clock and populates both chains', () => {
    const d = h.store.d;
    expect(d.mode).toBe('derivatives');
    expect(h.store.s.caseName).toBe('Newtonia vs Euleria');
    expect(d.clockSrc).toBe('REST');
    expect(d.chains.OIL.strikes).toEqual([60, 100, 140]);
    expect(d.chains.PLANE.strikes).toEqual([30, 40, 50]);
    expect(d.chains.OIL.contracts.every((c) => c.bid != null && c.ask != null)).toBe(true);
    expect(h.store.capture.kinds.has('ws:quote')).toBe(true);
    expect(h.store.capture.kinds.has('http:GET /api/v1/competitions/current')).toBe(true);
    expect([...h.store.capture.kinds.keys()].some((k) => k.includes('/auth/') || k.includes('/admin/'))).toBe(false);
    // the page's single subscribe frame went out untouched
    expect(exchange.sockets[0].sent).toHaveLength(1);
  });

  it('spot falls back to parity without an underlying quote, then uses the WS quote, then the DOM', async () => {
    expect(h.store.d.spot.OIL.src).toBe('parity');
    expect(Math.abs((h.store.d.spot.OIL.value as number) - 100)).toBeLessThan(0.1);
    exchange.sendUnderlying = true;
    for (const q of quoteFrames()) broadcast(q);
    await sleep(400);
    expect(h.store.d.spot.OIL.src).toBe('WS');
    expect(h.store.d.spot.OIL.value).toBeCloseTo(100, 6);
    // remove the underlying quote again: the mock page still shows "Spot 100.00" for the OIL chain
    h.store.s.undQuotes = {};
    h.readDom();
    await sleep(250);
    expect(h.store.d.spot.OIL.src).toBe('DOM');
    expect(h.store.d.spot.PLANE.src).toBe('parity');
  });

  it('suggests targets from the headline and ranks the ATM contract first after a vol jump', async () => {
    exchange.fictional = '2026-06-01T09:30:05';
    await sleep(1300); // next clock poll
    expect(h.store.d.phase?.phase).toBe('NEWS');
    expect(h.store.d.phase?.event?.n).toBe(1);
    broadcast(JSON.stringify({ type: 'news', message: { type: 'headline', seq: 501, time: '2026-06-01T09:30:00', headline: 'Oiler threatens exports. OIL steady at 100.00; implied vol now 65%. PLANE holds at 40.00, IV 70%.' } }));
    await sleep(300);
    const t = h.store.s.targets.OIL;
    expect(t.spot.value).toBeCloseTo(100, 6);
    expect(t.vol.value).toBeCloseTo(0.65, 6);
    expect(t.vol.confirmed).toBe(false);
    expect(h.store.d.targetsConfirmed).toBe(false);
    h.store.acceptSuggestions();
    expect(h.store.d.targetsConfirmed).toBe(true);
    const top = h.store.d.plan[0];
    expect(top.symbol).toMatch(/^OIL_0626_[CP]100$/);
    expect(top.side).toBe('BUY');
    // the overlay UI shows it
    await sleep(300);
    expect(h.shadow.textContent).toContain('Ticket queue');
    expect(h.shadow.textContent).toContain(top.symbol);
  });

  it('prefills QTY/PRICE/side on the mock form and the mock submit handler is never invoked', async () => {
    const top = h.store.d.plan[0];
    // start from the other side/type so the prefill has to change them
    ([...document.querySelectorAll('button')].find((b) => b.textContent === 'SELL') as HTMLButtonElement).click();
    ([...document.querySelectorAll('button')].find((b) => b.textContent === 'Market') as HTMLButtonElement).click();
    h.controller.loadNext('edge');
    for (let i = 0; i < 40 && h.store.s.loaded?.ok == null; i++) await sleep(50);
    expect(h.store.s.loaded?.ok, h.store.s.loaded?.message).toBe(true);
    expect(h.store.s.loaded?.message).toMatch(/^Ready: review and click/);
    const qty = document.querySelector('input.qty') as HTMLInputElement;
    const px = document.querySelector('input.price') as HTMLInputElement;
    expect(document.querySelector('.osym')?.textContent).toBe(top.symbol);
    expect(Number(qty.value)).toBe(top.qty);
    expect(Number(px.value)).toBeCloseTo(top.price, 9);
    expect(document.querySelector('.sidebtn.active')?.textContent).toBe('BUY');
    expect(document.querySelector('.typebtn.active')?.textContent).toBe('Limit');
    expect(document.querySelector('button.submit')?.textContent).toBe(`Buy ${top.qty} ${top.symbol}`);
    await sleep(200);
    expect((window as unknown as { __mockSubmitCount: number }).__mockSubmitCount).toBe(0);
    expect(exchange.orderPosts).toBe(0);
  });

  it('with prefill disabled, Alt+N only shows a copyable card', async () => {
    h.controller.patchConfig({ prefillEnabled: false });
    document.body.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyN', key: 'n', altKey: true, bubbles: true }));
    await sleep(50);
    expect(h.store.s.loaded?.ok).toBeNull();
    expect(h.store.s.loaded?.message).toMatch(/Prefill is off/);
    h.controller.patchConfig({ prefillEnabled: true });
    expect(exchange.orderPosts).toBe(0);
  });

  it('a human submit is observed for the rate meter, positions update the risk view', async () => {
    (document.querySelector('button.submit') as HTMLButtonElement).click(); // the human
    await sleep(100);
    expect(exchange.orderPosts).toBe(1);
    expect(h.store.d.rate.used).toBe(1);
    h.store.handleHttp('GET', '/api/v1/positions?include_zero=true', [{ symbol: 'OIL_0626_C100', quantity: 40 }]);
    h.store.changed(true);
    expect(h.store.d.portfolio.perUnderlying.OIL.delta).toBeGreaterThan(10);
    expect(h.store.d.flatten[0]).toMatchObject({ symbol: 'OIL_0626_C100', side: 'SELL', qty: 40 });
  });
});
