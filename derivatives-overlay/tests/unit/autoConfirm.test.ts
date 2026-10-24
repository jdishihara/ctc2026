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
function news(st: Store, seq: number, headline: string, extra: Record<string, unknown> = {}) {
  st.handleWsJson({ type: 'news', message: { type: 'headline', seq, headline, ...extra } });
}

function setup(opts: { confirm?: boolean; converter?: boolean } = {}) {
  let now = 1_000_000;
  const cfg = cloneDefaults();
  if (opts.confirm != null) cfg.auto.confirm = opts.confirm;
  if (opts.converter != null) cfg.auto.converter = opts.converter;
  const st = new Store(cfg, () => now);
  st.handleHttp('GET', '/api/v1/symbols', Object.entries(strikes).flatMap(([u, ks]) => [u, ...ks.flatMap((K) => [`${u}_0626_C${K}`, `${u}_0626_P${K}`])]));
  const tick = (ms: number) => { now += ms; st.s.lastClockPollAt = now; st.tick(); };
  /** advance the wall clock, then poll the exchange clock at the new time */
  const at = (t: string, advanceMs = 0) => { now += advanceMs; clock(st, t, now); };
  return { st, tick, at };
}

describe('auto-confirm (Round 1: spot and IV in the news)', () => {
  it('complete and sane news is accepted without Alt+A', () => {
    const { st, tick, at } = setup();
    at('2026-06-01T09:29:00');
    quoteAll(st, { OIL: 100, PLANE: 40 }, { OIL: 0.5, PLANE: 0.7 }, 20 / 252);
    tick(100);
    at('2026-06-01T09:30:02');
    tick(100);
    expect(st.d.phase).toMatchObject({ phase: 'NEWS', event: { n: 1, round: 1 } });
    news(st, 1, 'Oiler threatens exports. OIL steady at 100.00; implied vol now 65%. PLANE holds at 40.00, IV 70%.');
    expect(st.s.targets.OIL.spot).toMatchObject({ value: 100, confirmed: true });
    expect(st.s.targets.OIL.vol).toMatchObject({ value: 0.65, confirmed: true });
    expect(st.s.targets.PLANE.vol).toMatchObject({ value: 0.7, confirmed: true });
    expect(st.d.targetsConfirmed).toBe(true);
    expect(st.s.auto.targets.OIL.status).toBe('confirmed');
    expect(st.s.auto.targets.OIL.reason).toMatch(/spot 100.00 .* vol 65.0%/);
    expect(st.s.timeline[1].targets?.OIL.spot).toBe(100);
    expect(st.pickNext('edge')).not.toBeNull();
  });
  it('a headline that lands just before our clock enters NEWS is confirmed at the phase flip, not at the +60 s move', () => {
    const { st, tick, at } = setup();
    at('2026-06-01T09:29:00');
    quoteAll(st, { OIL: 100, PLANE: 40 }, { OIL: 0.5, PLANE: 0.7 }, 20 / 252);
    tick(100);
    at('2026-06-01T09:29:50');
    tick(100);
    expect(st.d.phase?.phase).not.toBe('NEWS');
    // the exchange stamps the message with its event; our interpolated clock is still 2 market seconds short of 09:30
    news(st, 1, 'Oiler threatens exports. OIL steady at 100.00; implied vol now 65%. PLANE holds at 40.00, IV 70%.', { event: 1 });
    expect(st.s.targets.OIL.spot).toMatchObject({ value: 100, confirmed: false, event: 1 });
    expect(st.d.targetsConfirmed).toBe(false);
    at('2026-06-01T09:30:02', 300);
    tick(100);
    expect(st.d.phase).toMatchObject({ phase: 'NEWS', event: { n: 1 } });
    expect(st.s.targets.OIL.spot).toMatchObject({ value: 100, confirmed: true });
    expect(st.s.targets.PLANE.vol).toMatchObject({ value: 0.7, confirmed: true });
    expect(st.d.targetsConfirmed).toBe(true);
    expect(st.s.auto.targets.OIL.status).toBe('confirmed');
  });
  it('incomplete news stays amber with the reason; a later message completes it', () => {
    const { st, tick, at } = setup();
    at('2026-06-01T09:29:00');
    quoteAll(st, { OIL: 100, PLANE: 40 }, { OIL: 0.5, PLANE: 0.7 }, 20 / 252);
    tick(100);
    at('2026-06-01T09:30:02');
    tick(100);
    news(st, 1, 'Oiler threatens exports. OIL steady at 100.00. PLANE holds at 40.00.');
    expect(st.s.targets.OIL.spot.confirmed).toBe(false);
    expect(st.s.auto.targets.OIL).toMatchObject({ status: 'manual', reason: 'waiting for the announced IV' });
    expect(st.d.targetsConfirmed).toBe(false);
    news(st, 2, 'Volatility update: OIL implied vol 65%, PLANE IV 70%.');
    expect(st.s.targets.OIL).toMatchObject({ spot: { value: 100, confirmed: true }, vol: { value: 0.65, confirmed: true } });
    expect(st.d.targetsConfirmed).toBe(true);
  });
  it('a spot far from the live price or a vol outside the bounds is left for the human', () => {
    const { st, tick, at } = setup();
    at('2026-06-01T09:29:00');
    quoteAll(st, { OIL: 100, PLANE: 40 }, { OIL: 0.5, PLANE: 0.7 }, 20 / 252);
    tick(100);
    at('2026-06-01T09:30:02');
    tick(100);
    news(st, 1, 'Typo day. OIL jumps to 8.00; implied vol now 65%. PLANE holds at 40.00, IV 400%.');
    expect(st.s.targets.OIL.spot).toMatchObject({ value: 8, confirmed: false });
    expect(st.s.auto.targets.OIL.status).toBe('manual');
    expect(st.s.auto.targets.OIL.reason).toMatch(/spot 8.00 is 92% from live 100.00 .*bound 40%/);
    expect(st.s.auto.targets.PLANE.reason).toMatch(/vol 400.0% outside 5–300%/);
    expect(st.d.targetsConfirmed).toBe(false);
    st.acceptSuggestions(); // the human can still override
    expect(st.d.targetsConfirmed).toBe(true);
  });
  it('with auto.confirm off nothing changes', () => {
    const { st, tick, at } = setup({ confirm: false });
    at('2026-06-01T09:29:00');
    quoteAll(st, { OIL: 100, PLANE: 40 }, { OIL: 0.5, PLANE: 0.7 }, 20 / 252);
    tick(100);
    at('2026-06-01T09:30:02');
    tick(100);
    news(st, 1, 'OIL steady at 100.00; implied vol now 65%. PLANE holds at 40.00, IV 70%.');
    expect(st.s.targets.OIL.spot.confirmed).toBe(false);
    expect(st.d.targetsConfirmed).toBe(false);
  });
  it('the live spot after the move replaces a confirmed target automatically', () => {
    const { st, tick, at } = setup();
    at('2026-06-01T09:29:00');
    quoteAll(st, { OIL: 100, PLANE: 40 }, { OIL: 0.5, PLANE: 0.7 }, 20 / 252);
    tick(100);
    at('2026-06-01T09:30:02');
    tick(100);
    news(st, 1, 'OIL rises to 104.00; implied vol now 65%. PLANE holds at 40.00, IV 70%.');
    expect(st.s.targets.OIL.spot).toMatchObject({ value: 104, confirmed: true });
    at('2026-06-01T10:22:01', 60_000);
    quoteAll(st, { OIL: 110, PLANE: 40 }, { OIL: 0.5, PLANE: 0.7 }, 20 / 252);
    tick(100);
    expect(st.d.phase?.phase).toBe('UNDERLYING_MOVED');
    expect(st.s.targets.OIL.spot).toMatchObject({ value: 110, confirmed: true, src: 'live after move' });
    expect(st.s.targets.OIL.spot.suggestion).toBeNull();
  });
});

