import { describe, expect, it } from 'vitest';
import { cloneDefaults } from '../../src/core/config';
import { price } from '../../src/engine/blackScholes';
import { Store } from '../../src/state/store';

const strikes: Record<string, number[]> = { OIL: [60, 100, 140], PLANE: [30, 40, 50] };

function quoteAll(st: Store, spots: Record<string, number>, vols: Record<string, number>, T: number) {
  for (const [u, ks] of Object.entries(strikes)) {
    st.handleWsJson({ type: 'quote', symbol: u, bid: spots[u] - 0.01, ask: spots[u] + 0.01, bid_size: 5, ask_size: 5 });
    for (const K of ks) {
      for (const k of ['C', 'P'] as const) {
        const f = price(k, spots[u], K, vols[u], T);
        const r = (x: number) => Math.round(x * 100) / 100;
        st.handleWsJson({ type: 'quote', symbol: `${u}_0626_${k}${K}`, bid: Math.max(0.01, r(f - 0.05)), ask: r(f + 0.05), bid_size: 40, ask_size: 40 });
      }
    }
  }
}

function clock(st: Store, t: string, now: number, rate = 52) {
  st.handleHttp('GET', '/api/v1/competitions/current', { competition_id: 'c1', name: 'Newtonia vs Euleria', state: 'running', fictional_time: t, clock_rate: rate }, now);
}

describe('store: case detection', () => {
  it('Hurricane stays capture-only; OIL+PLANE symbols or option quotes switch to derivatives', () => {
    const st = new Store(cloneDefaults(), () => 0);
    st.handleHttp('GET', '/api/v1/competitions/current', { name: 'Hurricane Season', state: 'running', fictional_time: '1800-05-13T10:15:30', clock_rate: 30 }, 0);
    st.handleWsJson({ type: 'quote', symbol: 'AQUA', bid: 27.25, ask: 27.32, bid_size: 38, ask_size: 19 });
    expect(st.compute().mode).toBe('capture-only');
    expect(st.compute().replay).toBe(true);
    st.handleHttp('GET', '/api/v1/symbols', [{ symbol: 'OIL' }, { symbol: 'PLANE' }]);
    expect(st.compute().mode).toBe('derivatives');
    const st2 = new Store(cloneDefaults(), () => 0);
    st2.handleWsJson({ type: 'quote', symbol: 'OIL_0626_C100', bid: 1, ask: 2 });
    expect(st2.compute().mode).toBe('derivatives');
    const st3 = new Store({ ...cloneDefaults(), mode: 'capture-only' }, () => 0);
    st3.handleWsJson({ type: 'quote', symbol: 'OIL_0626_C100', bid: 1, ask: 2 });
    expect(st3.compute().mode).toBe('capture-only');
  });
  it('parses positions and resting orders with the configured field names', () => {
    const st = new Store(cloneDefaults(), () => 0);
    st.handleHttp('GET', '/api/v1/positions?include_zero=true', { positions: [{ symbol: 'OIL_0626_C100', net_quantity: -20 }, { symbol: 'X', position: 3 }] });
    expect(st.s.positions).toEqual({ OIL_0626_C100: -20, X: 3 });
    st.handleHttp('GET', '/api/v1/orders/open?symbol=OIL_0626_C100', [{ symbol: 'OIL_0626_C100', side: 'buy', remaining_quantity: 7, status: 'open' }, { symbol: 'OIL_0626_C100', side: 'sell', quantity: 4 }]);
    expect(st.s.resting.OIL_0626_C100).toEqual({ buy: 7, sell: 4 });
    st.handleHttp('GET', '/api/v1/orders/open?symbol=OIL_0626_C100', []);
    expect(st.s.resting.OIL_0626_C100).toEqual({ buy: 0, sell: 0 });
  });
});

