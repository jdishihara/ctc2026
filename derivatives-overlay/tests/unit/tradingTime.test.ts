import { describe, expect, it } from 'vitest';
import { fmtTime, parseNaive, parseNaiveSec, toSec, tradingDaysRemaining } from '../../src/engine/tradingTime';

const at = (s: string) => parseNaiveSec(s) as number;

describe('trading days remaining', () => {
  it('matches the packet', () => {
    expect(tradingDaysRemaining(at('2026-06-01T09:30:00'))).toBeCloseTo(20, 10);
    expect(tradingDaysRemaining(at('2026-06-01T09:30:00')) / 252).toBeCloseTo(0.0793651, 7);
    expect(tradingDaysRemaining(at('2026-06-02T09:30:00'))).toBeCloseTo(19, 10);
    expect(tradingDaysRemaining(at('2026-06-01T12:45:00'))).toBeCloseTo(19.5, 10);
    expect(tradingDaysRemaining(at('2026-06-26T16:00:00'))).toBe(0);
    expect(tradingDaysRemaining(at('2026-06-27T10:00:00'))).toBe(0);
  });
  it('clamps before the open, after the close and over weekends', () => {
    expect(tradingDaysRemaining(at('2026-06-01T08:00:00'))).toBeCloseTo(20, 10);
    expect(tradingDaysRemaining(at('2026-06-01T17:00:00'))).toBeCloseTo(19, 10);
    expect(tradingDaysRemaining(at('2026-06-06T12:00:00'))).toBeCloseTo(15, 10); // Saturday
    expect(tradingDaysRemaining(at('2026-06-26T12:45:00'))).toBeCloseTo(0.5, 10);
  });
  it('parses naive timestamps without timezone conversion', () => {
    const t = parseNaive('1800-05-13T10:15:30') as NonNullable<ReturnType<typeof parseNaive>>;
    expect(t).toMatchObject({ y: 1800, m: 5, d: 13, hh: 10, mm: 15, ss: 30 });
    expect(fmtTime(toSec(t))).toBe('10:15:30');
    expect(parseNaive('2026-10-23T13:03:20.554838')?.ss).toBeCloseTo(20.554838, 6);
    expect(parseNaive('garbage')).toBeNull();
  });
});
