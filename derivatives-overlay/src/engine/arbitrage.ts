// Live no-arbitrage and consistency checks on executable (bid/ask) prices.
import { price } from './blackScholes';
import { Chain, Contract, contractIV, median, Side } from './chain';
import { Leg } from './structures';

export type ArbKind = 'parity' | 'box' | 'monotonicity' | 'vertical' | 'convexity' | 'ivOutlier';

export interface ArbFlag {
  kind: ArbKind;
  underlying: string;
  description: string;
  legs: Leg[];
  edgePerUnit: number;
  maxSize: number;
  expectedPnL: number;
  spotDependent: boolean;
  riskless: boolean;
}

export interface ArbOpts {
  eps: number;
  ivOutlierPts: number;
  minVega: number;
  cap: number;
}

export const DEFAULT_ARB_OPTS: ArbOpts = { eps: 0.02, ivOutlierPts: 1.5, minVega: 0.02, cap: 300 };

const has = (x: number | null | undefined): x is number => x != null && Number.isFinite(x) && x > 0;
const touch = (c: Contract, side: Side, cap: number) => {
  const s = side === 'BUY' ? c.askSize : c.bidSize;
  return s != null && s > 0 ? Math.min(s, cap) : cap;
};
const leg = (c: Contract, side: Side, ratio = 1): Leg => ({ symbol: c.symbol, side, price: (side === 'BUY' ? c.ask : c.bid) as number, ratio });
const sizeOf = (legs: Leg[], cs: Contract[], cap: number) =>
  Math.max(0, Math.floor(Math.min(cap, ...legs.map((l, i) => touch(cs[i], l.side, cap) / l.ratio))));

function flag(kind: ArbKind, ch: Chain, description: string, legs: Leg[], cs: Contract[], edge: number, cap: number, spotDependent: boolean, riskless: boolean): ArbFlag {
  const maxSize = sizeOf(legs, cs, cap);
  return { kind, underlying: ch.underlying, description, legs, edgePerUnit: edge, maxSize, expectedPnL: edge * maxSize, spotDependent, riskless };
}

function gcd(a: number, b: number): number {
  a = Math.abs(Math.round(a));
  b = Math.abs(Math.round(b));
  while (b) [a, b] = [b, a % b];
  return a || 1;
}