describe('auto-confirm (Round 2: three analysts)', () => {
  it('waits for all three analysts, then accepts the blend', () => {
    const { st, tick, at } = setup();
    at('2026-06-02T09:29:00');
    quoteAll(st, { OIL: 112, PLANE: 37.8 }, { OIL: 0.72, PLANE: 0.66 }, 19 / 252);
    tick(100);
    at('2026-06-02T09:30:02');
    tick(100);
    expect(st.d.phase).toMatchObject({ phase: 'NEWS', event: { n: 4, round: 2 } });
    news(st, 1, 'Oiler hints at a trade deal. OIL falls to 104.00. PLANE rallies to 41.50.');
    expect(st.s.auto.targets.OIL).toMatchObject({ status: 'manual', reason: 'waiting for analysts A1, A2, A3 (0/3)' });
    news(st, 2, 'Analyst 1: OIL vol 63.0%, PLANE vol 66.0%', { type: 'analyst' });
    news(st, 3, 'Analyst 2: OIL vol 55.5%, PLANE vol 58.5%', { type: 'analyst' });
    expect(st.s.targets.OIL.vol.confirmed).toBe(false);
    expect(st.s.auto.targets.OIL.reason).toBe('waiting for analyst A3 (2/3)');
    news(st, 4, 'Analyst 3: OIL vol 47.0%, PLANE vol 70.0%', { type: 'analyst' });
    expect(st.s.targets.OIL.spot).toMatchObject({ value: 104, confirmed: true });
    expect(st.s.targets.OIL.vol.value as number).toBeCloseTo(0.555, 9);
    expect(st.s.targets.OIL.vol.confirmed).toBe(true);
    expect(st.s.targets.PLANE.vol.value as number).toBeCloseTo(0.66, 9);
    expect(st.d.targetsConfirmed).toBe(true);
    expect(st.s.auto.targets.PLANE.status).toBe('confirmed');
  });
});

