import { describe, expect, it } from 'vitest';
import { delta, gamma, greeks, price, thetaPerDay, vegaPerPoint } from '../../src/engine/blackScholes';
import { impliedVol } from '../../src/engine/impliedVol';
import { normCdf, normInv, normPdf } from '../../src/engine/normal';

const T20 = 20 / 252;

describe('normal distribution', () => {
  it('normCdf matches known values', () => {
    expect(normCdf(0)).toBeCloseTo(0.5, 15);
    expect(normCdf(1)).toBeCloseTo(0.8413447460685429, 13);
    expect(normCdf(-1.96)).toBeCloseTo(0.024997895148220435, 13);
    expect(normCdf(3)).toBeCloseTo(0.9986501019683699, 13);
    expect(normCdf(-8)).toBeCloseTo(6.22096057427178e-16, 20);
    expect(normCdf(40)).toBe(1);
  });
  it('normInv inverts normCdf', () => {
    for (const p of [1e-10, 1e-4, 0.01, 0.2, 0.5, 0.77, 0.975, 0.9999]) expect(normCdf(normInv(p))).toBeCloseTo(p, 12);
    expect(normPdf(0)).toBeCloseTo(0.3989422804014327, 15);
  });
});

describe('Black-Scholes test vectors (exchange Fair tab)', () => {
  it('S=100 K=100 call sigma=100% T=20/252', () => {
    const g = greeks('C', 100, 100, 1.0, T20);
    expect(Math.abs(g.price - 11.2019)).toBeLessThan(0.002);
    expect(Math.abs(g.delta - 0.556)).toBeLessThan(0.0005);
    expect(Math.abs(g.gamma - 0.014)).toBeLessThan(0.0005);
    expect(Math.abs(g.vegaPerPoint - 0.1113)).toBeLessThan(0.0005);
    expect(Math.abs(g.thetaPerDay - -0.2782)).toBeLessThan(0.0005);
  });
  it('IV of 11.2 is 99.98%', () => {
    const iv = impliedVol('C', 11.2, 100, 100, T20) as number;
    expect(Math.abs(iv * 100 - 99.98)).toBeLessThan(0.02);
  });
  it('handles T<=0 and sigma<=0 without NaN', () => {
    expect(price('C', 110, 100, 0.5, 0)).toBe(10);
    expect(price('P', 90, 100, 0, T20)).toBe(10);
    expect(price('C', 90, 100, 0, T20)).toBe(0);
    for (const v of [delta('C', 100, 100, 0, 0), gamma(100, 100, 0, 0), vegaPerPoint(100, 100, 0, 0), thetaPerDay(100, 100, 0.5, 0)]) expect(Number.isNaN(v)).toBe(false);
  });
});

describe('put-call parity', () => {
  it('C - P = S - K for random inputs', () => {
    let seed = 7;
    const r = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let i = 0; i < 2000; i++) {
      const S = 10 + r() * 200;
      const K = 10 + r() * 200;
      const v = 0.01 + r() * 3;
      const T = (1 + r() * 30) / 252;
      expect(Math.abs(price('C', S, K, v, T) - price('P', S, K, v, T) - (S - K))).toBeLessThan(1e-9);
    }
  });
});

describe('implied vol', () => {
  it('round-trips across strikes, vols and maturities', () => {
    for (const K of [60, 80, 100, 120, 140]) {
      for (const v of [0.05, 0.2, 0.5, 1, 1.7, 3]) {
        for (const days of [1, 5, 12, 20]) {
          const T = days / 252;
          for (const kind of ['C', 'P'] as const) {
            const p = price(kind, 100, K, v, T);
            const intr = kind === 'C' ? Math.max(100 - K, 0) : Math.max(K - 100, 0);
            if (p - intr < 1e-6) continue; // no time value left to invert (vol not identifiable)
            const iv = impliedVol(kind, p, 100, K, T);
            expect(iv).not.toBeNull();
            expect(Math.abs(price(kind, 100, K, iv as number, T) - p)).toBeLessThan(1e-8);
          }
        }
      }
    }
  });
  it('returns null outside no-arbitrage bounds', () => {
    expect(impliedVol('C', 9.0, 110, 100, T20)).toBeNull(); // below intrinsic 10
    expect(impliedVol('P', 4.0, 100, 105, T20)).toBeNull(); // below intrinsic 5
    expect(impliedVol('C', 101, 100, 100, T20)).toBeNull(); // above S
    expect(impliedVol('P', 101, 100, 100, T20)).toBeNull(); // above K
  });
});
