// Ticket planner: turns edges, structures, arbitrage flags and flatten orders into an ordered queue of
// human-confirmed limit orders. Simulates positions as it goes so the 300 limit (incl. resting) and risk caps hold.
import { delta as bsDelta, vegaPerPoint } from './blackScholes';
import { Contract, roundToTick, Side } from './chain';
import { EdgeRow, Resting } from './fairValue';
import { Caps } from './risk';
import { Structure } from './structures';
import { ArbFlag } from './arbitrage';
import { CloseOrder } from './risk';

export interface Ticket {
  id: string;
  symbol: string;
  underlying: string;
  side: Side;
  type: 'limit';
  qty: number;
  price: number;
  reason: string;
  expectedPnL: number;
  edgePerUnit: number;
  groupId?: string;
  source: 'edge' | 'struct' | 'arb' | 'flatten';
  breach: string[];
  withinRateBudget: boolean;
}

export interface PlanInput {
  edges: EdgeRow[];
  structures?: Structure[];
  contracts: Record<string, Contract>;
  targets: Record<string, { spot: number; vol: number } | undefined>;
  T: number;
  positions: Record<string, number>;
  resting: Record<string, Resting>;
  bookGreeks: Record<string, { delta: number; vega: number } | undefined>;
  caps: Caps;
  positionLimit: number;
  perTicketCap: number;
  minEdge: number;
  rateRemaining: number;
  round: 1 | 2 | 3 | null;
  preferSynthForSpot: boolean;
  priceMode: 'touch' | 'passive';
  tick: number;
  focus: string | null; // underlying filter, null = all
  multiplier?: number;
  edgeThroughFrac?: number;
}

let seq = 0;
const nextId = (p: string) => `${p}-${++seq}`;

function legGreeks(inp: PlanInput, symbol: string, side: Side, qty: number) {
  const c = inp.contracts[symbol];
  const t = c && inp.targets[c.underlying];
  if (!c || !t) return { d: 0, v: 0 };
  const sgn = side === 'BUY' ? 1 : -1;
  return { d: sgn * qty * bsDelta(c.kind, t.spot, c.strike, t.vol, inp.T), v: sgn * qty * vegaPerPoint(t.spot, c.strike, t.vol, inp.T) };
}

function priceFor(inp: PlanInput, c: Contract, side: Side, fair: number | null, through = 0): number | null {
  const touch = side === 'BUY' ? c.ask : c.bid;
  if (touch == null) return null;
  if (through > 0) return roundToTick(side === 'BUY' ? touch + through : Math.max(inp.tick, touch - through), inp.tick, side === 'BUY' ? 'up' : 'down');
  if (inp.priceMode === 'passive' && fair != null) {
    // rest inside the spread, never closer to fair than minEdge
    if (side === 'BUY') {
      const p = Math.min((c.bid ?? touch - inp.tick) + inp.tick, fair - inp.minEdge, touch);
      return roundToTick(p, inp.tick, 'down');
    }
    const p = Math.max((c.ask ?? touch + inp.tick) - inp.tick, fair + inp.minEdge, touch);
    return roundToTick(p, inp.tick, 'up');
  }
  return roundToTick(touch, inp.tick, side === 'BUY' ? 'up' : 'down');
}

