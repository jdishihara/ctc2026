// Multi-leg structures: synthetic forwards (vega-neutral spot trades) and straddles (vol trades).
import { price, vegaPerPoint, delta as bsDelta } from './blackScholes';
import { Chain, Side } from './chain';
import { Resting, roomFor, sizeAtTouch } from './fairValue';

export interface Leg {
  symbol: string;
  side: Side;
  price: number;
  ratio: number; // units of this leg per structure unit
}

export interface Structure {
  kind: 'synthLong' | 'synthShort' | 'straddleBuy' | 'straddleSell';
  underlying: string;
  strike: number;
  legs: Leg[];
  cost: number; // net debit per unit (negative = credit)
  fair: number; // fair value of what we receive per unit, sign-matched to cost
  edge: number; // per unit
  size: number;
  expectedPnL: number;
  vega: number; // per vol point, per unit (signed for our position)
  delta: number; // per unit
}

export interface StructOpts {
  positionLimit: number;
  perTicketCap: number;
}

function legRoom(sym: string, side: Side, positions: Record<string, number>, resting: Record<string, Resting>, limit: number) {
  return roomFor(side, positions[sym] ?? 0, resting[sym], limit);
}

export function syntheticForwards(
  chain: Chain,
  targetSpot: number,
  T: number,
  vol: number,
  positions: Record<string, number> = {},
  resting: Record<string, Resting> = {},
  opts: StructOpts = { positionLimit: 300, perTicketCap: 300 },
): Structure[] {
  const out: Structure[] = [];
  for (const r of chain.rows) {
    const c = r.call;
    const p = r.put;
    if (!c || !p) continue;
    const K = r.strike;
    const fwd = targetSpot - K;
    const vC = vegaPerPoint(targetSpot, K, vol, T);
    const vP = vegaPerPoint(targetSpot, K, vol, T);
    const dC = bsDelta('C', targetSpot, K, vol, T);
    const dP = bsDelta('P', targetSpot, K, vol, T);
    if (c.ask != null && p.bid != null && c.ask > 0 && p.bid > 0) {
      const cost = c.ask - p.bid;
      const size = Math.min(
        sizeAtTouch(c, 'BUY', opts.perTicketCap), sizeAtTouch(p, 'SELL', opts.perTicketCap),
        legRoom(c.symbol, 'BUY', positions, resting, opts.positionLimit), legRoom(p.symbol, 'SELL', positions, resting, opts.positionLimit),
        opts.perTicketCap,
      );
      const edge = fwd - cost;
      out.push({
        kind: 'synthLong', underlying: chain.underlying, strike: K,
        legs: [{ symbol: c.symbol, side: 'BUY', price: c.ask, ratio: 1 }, { symbol: p.symbol, side: 'SELL', price: p.bid, ratio: 1 }],
        cost, fair: fwd, edge, size, expectedPnL: edge * size, vega: vC - vP, delta: dC - dP,
      });
    }
    if (c.bid != null && p.ask != null && c.bid > 0 && p.ask > 0) {
      const cost = p.ask - c.bid; // debit of (sell C, buy P)
      const size = Math.min(
        sizeAtTouch(c, 'SELL', opts.perTicketCap), sizeAtTouch(p, 'BUY', opts.perTicketCap),
        legRoom(c.symbol, 'SELL', positions, resting, opts.positionLimit), legRoom(p.symbol, 'BUY', positions, resting, opts.positionLimit),
        opts.perTicketCap,
      );
      const edge = c.bid - p.ask - fwd;
      out.push({
        kind: 'synthShort', underlying: chain.underlying, strike: K,
        legs: [{ symbol: c.symbol, side: 'SELL', price: c.bid, ratio: 1 }, { symbol: p.symbol, side: 'BUY', price: p.ask, ratio: 1 }],
        cost, fair: -fwd, edge, size, expectedPnL: edge * size, vega: vP - vC, delta: dP - dC,
      });
    }
  }
  return out.sort((a, b) => b.edge - a.edge);
}

export function straddles(
  chain: Chain,
  targetSpot: number,
  targetVol: number,
  T: number,
  positions: Record<string, number> = {},
  resting: Record<string, Resting> = {},
  opts: StructOpts = { positionLimit: 300, perTicketCap: 300 },
): Structure[] {
  const out: Structure[] = [];
  for (const r of chain.rows) {
    const c = r.call;
    const p = r.put;
    if (!c || !p) continue;
    const K = r.strike;
    const fair = price('C', targetSpot, K, targetVol, T) + price('P', targetSpot, K, targetVol, T);
    const vega = 2 * vegaPerPoint(targetSpot, K, targetVol, T);
    const delta = bsDelta('C', targetSpot, K, targetVol, T) + bsDelta('P', targetSpot, K, targetVol, T);
    if (c.ask != null && p.ask != null && c.ask > 0 && p.ask > 0) {
      const cost = c.ask + p.ask;
      const size = Math.min(
        sizeAtTouch(c, 'BUY', opts.perTicketCap), sizeAtTouch(p, 'BUY', opts.perTicketCap),
        legRoom(c.symbol, 'BUY', positions, resting, opts.positionLimit), legRoom(p.symbol, 'BUY', positions, resting, opts.positionLimit),
        opts.perTicketCap,
      );
      out.push({
        kind: 'straddleBuy', underlying: chain.underlying, strike: K,
        legs: [{ symbol: c.symbol, side: 'BUY', price: c.ask, ratio: 1 }, { symbol: p.symbol, side: 'BUY', price: p.ask, ratio: 1 }],
        cost, fair, edge: fair - cost, size, expectedPnL: (fair - cost) * size, vega, delta,
      });
    }
    if (c.bid != null && p.bid != null && c.bid > 0 && p.bid > 0) {
      const credit = c.bid + p.bid;
      const size = Math.min(
        sizeAtTouch(c, 'SELL', opts.perTicketCap), sizeAtTouch(p, 'SELL', opts.perTicketCap),
        legRoom(c.symbol, 'SELL', positions, resting, opts.positionLimit), legRoom(p.symbol, 'SELL', positions, resting, opts.positionLimit),
        opts.perTicketCap,
      );
      out.push({
        kind: 'straddleSell', underlying: chain.underlying, strike: K,
        legs: [{ symbol: c.symbol, side: 'SELL', price: c.bid, ratio: 1 }, { symbol: p.symbol, side: 'SELL', price: p.bid, ratio: 1 }],
        cost: -credit, fair: -fair, edge: credit - fair, size, expectedPnL: (credit - fair) * size, vega: -vega, delta: -delta,
      });
    }
  }
  return out.sort((a, b) => b.edge - a.edge);
}
