import { afterAll, describe, expect, it } from 'vitest';
import { cloneDefaults } from '../../src/core/config';
import { fmtDate, fmtTime } from '../../src/engine/tradingTime';
import { Store } from '../../src/state/store';

const ORIG_TZ = process.env.TZ;
afterAll(() => {
  process.env.TZ = ORIG_TZ;
});

describe('clock interpolation from naive timestamps', () => {
  for (const tz of ['UTC', 'America/New_York', 'Asia/Kolkata']) {
    it(`no timezone drift (TZ=${tz})`, () => {
      process.env.TZ = tz;
      let now = 1_000_000;
      const st = new Store(cloneDefaults(), () => now);
      st.handleHttp('GET', 'https://cornelltradingcompetition.org/api/v1/competitions/current', {
        competition_id: 'x', name: 'Newtonia vs Euleria', state: 'running', fictional_time: '2026-06-01T09:30:00', elapsed_active_seconds: 0, clock_rate: 52.0,
      }, now);
      now += 60_000; // one real minute
      st.s.lastClockPollAt = now; // keep the clock fresh
      const d = st.compute();
      expect(fmtDate(d.simNow as number)).toBe('2026-06-01');
      expect(fmtTime(d.simNow as number)).toBe('10:22:00');
      expect(d.phase?.phase).toBe('UNDERLYING_MOVED');
      expect(d.phase?.event?.n).toBe(1);
      expect(d.realToNext).toBeCloseTo(60, 6);
      expect(d.T.days).toBeCloseTo(20 - 52 / 390, 9);
      expect(d.mode).toBe('derivatives');
    });
  }
  it('stale after 3 s without a poll; DOM clock fallback; paused state does not advance', () => {
    let now = 0;
    const st = new Store(cloneDefaults(), () => now);
    st.handleHttp('GET', '/api/v1/competitions/current', { name: 'x', state: 'paused', fictional_time: '2026-06-02T16:00:00', clock_rate: 52 }, now);
    now = 2000;
    expect(fmtTime(st.compute().simNow as number)).toBe('16:00:00');
    now = 5000;
    expect(st.compute().clockStale).toBe(true);
    st.handleDom({ clockSec: 9 * 3600 + 31 * 60 });
    const d = st.compute();
    expect(d.clockSrc).toBe('DOM');
    expect(fmtTime(d.simNow as number)).toBe('09:31:00');
  });
});
