// Fair value, executable edge, robust edge across a vol band, and the spot/vol decomposition.
import { Greeks, greeks, price } from './blackScholes';
import { Chain, Contract, Side } from './chain';

export interface Target {
  spot: number;
  vol: number;
  volLow: number;
  volHigh: number;
}

export interface Baseline {
  oldSpot: number;
  oldVol: number;
}

export interface Resting {
  buy: number;
  sell: number;
}

export interface EdgeOpts {
  positionLimit: number;
  perTicketCap: number;
  minEdge: number;
  multiplier: number;
  tick: number;
}

export const DEFAULT_EDGE_OPTS: EdgeOpts = { positionLimit: 300, perTicketCap: 300, minEdge: 0.05, multiplier: 1, tick: 0.01 };

export interface EdgeRow {
  contract: Contract;
  fair: number;
  fairLow: number;
  fairHigh: number;
  buyEdge: number | null;
  sellEdge: number | null;
  side: Side | null;
  edge: number; // best edge at the target vol
  robustSide: Side | null;
  robustEdge: number; // min edge over the vol band, best side
  qty: number;
  room: number;
  expectedPnL: number;
  robustPnL: number;
  spotComponent: number | null;
  volComponent: number | null;
  greeks: Greeks;
  edgeTicks: number;
  passes: boolean; // robust edge >= minEdge and qty > 0
}

/** Remaining room toward the position limit in the trade direction, counting same-side resting orders. */
export function roomFor(side: Side, position: number, resting: Resting | undefined, limit: number): number {
  const rb = resting?.buy ?? 0;
  const rs = resting?.sell ?? 0;
  const r = side === 'BUY' ? limit - (position + rb) : limit + (position - rs);
  return Math.max(0, Math.floor(r));
}

export function sizeAtTouch(c: Contract, side: Side, fallback: number): number {
  const s = side === 'BUY' ? c.askSize : c.bidSize;
  return s != null && s > 0 ? s : fallback;
}

export function computeEdges(
  chain: Chain,
  target: Target,
  baseline: Baseline | null,
  T: number,
  positions: Record<string, number>,
  resting: Record<string, Resting>,
  opts: EdgeOpts = DEFAULT_EDGE_OPTS,
): EdgeRow[] {
  const rows: EdgeRow[] = [];
  for (const c of chain.contracts) {
    const K = c.strike;
    const fair = price(c.kind, target.spot, K, target.vol, T);
    const fLo = price(c.kind, target.spot, K, target.volLow, T);
    const fHi = price(c.kind, target.spot, K, target.volHigh, T);
    const fairs = [fLo, fair, fHi];
    const buyEdge = c.ask != null && c.ask > 0 ? fair - c.ask : null;
    const sellEdge = c.bid != null && c.bid > 0 ? c.bid - fair : null;
    const robustBuy = c.ask != null && c.ask > 0 ? Math.min(...fairs) - c.ask : null;
    const robustSell = c.bid != null && c.bid > 0 ? c.bid - Math.max(...fairs) : null;
    let side: Side | null = null;
    let edge = 0;
    if (buyEdge != null && (sellEdge == null || buyEdge >= sellEdge)) {
      side = 'BUY';
      edge = buyEdge;
    } else if (sellEdge != null) {
      side = 'SELL';
      edge = sellEdge;
    }
    let robustSide: Side | null = null;
    let robustEdge = -Infinity;
    if (robustBuy != null && robustBuy > robustEdge) {
      robustSide = 'BUY';
      robustEdge = robustBuy;
    }
    if (robustSell != null && robustSell > robustEdge) {
      robustSide = 'SELL';
      robustEdge = robustSell;
    }
    if (!Number.isFinite(robustEdge)) robustEdge = 0;
    const tradeSide = robustSide ?? side;
    const pos = positions[c.symbol] ?? 0;
    const room = tradeSide ? roomFor(tradeSide, pos, resting[c.symbol], opts.positionLimit) : 0;
    const touch = tradeSide ? sizeAtTouch(c, tradeSide, opts.perTicketCap) : 0;
    const qty = Math.max(0, Math.min(touch, room, opts.perTicketCap));
    let spotComponent: number | null = null;
    let volComponent: number | null = null;
    if (baseline && baseline.oldSpot > 0 && baseline.oldVol > 0) {
      const base = price(c.kind, baseline.oldSpot, K, baseline.oldVol, T);
      const atNewSpot = price(c.kind, target.spot, K, baseline.oldVol, T);
      spotComponent = atNewSpot - base;
      volComponent = fair - atNewSpot;
    }
    rows.push({
      contract: c,
      fair,
      fairLow: Math.min(...fairs),
      fairHigh: Math.max(...fairs),
      buyEdge,
      sellEdge,
      side,
      edge,
      robustSide,
      robustEdge,
      qty,
      room,
      expectedPnL: edge * qty * opts.multiplier,
      robustPnL: Math.max(robustEdge, 0) * qty * opts.multiplier,
      spotComponent,
      volComponent,
      greeks: greeks(c.kind, target.spot, K, target.vol, T),
      edgeTicks: opts.tick > 0 ? edge / opts.tick : 0,
      passes: robustEdge >= opts.minEdge && qty > 0,
    });
  }
  return rows;
}

/** Rank by robust expected PnL, keeping only rows that clear minEdge. */
export function rankRobust(rows: EdgeRow[]): EdgeRow[] {
  return rows.filter((r) => r.passes).sort((a, b) => b.robustPnL - a.robustPnL);
}
