import { describe, expect, it } from 'vitest';
import { convertToSigma, ConverterId, sigmaToQuantity } from '../../src/engine/converters';
import { compileExpr, evaluate } from '../../src/engine/safeExpr';

const ctx = { S: 100, T: 15 / 252, strikes: [60, 100, 140] };

describe('Round 3 converters round-trip', () => {
  const ids: [ConverterId, number, object?][] = [
    ['variance', 1e-6], ['dailyMoveAbs', 1e-6], ['dailyMovePct', 1e-6], ['expiryMovePct', 1e-6], ['atmStraddle', 1e-6],
    ['callPrice', 1e-6, { K: 110 }], ['putPrice', 1e-6, { K: 90 }], ['vegaPerPoint', 1e-5, { K: 100 }],
    ['probItmCall', 1e-5, { K: 110 }], ['probItmPut', 1e-5, { K: 90 }], ['probItmCall', 1e-5, { K: 95 }],
  ];
  for (const [id, tol, extra] of ids) {
    it(`${id} ${extra ? JSON.stringify(extra) : ''}`, () => {
      for (const sigma of [0.2, 0.45, 0.8, 1.2]) {
        const c = { ...ctx, ...(extra ?? {}), prior: sigma };
        const q = sigmaToQuantity(id, sigma, c) as number;
        const back = convertToSigma(id, q, c).sigma as number;
        expect(Math.abs(back - sigma), `${id} sigma=${sigma}`).toBeLessThan(tol);
      }
    });
  }
  it('variance units: decimal vs %² (auto)', () => {
    expect(convertToSigma('variance', 0.36, ctx).sigma).toBeCloseTo(0.6, 12);
    expect(convertToSigma('variance', 3600, ctx).sigma).toBeCloseTo(0.6, 12);
    expect(convertToSigma('variance', 36, { ...ctx, varianceUnit: 'pct2' }).sigma).toBeCloseTo(0.06, 12);
  });
  it('ATM straddle shows the 0.8 approximation too', () => {
    const r = convertToSigma('atmStraddle', 10, ctx);
    expect(r.approx as number).toBeCloseTo(10 / (0.8 * 100 * Math.sqrt(ctx.T)), 12);
    expect(Math.abs((r.sigma as number) - (r.approx as number))).toBeLessThan(0.02);
  });
  it('P(ITM) without a solution returns null', () => {
    expect(convertToSigma('probItmCall', 0.9, { ...ctx, K: 140 }).sigma).toBeNull();
    expect(convertToSigma('probItmCall', 1.5, { ...ctx, K: 100 }).sigma).toBeNull();
  });
  it('custom formula', () => {
    expect(convertToSigma('custom', 0.25, { ...ctx, formula: 'sqrt(x)' }).sigma).toBeCloseTo(0.5, 12);
    expect(convertToSigma('custom', 2, { ...ctx, formula: 'x/100*sqrt(252)' }).sigma).toBeCloseTo(0.02 * Math.sqrt(252), 12);
    expect(convertToSigma('custom', 2, { ...ctx, formula: 'alert(1)' }).sigma).toBeNull();
  });
});

describe('safe expression evaluator', () => {
  it('does math', () => {
    expect(evaluate('1 + 2 * 3', {})).toBe(7);
    expect(evaluate('(1 + 2) * 3', {})).toBe(9);
    expect(evaluate('2 ^ 3 ^ 2', {})).toBe(512);
    expect(evaluate('-2 ^ 2', {})).toBe(-4);
    expect(evaluate('sqrt(x) * S / K', { x: 4, S: 100, K: 50 })).toBe(4);
    expect(evaluate('ln(exp(1))', {})).toBeCloseTo(1, 15);
    expect(evaluate('log(1000)', {})).toBeCloseTo(3, 15);
    expect(evaluate('max(1, 5, 3) - min(2, -1) + abs(-2)', {})).toBe(8);
    expect(evaluate('normcdf(0)', {})).toBeCloseTo(0.5, 15);
    expect(evaluate('norminv(0.975)', {})).toBeCloseTo(1.959963984540054, 9);
    expect(evaluate('x / sqrt(T)', { x: 0.1, T: 0.25 })).toBeCloseTo(0.2, 15);
    expect(evaluate('pi', {})).toBeCloseTo(Math.PI, 15);
    expect(evaluate('1e-2 * 3', {})).toBeCloseTo(0.03, 15);
  });
  it('rejects identifiers, property access and injection', () => {
    for (const bad of ['constructor', 'alert(1)', 'x.constructor', 'this', 'window', 'S["constructor"]', 'Function("return 1")()', 'sqrt', '1 +', '(1', '1;2', 'x = 1', '__proto__', 'toString()', 'process.exit()', '`1`']) {
      expect(compileExpr(bad).ok, bad).toBe(false);
    }
    expect(() => evaluate('x + 1', {})).toThrow();
  });
});
