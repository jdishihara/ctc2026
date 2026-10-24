import { describe, expect, it } from 'vitest';
import { cloneDefaults } from '../../src/core/config';
import { price } from '../../src/engine/blackScholes';
import { readiness, summarize } from '../../src/state/readiness';
import { Store } from '../../src/state/store';

const strikes: Record<string, number[]> = { OIL: [60, 100, 140], PLANE: [30, 40, 50] };

function quoteAll(st: Store, spots: Record<string, number>, vols: Record<string, number>, T: number, now: number) {
  for (const [u, ks] of Object.entries(strikes)) {
    st.handleWsJson({ type: 'quote', symbol: u, bid: spots[u] - 0.01, ask: spots[u] + 0.01, bid_size: 5, ask_size: 5 }, now);
    for (const K of ks) for (const k of ['C', 'P'] as const) {
      const f = price(k, spots[u], K, vols[u], T);
      st.handleWsJson({ type: 'quote', symbol: `${u}_0626_${k}${K}`, bid: Math.max(0.01, f - 0.05), ask: f + 0.05, bid_size: 40, ask_size: 40 }, now);
    }
  }
}

const byId = (cs: ReturnType<typeof readiness>) => Object.fromEntries(cs.map((c) => [c.id, c]));

describe('readiness checks', () => {
  it('a fresh page is red on case, feed, contracts, quotes, spot, clock and order form, each with a fix', () => {
    const st = new Store(cloneDefaults(), () => 1000);
    const d = st.compute();
    const cs = readiness(st.s, d, st.cfg, 1000, null);
    const m = byId(cs);
    for (const id of ['case', 'feed', 'chain:OIL', 'chain:PLANE', 'quotes', 'spot:OIL', 'spot:PLANE', 'clock']) {
      expect(m[id].status, id).toBe('bad');
      expect(m[id].fix, id).toBeTruthy();
    }
    // the API submit path does not need the page's form: it waits instead of failing; the form path still fails red
    expect(m.form.status).toBe('wait');
    expect(m.api.status).toBe('wait');
    expect(m.submit.status).toBe('warn');
    expect(m.submit.fix).toContain('ONE laptop');
    const cfgForm = { ...cloneDefaults(), auto: { ...cloneDefaults().auto, submitVia: 'form' as const } };
    expect(byId(readiness(st.s, d, cfgForm, 1000, null)).form.status).toBe('bad');
    expect(m.news.status).toBe('wait');
    expect(summarize(cs).worst).toBe('bad');
  });

  it('goes green once quotes, clock, positions, the order form and a parsed headline are seen', () => {
    let now = 1_000_000;
    const st = new Store(cloneDefaults(), () => now);
    st.handleBridge('ws:open', { url: 'wss://x/ws/v1/market-data' });
    st.handleHttp('GET', '/api/v1/symbols', Object.entries(strikes).flatMap(([u, ks]) => [u, ...ks.flatMap((K) => [`${u}_0626_C${K}`, `${u}_0626_P${K}`])]), now);
    st.handleHttp('GET', '/api/v1/competitions/current', { competition_id: 'c1', name: 'Newtonia vs Euleria', state: 'running', fictional_time: '2026-06-01T09:31:00', clock_rate: 52 }, now);
    st.handleHttp('GET', '/api/v1/positions?include_zero=true', [{ symbol: 'OIL_0626_C100', quantity: 0 }], now);
    quoteAll(st, { OIL: 100, PLANE: 40 }, { OIL: 0.5, PLANE: 0.7 }, 20 / 252, now);
    st.s.ws.lastMsgAt = now;
    st.handleWsJson({ type: 'news', message: { seq: 1, type: 'headline', headline: 'OIL jumps to 108.50; implied vol now 65%. PLANE slides to 36.20, IV 85%.' } }, now);
    // the API poller, the chain endpoint for both underlyings, our own feed and an armed auto-pilot
    st.s.api = { polls: 12, errors: 0, lastOkAt: now, backoff: 1, note: '' };
    for (const [u, sp] of [['OIL', 100], ['PLANE', 40]] as const) {
      st.handleHttp('GET', `/api/v1/options/${u}/chain`, { underlying_symbol: u, current_underlying_price: sp, risk_free_rate: 0, expiries: [{ expiry_fictional_time: '2026-06-26T16:00:00', trading_days_to_expiry: 20, rows: strikes[u].map((K) => ({ strike: K, call: { symbol: `${u}_0626_C${K}`, bid: 1, ask: 1.1 }, put: { symbol: `${u}_0626_P${K}`, bid: 1, ask: 1.1 } })) }] }, now);
    }
    st.s.feed = { open: true, frames: 40, lastAt: now, reconnects: 0, symbols: 14, url: 'wss://x/ws/v1/market-data' };
    st.cfg.auto.submit = true;
    const d = st.compute();
    const panel = { found: true, symbol: 'OIL_0626_C100', qty: true, price: true, buy: true, sell: true, limit: true, submit: 'Buy 20 OIL_0626_C100', t: now };
    const cs = readiness(st.s, d, st.cfg, now, panel);
    const m = byId(cs);
    const bad = cs.filter((c) => c.status === 'bad').map((c) => `${c.id}: ${c.detail}`);
    expect(bad).toEqual([]);
    expect(m['chain:OIL'].detail).toContain('6 (strikes 60/100/140)');
    expect(m['spot:OIL'].status).toBe('ok');
    expect(m.clock.status).toBe('ok');
    expect(m.clock.detail).toContain('rate 52');
    expect(m.pos.status).toBe('ok');
    expect(m.form.status).toBe('ok');
    expect(m.news.status).toBe('ok');
    expect(m.news.detail).toContain('OIL spot 108.5 iv 65%');
    expect(m.api.status).toBe('ok');
    expect(m['rest:OIL'].status).toBe('ok');
    expect(m['rest:OIL'].detail).toContain('T 20.00 d');
    expect(m.ownfeed.status).toBe('ok');
    expect(m.submit.status).toBe('ok');
    expect(m.submit.detail).toContain('ARMED');
    expect(m.T.detail).toContain('REST chain');
    expect(summarize(cs).ok).toBeGreaterThanOrEqual(cs.length - 1);

    // a Round 3 clock rate that looks like Rounds 1-2 is flagged, and a missing QTY input names the field
    st.handleHttp('GET', '/api/v1/competitions/current', { competition_id: 'c1', name: 'Newtonia vs Euleria', state: 'running', fictional_time: '2026-06-03T09:31:00', clock_rate: 52 }, now);
    const cs2 = readiness(st.s, st.compute(), st.cfg, now, { ...panel, qty: false });
    const m2 = byId(cs2);
    expect(m2.clock.status).toBe('warn');
    expect(m2.clock.detail).toContain('expected ~39');
    expect(m2.form.status).toBe('warn');
    expect(m2.form.detail).toContain('QTY input');
  });
});
