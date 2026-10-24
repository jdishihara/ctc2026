// The exchange's own API as the data and execution path: chain ingestion, pricing parity with the page's calculator,
// the API submit guard, the poller's back-off and the own feed's single subscription frame.
import { describe, expect, it } from 'vitest';
import { ExchangeApi } from '../../src/core/api';
import { cloneDefaults } from '../../src/core/config';
import { OwnFeed } from '../../src/core/feed';
import { ApiPoller } from '../../src/core/poller';
import { getRate, greeks, price, setRate } from '../../src/engine/blackScholes';
import { impliedVol } from '../../src/engine/impliedVol';
import { Store } from '../../src/state/store';
import { apiSubmitRefusal } from '../../src/ticket/guard';

// The trading page's Black-Scholes (function K in the /trading chunk, read 2026-10-24), as the oracle.
function pageBS(kind: 'call' | 'put', spot: number, strike: number, t: number, rate: number, vol: number) {
  const V = (e: number) => 0.5 * (1 + ((e: number) => { const t = Math.abs(e), l = 1 / (1 + 0.3275911 * t); return (e < 0 ? -1 : 1) * (1 - l * (0.254829592 + l * (-0.284496736 + l * (1.421413741 + l * (-1.453152027 + 1.061405429 * l)))) * Math.exp(-t * t)); })(e / Math.SQRT2));
  const s = kind === 'call', o = s ? 1 : -1;
  const c = Math.sqrt(t), u = Math.exp(-rate * t), d = (Math.log(spot / strike) + (rate + 0.5 * vol * vol) * t) / (vol * c), m = d - vol * c, x = Math.exp(-0.5 * d * d) / Math.sqrt(2 * Math.PI);
  const p = o * (spot * V(o * d) - strike * u * V(o * m)), h = s ? V(d) : V(d) - 1, f = -(spot * x * vol) / (2 * c) - o * rate * strike * u * V(o * m);
  return { fair: p, delta: h, gamma: x / (spot * vol * c), vega: spot * x * c / 100, theta: f / 252 };
}

const chainBody = (spot: number, r: number, tDays: number) => ({
  underlying_symbol: 'OIL', current_underlying_price: spot, risk_free_rate: r,
  expiries: [{
    expiry_fictional_time: '2026-06-26T16:00:00', trading_days_to_expiry: tDays,
    rows: [60, 100, 140].map((K) => ({
      strike: K,
      call: { symbol: `OIL_0626_C${K}`, bid: 1 + (140 - K) / 10, ask: 1.1 + (140 - K) / 10, bid_size: 20, ask_size: 30, last: null, settled: false },
      put: { symbol: `OIL_0626_P${K}`, bid: 1 + K / 100, ask: 1.1 + K / 100, bid_size: 10, ask_size: 10, last: null, settled: false },
    })),
  }],
});

describe('pricing matches the exchange calculator with a rate', () => {
  it('fair, delta, gamma, vega and theta agree with the page for r = 0 and r = 4%', () => {
    for (const r of [0, 0.04]) {
      setRate(r);
      for (const [kind, K] of [['C', 100], ['P', 100], ['C', 60], ['P', 140]] as const) {
        const T = 17.5 / 252;
        const mine = greeks(kind, 101.3, K, 0.62, T);
        const ref = pageBS(kind === 'C' ? 'call' : 'put', 101.3, K, T, r, 0.62);
        // the page uses the Abramowitz-Stegun erf (1.5e-7); ours is exact to 1e-15, so agree to 1e-5
        expect(mine.price).toBeCloseTo(ref.fair, 3);
        expect(mine.delta).toBeCloseTo(ref.delta, 6);
        expect(mine.gamma).toBeCloseTo(ref.gamma, 6);
        expect(mine.vegaPerPoint).toBeCloseTo(ref.vega, 6);
        expect(mine.thetaPerDay).toBeCloseTo(ref.theta, 6);
        // implied vol inverts the price under the same rate
        expect(impliedVol(kind, mine.price, 101.3, K, T)).toBeCloseTo(0.62, 6);
      }
    }
    setRate(0);
    expect(getRate()).toBe(0);
    expect(price('C', 100, 100, 0.5, 20 / 252)).toBeCloseTo(pageBS("call", 100, 100, 20 / 252, 0, 0.5).fair, 3);
  });
});