export function planTickets(inp: PlanInput): Ticket[] {
  const pos: Record<string, number> = { ...inp.positions };
  const greeksNow: Record<string, { delta: number; vega: number }> = {};
  for (const [u, g] of Object.entries(inp.bookGreeks)) if (g) greeksNow[u] = { ...g };
  const room = (sym: string, side: Side) => {
    const r = inp.resting[sym];
    const p = pos[sym] ?? 0;
    return Math.max(0, side === 'BUY' ? inp.positionLimit - (p + (r?.buy ?? 0)) : inp.positionLimit + (p - (r?.sell ?? 0)));
  };
  const inFocus = (u: string) => !inp.focus || inp.focus === u;
  const mult = inp.multiplier ?? 1;

  type Cand = { pnl: number; legs: { symbol: string; side: Side; ratio: number; fair: number | null; edge: number }[]; size: number; reason: string; source: Ticket['source']; underlying: string };
  const cands: Cand[] = [];

  const synths = (inp.structures ?? []).filter((s) => (s.kind === 'synthLong' || s.kind === 'synthShort') && s.edge >= inp.minEdge && s.size > 0 && inFocus(s.underlying));
  const useSynth = inp.preferSynthForSpot && (inp.round === 2 || inp.round === 3);
  for (const s of useSynth ? synths : []) {
    cands.push({
      pnl: s.edge * s.size * mult, size: s.size, underlying: s.underlying, source: 'struct',
      reason: `${s.kind === 'synthLong' ? 'Buy' : 'Sell'} synthetic K=${s.strike}: edge ${s.edge.toFixed(2)} (vega-neutral spot trade)`,
      legs: s.legs.map((l) => ({ symbol: l.symbol, side: l.side, ratio: l.ratio, fair: null, edge: s.edge / 2 })),
    });
  }
  for (const e of inp.edges) {
    const c = e.contract;
    if (!e.passes || !e.robustSide || !inFocus(c.underlying)) continue;
    // In rounds 2-3, spot-driven single legs are replaced by the vega-neutral synthetic when one exists.
    if (useSynth && e.spotComponent != null && e.volComponent != null && Math.abs(e.spotComponent) > 2 * Math.abs(e.volComponent)) {
      const dirLong = (e.robustSide === 'BUY') === (c.kind === 'C');
      if (synths.some((s) => s.underlying === c.underlying && (s.kind === 'synthLong') === dirLong)) continue;
    }
    cands.push({
      pnl: e.robustEdge * e.qty * mult, size: e.qty, underlying: c.underlying, source: 'edge',
      reason: `${e.robustSide === 'BUY' ? 'Buy' : 'Sell'} ${c.symbol}: fair ${e.fair.toFixed(2)}, robust edge ${e.robustEdge.toFixed(2)}`,
      legs: [{ symbol: c.symbol, side: e.robustSide, ratio: 1, fair: e.fair, edge: e.robustEdge }],
    });
  }
  cands.sort((a, b) => b.pnl - a.pnl);

  const ok: Ticket[] = [];
  const red: Ticket[] = [];
  for (const cand of cands) {
    const thrFrac = inp.edgeThroughFrac ?? 0;
    let size = Math.min(thrFrac > 0 ? inp.perTicketCap : cand.size, inp.perTicketCap, ...cand.legs.map((l) => Math.floor(room(l.symbol, l.side) / l.ratio)));
    if (!(size > 0)) continue;
    const gid = cand.legs.length > 1 ? nextId('grp') : undefined;
    const g = greeksNow[cand.underlying] ?? { delta: 0, vega: 0 };
    let dd = 0;
    let dv = 0;
    for (const l of cand.legs) {
      const lg = legGreeks(inp, l.symbol, l.side, size * l.ratio);
      dd += lg.d;
      dv += lg.v;
    }
    const breach: string[] = [];
    if (Math.abs(g.delta + dd) > inp.caps.maxAbsDeltaPerUnderlying && Math.abs(g.delta + dd) > Math.abs(g.delta)) breach.push(`delta → ${(g.delta + dd).toFixed(0)}`);
    if (Math.abs(g.vega + dv) > inp.caps.maxAbsVegaPts && Math.abs(g.vega + dv) > Math.abs(g.vega)) breach.push(`vega → ${(g.vega + dv).toFixed(0)}`);
    const tickets: Ticket[] = [];
    for (const l of cand.legs) {
      const c = inp.contracts[l.symbol];
      if (!c) continue;
      const px = priceFor(inp, c, l.side, l.fair, thrFrac > 0 ? Math.max(inp.tick, thrFrac * Math.abs(l.edge)) : 0);
      if (px == null) continue;
      tickets.push({
        id: nextId('t'), symbol: l.symbol, underlying: cand.underlying, side: l.side, type: 'limit', qty: size * l.ratio, price: px,
        reason: cand.reason, expectedPnL: cand.pnl * (size / cand.size) / cand.legs.length, edgePerUnit: l.edge,
        groupId: gid, source: cand.source, breach, withinRateBudget: true,
      });
    }
    if (tickets.length !== cand.legs.length) continue;
    if (breach.length) {
      red.push(...tickets);
      continue;
    }
    for (const t of tickets) pos[t.symbol] = (pos[t.symbol] ?? 0) + (t.side === 'BUY' ? t.qty : -t.qty);
    greeksNow[cand.underlying] = { delta: g.delta + dd, vega: g.vega + dv };
    ok.push(...tickets);
    size = 0;
  }
  const all = [...ok, ...red];
  all.forEach((t, i) => (t.withinRateBudget = i < inp.rateRemaining));
  return all;
}

export function ticketsFromArb(f: ArbFlag, contracts: Record<string, Contract>, perTicketCap: number, tick: number): Ticket[] {
  const units = Math.max(0, Math.min(f.maxSize, Math.floor(perTicketCap / Math.max(...f.legs.map((l) => l.ratio)))));
  const gid = nextId('arb');
  return f.legs.map((l) => ({
    id: nextId('t'), symbol: l.symbol, underlying: contracts[l.symbol]?.underlying ?? f.underlying, side: l.side, type: 'limit' as const,
    qty: units * l.ratio, price: roundToTick(l.price, tick, l.side === 'BUY' ? 'up' : 'down'),
    reason: `${f.kind}: ${f.description}`, expectedPnL: (f.edgePerUnit * units) / f.legs.length, edgePerUnit: f.edgePerUnit,
    groupId: f.legs.length > 1 ? gid : undefined, source: 'arb' as const, breach: [], withinRateBudget: true,
  })).filter((t) => t.qty > 0);
}

export function ticketsFromFlatten(orders: CloseOrder[], tick: number, rateRemaining: number, focus: string | null): Ticket[] {
  return orders
    .filter((o) => o.price != null && (!focus || o.underlying === focus))
    .map((o, i) => ({
      id: nextId('t'), symbol: o.symbol, underlying: o.underlying, side: o.side, type: 'limit' as const, qty: o.qty,
      price: roundToTick(o.price as number, tick, o.side === 'BUY' ? 'up' : 'down'), reason: o.reason,
      expectedPnL: -o.spreadCost, edgePerUnit: 0, groupId: o.groupId, source: 'flatten' as const, breach: [], withinRateBudget: i < rateRemaining,
    }));
}

/** Still valid if the touch has not moved through our price and (for edge tickets) fair still beats it. */
export function ticketStillValid(t: Ticket, c: Contract | undefined, fair: number | null, minEdge = 0): boolean {
  if (!c) return false;
  if (t.side === 'BUY') {
    if (c.ask == null || c.ask > t.price + 1e-9) return false;
    return fair == null || t.source === 'flatten' || fair - c.ask >= minEdge - 1e-9;
  }
  if (c.bid == null || c.bid < t.price - 1e-9) return false;
  return fair == null || t.source === 'flatten' || c.bid - fair >= minEdge - 1e-9;
}