describe('store: one Round 2 event end to end', () => {
  it('baseline at news, analyst suggestions, snap, learning at SNAPPED + 5 s', () => {
    let now = 1_000_000;
    const cfg = cloneDefaults();
    const st = new Store(cfg, () => now);
    st.handleHttp('GET', '/api/v1/symbols', Object.entries(strikes).flatMap(([u, ks]) => [u, ...ks.flatMap((K) => [`${u}_0626_C${K}`, `${u}_0626_P${K}`])]));
    const T4 = 19 / 252;
    // pre-news (day 2 opens at 09:30 with event 4's news; start just before)
    clock(st, '2026-06-02T09:29:00', now);
    quoteAll(st, { OIL: 112, PLANE: 37.8 }, { OIL: 0.72, PLANE: 0.66 }, T4);
    st.tick();
    expect(st.d.phase?.phase).toBe('CLOSED');
    expect(st.d.marketIV.OIL as number).toBeCloseTo(0.72, 2);
    // news
    now += 1200;
    clock(st, '2026-06-02T09:30:02', now);
    st.tick();
    expect(st.d.phase).toMatchObject({ phase: 'NEWS', event: { n: 4, round: 2 } });
    expect(st.s.baselines[4].OIL.oldSpot).toBeCloseTo(112, 6);
    expect(st.s.baselines[4].OIL.oldVol).toBeCloseTo(0.72, 2);
    st.handleWsJson({ type: 'news', message: { type: 'headline', seq: 1, headline: 'Oiler hints at a trade deal. OIL falls to 104.00. PLANE rallies to 41.50.' } });
    st.handleWsJson({ type: 'news', message: { type: 'analyst', seq: 2, headline: 'Analyst 1: OIL vol 63.0%, PLANE vol 66.0%' } });
    st.handleWsJson({ type: 'news', message: { type: 'analyst', seq: 3, headline: 'Analyst 2: OIL vol 55.5%, PLANE vol 58.5%' } });
    st.handleWsJson({ type: 'news', message: { type: 'analyst', seq: 4, headline: 'Analyst 3: OIL vol 47.0%, PLANE vol 70.0%' } });
    st.tick();
    const t = st.s.targets.OIL;
    // spot from the headline plus all three analysts: auto-confirmed (Config auto.confirm)
    expect(t.spot).toMatchObject({ value: 104, confirmed: true });
    expect(t.vol.value as number).toBeCloseTo(0.555, 9); // median
    expect(t.volLow as number).toBeCloseTo(0.47, 9);
    expect(t.volHigh as number).toBeCloseTo(0.63, 9);
    expect(st.d.targetsConfirmed).toBe(true);
    expect(st.s.auto.targets.OIL.status).toBe('confirmed');
    expect(st.pickNext('edge')).not.toBeNull();
    // the underlying moves (+60 real s), then the makers snap (+120 real s) to the true vol 55% / 58%
    now += 60_000;
    clock(st, '2026-06-02T10:22:01', now);
    quoteAll(st, { OIL: 104, PLANE: 41.5 }, { OIL: 0.72, PLANE: 0.66 }, T4);
    st.tick();
    expect(st.d.phase?.phase).toBe('UNDERLYING_MOVED');
    now += 60_000;
    clock(st, '2026-06-02T11:14:01', now);
    quoteAll(st, { OIL: 104, PLANE: 41.5 }, { OIL: 0.55, PLANE: 0.58 }, T4);
    st.tick();
    expect(st.d.phase?.phase).toBe('SNAPPED');
    expect(st.s.ui.tab).toBe('Risk');
    expect(st.s.history).toHaveLength(0);
    now += 5_100;
    st.s.lastClockPollAt = now;
    st.tick();
    expect(st.s.history.map((r) => r.underlying).sort()).toEqual(['OIL', 'PLANE']);
    const oil = st.s.timeline[4];
    expect(oil.trueVol?.OIL as number).toBeCloseTo(0.55, 2);
    expect(oil.analystErrors?.OIL?.[1] as number).toBeCloseTo(0.08, 2);
    expect(Math.abs(oil.analystErrors?.OIL?.[2] as number)).toBeLessThan(0.01);
    // the next event starts from unconfirmed pre-news values
    now += 30_000;
    clock(st, '2026-06-02T11:40:01', now);
    st.tick();
    expect(st.d.phase?.event?.n).toBe(5);
    expect(st.s.targets.OIL.spot.confirmed).toBe(false);
    expect(st.s.targets.OIL.spot.src).toBe('pre-news');
  });
});