describe('store ingests the chain endpoint', () => {
  it('fills metas, quotes, spot, T and the rate from one response and prices with that rate', () => {
    let now = 1_000_000;
    const st = new Store(cloneDefaults(), () => now);
    st.handleHttp('GET', '/api/v1/competitions/current', { competition_id: 'c1', name: 'Newtonia vs Euleria', state: 'running', fictional_time: '2026-06-01T09:29:00', clock_rate: 52 }, now);
    st.handleHttp('GET', 'https://cornelltradingcompetition.org/api/v1/options/OIL/chain', chainBody(101.25, 0.03, 19.5), now);
    st.changed(true);
    const d = st.d;
    expect(d.mode).toBe('derivatives');
    expect(d.chains.OIL.strikes).toEqual([60, 100, 140]);
    expect(d.contracts['OIL_0626_P140']).toMatchObject({ bid: 2.4, ask: 2.5, bidSize: 10, src: 'REST' });
    expect(d.spot.OIL).toMatchObject({ value: 101.25, src: 'REST' });
    expect(d.T.days).toBeCloseTo(19.5, 9);
    expect(d.T.src).toBe('REST chain');
    expect(d.r).toBe(0.03);
    expect(getRate()).toBe(0.03);
    // a fresher WS quote wins over the chain copy; the chain copy wins again once the socket goes quiet
    now += 500;
    st.handleWsJson({ type: 'quote', symbol: 'OIL_0626_C100', bid: 5, ask: 5.2, bid_size: 1, ask_size: 1 }, now);
    st.handleHttp('GET', '/api/v1/options/OIL/chain', chainBody(101.25, 0.03, 19.5), now);
    expect(st.s.quotes['OIL_0626_C100']).toMatchObject({ bid: 5, src: 'WS' });
    now += 2000;
    st.handleHttp('GET', '/api/v1/options/OIL/chain', chainBody(101.3, 0.03, 19.49), now);
    expect(st.s.quotes['OIL_0626_C100']).toMatchObject({ src: 'REST' });
    st.changed(true);
    expect(st.d.spot.OIL.value).toBe(101.3);
    setRate(0);
  });

  it('positions and open orders in the live shapes; remaining = quantity - filled', () => {
    const st = new Store(cloneDefaults());
    st.handleHttp('GET', '/api/v1/positions?include_zero=true', { positions: [{ symbol: 'OIL_0626_C100', quantity: 40, avg_price: 5 }, { symbol: 'OIL_0626_P100', quantity: 0 }] });
    expect(st.s.positions).toEqual({ OIL_0626_C100: 40, OIL_0626_P100: 0 });
    expect(st.s.positionsSrc).toBe('REST');
    st.handleHttp('GET', '/api/v1/orders/open', { orders: [
      { order_id: 'a', symbol: 'OIL_0626_C100', side: 'buy', order_type: 'limit', quantity: 30, filled_quantity: 10, price: 5, status: 'partial' },
      { order_id: 'b', symbol: 'OIL_0626_C100', side: 'sell', order_type: 'limit', quantity: 7, filled_quantity: 0, price: 6, status: 'pending' },
      { order_id: 'c', symbol: 'OIL_0626_P100', side: 'sell', order_type: 'limit', quantity: 9, filled_quantity: 9, price: 6, status: 'filled' },
    ] });
    expect(st.s.resting['OIL_0626_C100']).toEqual({ buy: 20, sell: 7 });
    expect(st.s.resting['OIL_0626_P100']).toBeUndefined();
  });

  it('symbols in the live shape ({symbols, groups}, option_kind, strike_price, underlying_symbol)', () => {
    const st = new Store({ ...cloneDefaults(), symbolRegex: '^$' }); // the name parser is switched off: fields must carry it
    st.handleHttp('GET', '/api/v1/symbols', { symbols: [
      { symbol: 'OIL', name: 'OIL', symbol_type: 'scheduled' },
      { symbol: 'OILCALL100', symbol_type: 'option', underlying_symbol: 'OIL', option_kind: 'call', strike_price: 100, expiry_fictional_time: '2026-06-26T16:00:00' },
    ], groups: [] });
    expect(st.s.metas.OILCALL100).toMatchObject({ underlying: 'OIL', kind: 'C', strike: 100, expiry: '2026-06-26T16:00:00' });
  });
});