describe('Round 3: converter auto-identification in the store', () => {
  function r3() {
    const { st, tick, at } = setup();
    at('2026-06-03T09:29:00');
    quoteAll(st, { OIL: 100, PLANE: 40 }, { OIL: 0.7, PLANE: 1.0 }, 18 / 252);
    tick(100);
    at('2026-06-03T09:30:02');
    tick(100);
    expect(st.d.phase).toMatchObject({ phase: 'NEWS', event: { n: 7, round: 3 } });
    expect(st.d.marketIV.OIL as number).toBeCloseTo(0.7, 1);
    news(st, 1, 'Oiler nationalises a refinery. OIL rises to 103.00. PLANE falls to 38.50.');
    return { st, tick };
  }
  it('variance quotes select the variance converter and the blend is then auto-confirmed', () => {
    const { st } = r3();
    st.s.converter.id = 'iv'; // a wrong default must be corrected
    expect(st.s.auto.targets.OIL.reason).toMatch(/Round 3 quantity not identified/);
    news(st, 2, 'Analyst 1: OIL variance 0.5, PLANE variance 1.05', { type: 'analyst' });
    expect(st.s.auto.converter.status).toBe('chosen');
    expect(st.s.converter.id).toBe('variance');
    expect(st.s.analystInputs[7].OIL[1]?.sigma as number).toBeCloseTo(Math.sqrt(0.5), 6);
    news(st, 3, 'Analyst 2: OIL variance 0.49, PLANE variance 1.0', { type: 'analyst' });
    news(st, 4, 'Analyst 3: OIL variance 0.55, PLANE variance 0.9', { type: 'analyst' });
    expect(st.s.targets.OIL.vol.confirmed).toBe(true);
    expect(st.s.targets.OIL.vol.value as number).toBeCloseTo(Math.sqrt(0.5), 6); // median of the three
    expect(st.d.targetsConfirmed).toBe(true);
  });
  it('daily percentage moves select the daily-move converter', () => {
    const { st } = r3();
    news(st, 2, 'Analyst 2: OIL one-day move 4.4%, PLANE one-day move 6.3%', { type: 'analyst' });
    expect(st.s.auto.converter).toMatchObject({ status: 'chosen', id: 'dailyMovePct' });
    expect(st.s.converter.id).toBe('dailyMovePct');
  });
  it('a hand-picked converter switches auto off until re-run', () => {
    const { st } = r3();
    st.setConverter({ id: 'expiryMovePct' });
    expect(st.s.auto.converter.status).toBe('manual');
    news(st, 2, 'Analyst 1: OIL variance 0.49, PLANE variance 1.0', { type: 'analyst' });
    expect(st.s.converter.id).toBe('expiryMovePct');
    st.resetAutoConverter();
    expect(st.s.auto.converter).toMatchObject({ status: 'chosen', id: 'variance' });
    expect(st.s.converter.id).toBe('variance');
  });
  it('an unidentifiable quantity leaves the converter alone and says why', () => {
    const { st } = r3();
    news(st, 2, 'Analyst 1: OIL 1234, PLANE 5678', { type: 'analyst' });
    expect(st.s.auto.converter.status).toBe('idle');
    expect(st.s.auto.converter.reason).toMatch(/nothing within|ambiguous/);
    expect(st.s.converter.id).toBe('variance'); // the default, unchanged
    expect(st.s.targets.OIL.vol.confirmed).toBe(false);
  });
});
