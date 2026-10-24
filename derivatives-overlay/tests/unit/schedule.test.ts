import { describe, expect, it } from 'vitest';
import { DEFAULT_SCHEDULE, eventTimeSec, phaseAt, realSecondsToNext, rebaseSchedule, withLiveRate } from '../../src/engine/schedule';
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

describe('rebasing onto the exchange dates', () => {
  const rates = { rounds12: 52, round3: 39 };
  const dates = (s: typeof DEFAULT_SCHEDULE) => [...new Set(s.map((e) => e.date))].sort();
  it('a scheduled date needs no rebase', () => {
    expect(rebaseSchedule(DEFAULT_SCHEDULE, at('2026-06-02T10:00:00'), 500, rates)).toBeNull();
  });
  it('day index from the active seconds: 450 s per day at 52/min, 600 s on the 39/min day', () => {
    const d1 = rebaseSchedule(DEFAULT_SCHEDULE, at('2026-08-03T09:35:00'), 10, rates)!;
    expect(dates(d1)).toEqual(['2026-08-03', '2026-08-04', '2026-08-05']);
    const d2 = rebaseSchedule(DEFAULT_SCHEDULE, at('2026-08-04T10:00:00'), 500, rates)!;
    expect(dates(d2)).toEqual(['2026-08-03', '2026-08-04', '2026-08-05']);
    const d3 = rebaseSchedule(DEFAULT_SCHEDULE, at('2026-08-05T11:00:00'), 1000, rates)!;
    expect(dates(d3)).toEqual(['2026-08-03', '2026-08-04', '2026-08-05']);
    expect(d3.map((e) => e.n)).toEqual(DEFAULT_SCHEDULE.map((e) => e.n));
    expect(d3.find((e) => e.n === 7)!.date).toBe('2026-08-05');
    // phases then work on the exchange's dates
    const ph = phaseAt(at('2026-08-04T10:00:00'), d2);
    expect(ph.event?.n).toBe(4);
    expect(ph.phase).toBe('NEWS');
    expect(ph.replay).toBe(false);
  });
  it('weekends are skipped when stepping and an unknown elapsed means day 1', () => {
    const fri = rebaseSchedule(DEFAULT_SCHEDULE, at('2026-08-07T09:31:00'), null, rates)!;
    expect(dates(fri)).toEqual(['2026-08-07', '2026-08-10', '2026-08-11']);
    const mon = rebaseSchedule(DEFAULT_SCHEDULE, at('2026-08-10T09:31:00'), 460, rates)!;
    expect(dates(mon)).toEqual(['2026-08-07', '2026-08-10', '2026-08-11']);
  });
});

describe('live clock rate', () => {
  const rates = { rounds12: 52, round3: 39 };
  const off = { move: 60, snap: 120 };
  it('the packet rate leaves the schedule as it is', () => {
    expect(withLiveRate(DEFAULT_SCHEDULE, 52, '2026-06-01', off, rates)).toBe(DEFAULT_SCHEDULE);
    expect(withLiveRate(DEFAULT_SCHEDULE, 39, '2026-06-03', off, rates)).toBe(DEFAULT_SCHEDULE);
    expect(withLiveRate(DEFAULT_SCHEDULE, 30, '2026-06-09', off, rates)).toBe(DEFAULT_SCHEDULE); // no events that day
  });
  it('a slower exchange moves and snaps earlier in market time: +1/+2 real minutes after the news', () => {
    const s = withLiveRate(DEFAULT_SCHEDULE, 30, '2026-06-01', off, rates);
    const e1 = s.find((e) => e.n === 1)!;
    expect([e1.news, e1.move, e1.snap]).toEqual(['09:30:00', '10:00:00', '10:30:00']);
    expect(s.find((e) => e.n === 4)).toBe(DEFAULT_SCHEDULE.find((e) => e.n === 4)); // other days untouched
    const ph = phaseAt(at('2026-06-01T10:22:00'), s);
    expect(ph.phase).toBe('UNDERLYING_MOVED');
    expect(phaseAt(at('2026-06-01T10:31:00'), s).phase).toBe('SNAPPED');
  });
});