describe('API submit guard', () => {
  const base = { armed: true, ticket: { symbol: 'OIL_0626_C100', side: 'BUY' as const, qty: 20, price: 5.25 }, known: true, tick: 0.01, perTicketCap: 300, positionLimit: 300, positionAfter: 20, rateUsed: 3, rateCap: 36, backoffLeftMs: 0 };
  it('accepts a sane ticket and names the first failing condition otherwise', () => {
    expect(apiSubmitRefusal(base)).toBeNull();
    expect(apiSubmitRefusal({ ...base, armed: false })).toMatch(/off or paused/);
    expect(apiSubmitRefusal({ ...base, backoffLeftMs: 2500 })).toMatch(/429/);
    expect(apiSubmitRefusal({ ...base, rateUsed: 36 })).toMatch(/rate budget/);
    expect(apiSubmitRefusal({ ...base, known: false })).toMatch(/not a contract/);
    expect(apiSubmitRefusal({ ...base, ticket: { ...base.ticket, qty: 301 } })).toMatch(/per-ticket cap/);
    expect(apiSubmitRefusal({ ...base, positionAfter: 301 })).toMatch(/position limit/);
    expect(apiSubmitRefusal({ ...base, ticket: { ...base.ticket, price: 5.255 } })).toMatch(/off the tick/);
    expect(apiSubmitRefusal({ ...base, ticket: { ...base.ticket, qty: 0 } })).toMatch(/positive/);
  });
});