export function findArbs(ch: Chain, spot: number | null, T: number, opts: ArbOpts = DEFAULT_ARB_OPTS): ArbFlag[] {
  const out: ArbFlag[] = [];
  const { eps, cap } = opts;
  const rows = ch.rows;

  // Put-call parity against the live spot (spot-dependent: the underlying itself is not tradable).
  if (spot != null && spot > 0) {
    for (const r of rows) {
      const c = r.call;
      const p = r.put;
      if (!c || !p) continue;
      const fwd = spot - r.strike;
      if (has(c.ask) && has(p.bid) && c.ask - p.bid < fwd - eps) {
        const legs = [leg(c, 'BUY'), leg(p, 'SELL')];
        out.push(flag('parity', ch, `Buy synthetic K=${r.strike}: costs ${(c.ask - p.bid).toFixed(2)} vs S−K ${fwd.toFixed(2)}`, legs, [c, p], fwd - (c.ask - p.bid), cap, true, false));
      }
      if (has(c.bid) && has(p.ask) && c.bid - p.ask > fwd + eps) {
        const legs = [leg(c, 'SELL'), leg(p, 'BUY')];
        out.push(flag('parity', ch, `Sell synthetic K=${r.strike}: receives ${(c.bid - p.ask).toFixed(2)} vs S−K ${fwd.toFixed(2)}`, legs, [c, p], c.bid - p.ask - fwd, cap, true, false));
      }
    }
  }

  for (let i = 0; i < rows.length; i++) {
    for (let j = i + 1; j < rows.length; j++) {
      const r1 = rows[i];
      const r2 = rows[j];
      const width = r2.strike - r1.strike;
      const c1 = r1.call, c2 = r2.call, p1 = r1.put, p2 = r2.put;
      // Box: long C1, short C2, long P2, short P1 pays exactly K2-K1 at expiry.
      if (c1 && c2 && p1 && p2) {
        if (has(c1.ask) && has(p1.bid) && has(c2.bid) && has(p2.ask)) {
          const cost = c1.ask - p1.bid - c2.bid + p2.ask;
          if (width - cost > eps) {
            const legs = [leg(c1, 'BUY'), leg(p1, 'SELL'), leg(c2, 'SELL'), leg(p2, 'BUY')];
            out.push(flag('box', ch, `Buy box ${r1.strike}/${r2.strike}: cost ${cost.toFixed(2)} < width ${width}`, legs, [c1, p1, c2, p2], width - cost, cap, false, true));
          }
        }
        if (has(c1.bid) && has(p1.ask) && has(c2.ask) && has(p2.bid)) {
          const recv = c1.bid - p1.ask - c2.ask + p2.bid;
          if (recv - width > eps) {
            const legs = [leg(c1, 'SELL'), leg(p1, 'BUY'), leg(c2, 'BUY'), leg(p2, 'SELL')];
            out.push(flag('box', ch, `Sell box ${r1.strike}/${r2.strike}: receive ${recv.toFixed(2)} > width ${width}`, legs, [c1, p1, c2, p2], recv - width, cap, false, true));
          }
        }
      }
      // Monotonicity: C(K1) >= C(K2), P(K2) >= P(K1).
      if (c1 && c2 && has(c1.ask) && has(c2.bid) && c2.bid - c1.ask > eps) {
        out.push(flag('monotonicity', ch, `Call ${r1.strike} ask ${c1.ask} < call ${r2.strike} bid ${c2.bid}`, [leg(c1, 'BUY'), leg(c2, 'SELL')], [c1, c2], c2.bid - c1.ask, cap, false, true));
      }
      if (p1 && p2 && has(p2.ask) && has(p1.bid) && p1.bid - p2.ask > eps) {
        out.push(flag('monotonicity', ch, `Put ${r2.strike} ask ${p2.ask} < put ${r1.strike} bid ${p1.bid}`, [leg(p2, 'BUY'), leg(p1, 'SELL')], [p2, p1], p1.bid - p2.ask, cap, false, true));
      }
      // Vertical spread worth at most the strike width.
      if (c1 && c2 && has(c1.bid) && has(c2.ask) && c1.bid - c2.ask - width > eps) {
        out.push(flag('vertical', ch, `Call spread ${r1.strike}/${r2.strike} bid ${(c1.bid - c2.ask).toFixed(2)} > width ${width}`, [leg(c1, 'SELL'), leg(c2, 'BUY')], [c1, c2], c1.bid - c2.ask - width, cap, false, true));
      }
      if (p1 && p2 && has(p2.bid) && has(p1.ask) && p2.bid - p1.ask - width > eps) {
        out.push(flag('vertical', ch, `Put spread ${r1.strike}/${r2.strike} bid ${(p2.bid - p1.ask).toFixed(2)} > width ${width}`, [leg(p2, 'SELL'), leg(p1, 'BUY')], [p2, p1], p2.bid - p1.ask - width, cap, false, true));
      }
    }
  }

  // Convexity: w1*X(K1) - w2*X(K2) + w3*X(K3) >= 0 with integer weights proportional to strike gaps.
  for (let i = 0; i + 2 < rows.length; i++) {
    for (let j = i + 1; j + 1 < rows.length; j++) {
      for (let k = j + 1; k < rows.length; k++) {
        const [a, b, c] = [rows[i], rows[j], rows[k]];
        let w1 = c.strike - b.strike;
        let w3 = b.strike - a.strike;
        let w2 = c.strike - a.strike;
        // scale to integers (strikes may be fractional)
        const s = 100;
        w1 = Math.round(w1 * s); w2 = Math.round(w2 * s); w3 = Math.round(w3 * s);
        const g = gcd(gcd(w1, w2), w3);
        w1 /= g; w2 /= g; w3 /= g;
        for (const kind of ['C', 'P'] as const) {
          const x1 = kind === 'C' ? a.call : a.put;
          const x2 = kind === 'C' ? b.call : b.put;
          const x3 = kind === 'C' ? c.call : c.put;
          if (!x1 || !x2 || !x3 || !has(x1.ask) || !has(x2.bid) || !has(x3.ask)) continue;
          const cost = w1 * x1.ask - w2 * x2.bid + w3 * x3.ask;
          if (cost < -eps) {
            const legs = [leg(x1, 'BUY', w1), leg(x2, 'SELL', w2), leg(x3, 'BUY', w3)];
            const name = kind === 'C' ? 'Call' : 'Put';
            out.push(flag('convexity', ch, `${name} butterfly ${a.strike}/${b.strike}/${c.strike} (${w1}:-${w2}:${w3}) for a credit of ${(-cost).toFixed(2)}`, legs, [x1, x2, x3], -cost, cap, false, true));
          }
        }
      }
    }
  }

  // Flat-vol outliers (BS assumptions hold, so IV should be flat across strikes).
  if (spot != null && spot > 0 && T > 0) {
    const ivs = ch.contracts.map((c) => ({ c, iv: contractIV(c, spot, T) }));
    const med = median(ivs.filter((x) => x.iv.mid != null && x.iv.vegaAtMid >= opts.minVega).map((x) => x.iv.mid as number));
    if (med != null) {
      for (const { c, iv } of ivs) {
        if (iv.mid == null || iv.vegaAtMid < opts.minVega) continue;
        const dev = (iv.mid - med) * 100;
        if (Math.abs(dev) <= opts.ivOutlierPts) continue;
        const fairAtMed = price(c.kind, spot, c.strike, med, T);
        if (dev > 0 && iv.bid != null && iv.bid > med && has(c.bid)) {
          out.push(flag('ivOutlier', ch, `${c.symbol} rich: mid IV ${(iv.mid * 100).toFixed(1)}% vs median ${(med * 100).toFixed(1)}% → sell`, [leg(c, 'SELL')], [c], c.bid - fairAtMed, cap, true, false));
        } else if (dev < 0 && iv.ask != null && iv.ask < med && has(c.ask)) {
          out.push(flag('ivOutlier', ch, `${c.symbol} cheap: mid IV ${(iv.mid * 100).toFixed(1)}% vs median ${(med * 100).toFixed(1)}% → buy`, [leg(c, 'BUY')], [c], fairAtMed - c.ask, cap, true, false));
        }
      }
    }
  }
  return out.sort((x, y) => Number(y.riskless) - Number(x.riskless) || y.expectedPnL - x.expectedPnL);
}
