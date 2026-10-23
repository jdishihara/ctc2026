import { describe, expect, it } from 'vitest';
import { DEFAULT_SCHEDULE, eventTimeSec, phaseAt, realSecondsToNext } from '../../src/engine/schedule';
import { parseNaiveSec } from '../../src/engine/tradingTime';

const at = (s: string) => parseNaiveSec(s) as number;

describe('schedule phases', () => {
  it('every event: NEWS → UNDERLYING_MOVED → SNAPPED at the right boundaries', () => {
    for (const e of DEFAULT_SCHEDULE) {
      const news = eventTimeSec(e, 'news');
      const move = eventTimeSec(e, 'move');
      const snap = eventTimeSec(e, 'snap');
      expect(phaseAt(news).phase).toBe('NEWS');
      expect(phaseAt(news).event?.n).toBe(e.n);
      expect(phaseAt(move - 1).phase).toBe('NEWS');
      expect(phaseAt(move).phase).toBe('UNDERLYING_MOVED');
      expect(phaseAt(snap - 1).phase).toBe('UNDERLYING_MOVED');
      expect(phaseAt(snap).phase).toBe('SNAPPED');
      expect(phaseAt(snap).event?.n).toBe(e.n);
    }
  });
  it('real-second countdowns: 60/60/30 s at rate 52 (rounds 1-2) and 39 (round 3)', () => {
    for (const e of DEFAULT_SCHEDULE) {
      const rate = e.round === 3 ? 39 : 52;
      const news = eventTimeSec(e, 'news');
      const snap = eventTimeSec(e, 'snap');
      expect(realSecondsToNext(phaseAt(news), rate)).toBeCloseTo(60, 6);
      expect(realSecondsToNext(phaseAt(eventTimeSec(e, 'move')), rate)).toBeCloseTo(60, 6);
      const toNext = realSecondsToNext(phaseAt(snap), rate) as number;
      expect(toNext).toBeCloseTo(30, 6); // next news, or the 16:00 close after the last event of a day
    }
  });
  it('closed before the open, ended after the final day', () => {
    expect(phaseAt(at('2026-06-01T09:00:00')).phase).toBe('CLOSED');
    expect(phaseAt(at('2026-06-01T09:00:00')).nextPhase).toBe('NEWS');
    expect(phaseAt(at('2026-06-01T16:30:00')).phase).toBe('CLOSED');
    expect(phaseAt(at('2026-06-03T16:00:00')).phase).toBe('ENDED');
    expect(phaseAt(at('2026-06-03T15:50:00')).nextPhase).toBe('ENDED');
  });
  it('replay dates match on time of day and set the REPLAY flag', () => {
    const p = phaseAt(at('1800-05-13T10:30:00'));
    expect(p.replay).toBe(true);
    expect(p.phase).toBe('UNDERLYING_MOVED');
    expect(p.event?.n).toBe(1);
    expect(phaseAt(at('1800-05-13T12:00:00')).event?.n).toBe(2);
    expect(phaseAt(at('2026-06-01T10:30:00')).replay).toBe(false);
  });
});