describe('REST poller and own feed', () => {
  it('polls each endpoint at its cadence, backs off on 429 and recovers', async () => {
    let now = 100_000;
    const calls: string[] = [];
    let mode429 = false;
    const api = new ExchangeApi('', async (url) => {
      calls.push(String(url));
      return new Response(mode429 ? '{"detail":"Rate limited"}' : '{"ok":true}', { status: mode429 ? 429 : 200, headers: { 'content-type': 'application/json' } });
    });
    const sunk: { url: string; status?: number }[] = [];
    const cfg = { ...cloneDefaults().api, clockMs: 1000, symbolsMs: 15_000, chainMs: 1000, positionsMs: 1000, ordersMs: 1500, tradesMs: 3000 };
    const p = new ApiPoller({ api, sink: (_k, x) => sunk.push({ url: x.url, status: x.status }), cfg: () => cfg, isDerivatives: () => true, underlyings: () => ['OIL', 'PLANE'], now: () => now });
    await p.tick();
    expect(calls.sort()).toEqual(['/api/v1/competitions/current', '/api/v1/options/OIL/chain', '/api/v1/options/PLANE/chain', '/api/v1/orders/open', '/api/v1/positions?include_zero=true', '/api/v1/symbols', '/api/v1/trades?limit=200'].sort());
    expect(sunk.every((x) => x.status === 200)).toBe(true);
    calls.length = 0;
    now = 100_500;
    await p.tick();
    expect(calls).toEqual([]); // nothing due yet
    now = 101_000;
    await p.tick();
    expect(calls.sort()).toEqual(['/api/v1/competitions/current', '/api/v1/options/OIL/chain', '/api/v1/options/PLANE/chain', '/api/v1/positions?include_zero=true'].sort());
    // 429 on everything: the next due time doubles per endpoint
    mode429 = true;
    calls.length = 0;
    now = 102_000;
    await p.tick();
    expect(calls.length).toBeGreaterThan(0);
    expect(p.status.endpoints['chain:OIL'].backoff).toBe(2);
    calls.length = 0;
    now = 103_000;
    await p.tick();
    expect(calls).not.toContain('/api/v1/options/OIL/chain');
    now = 104_000;
    mode429 = false;
    // the 429 (at 102 s) also started a 10 s calm-down: chain/positions at twice their cadence (and backoff x2): due at 106 s
    await p.tick();
    expect(calls).toEqual([]);
    now = 106_000;
    await p.tick();
    expect(calls).toContain('/api/v1/options/OIL/chain');
    expect(calls).not.toContain('/api/v1/competitions/current'); // no clock/symbols/trades while calming down
    expect(calls).not.toContain('/api/v1/trades?limit=200');
    expect(p.status.endpoints['chain:OIL'].backoff).toBe(1);
    calls.length = 0;
    now = 107_000;
    await p.tick();
    expect(calls).toEqual([]); // calm still doubles the 1 s cadence
    now = 113_000;
    await p.tick();
    expect(calls).toContain('/api/v1/competitions/current'); // calm over (102 + 10 s)
    // the auto-pilot can also report an order POST's 429
    p.noteRateLimit(now);
    calls.length = 0;
    now = 114_500;
    await p.tick();
    expect(calls).not.toContain('/api/v1/competitions/current');
  });

  it('opens one socket, sends exactly one subscribe frame with all symbols, reopens when the set grows', () => {
    let now = 0;
    const sockets: FakeWS[] = [];
    class FakeWS extends EventTarget {
      sent: string[] = [];
      closed: number | null = null;
      constructor(public url: string) {
        super();
        sockets.push(this);
      }
      send(d: string) {
        this.sent.push(d);
      }
      close(code: number) {
        this.closed = code;
      }
    }
    let symbols = ['OIL', 'PLANE', 'OIL_0626_C100'];
    const sunk: string[] = [];
    const f = new OwnFeed({
      url: () => 'wss://x/ws/v1/market-data', symbols: () => symbols, cfg: () => ({ enabled: true, channels: ['quotes', 'trades', 'news'], path: '/ws/v1/market-data' }),
      enabled: () => true, sink: (k) => sunk.push(k), WS: FakeWS as unknown as typeof WebSocket, now: () => now,
    });
    f.tick();
    expect(sockets).toHaveLength(1);
    sockets[0].dispatchEvent(new Event('open'));
    expect(sockets[0].sent).toHaveLength(1);
    expect(JSON.parse(sockets[0].sent[0])).toEqual({ action: 'subscribe', symbols: ['OIL', 'OIL_0626_C100', 'PLANE'], channels: ['quotes', 'trades', 'news'] });
    sockets[0].dispatchEvent(Object.assign(new Event('message'), { data: '{"type":"quote","symbol":"OIL_0626_C100","bid":1,"ask":2}' }));
    expect(sunk).toEqual(['ws-open', 'ws-in']);
    expect(f.status.frames).toBe(1);
    // same symbols: no new socket; more symbols within 10 s: still the same socket; after 10 s: reopened once
    f.tick();
    expect(sockets).toHaveLength(1);
    symbols = [...symbols, 'OIL_0626_P100'];
    now = 5000;
    f.tick();
    expect(sockets).toHaveLength(1);
    now = 11_000;
    f.tick();
    expect(sockets[0].closed).toBe(1000);
    expect(sockets).toHaveLength(2);
    sockets[1].dispatchEvent(new Event('open'));
    expect(JSON.parse(sockets[1].sent[0]).symbols).toHaveLength(4);
    // a frame on the stale socket is ignored
    sockets[0].dispatchEvent(Object.assign(new Event('message'), { data: '{"type":"quote"}' }));
    expect(f.status.frames).toBe(1);
  });
});
