// Portfolio greeks at the current targets, cap checks, and the flatten queue.
import { greeks } from './blackScholes';
import { Chain, Contract, mid, Side } from './chain';

export interface Caps {
  maxAbsDeltaPerUnderlying: number;
  maxAbsVegaPts: number;
}

export const DEFAULT_CAPS: Caps = { maxAbsDeltaPerUnderlying: 300, maxAbsVegaPts: 150 };

export interface RiskInputs {
  spot: number;
  vol: number;
}

export interface PosRow {
  symbol: string;
  underlying: string;
  qty: number;
  fair: number;
  mark: number | null;
  delta: number;
  gamma: number;
  vega: number;
  theta: number;
}

export interface Book {
  delta: number;
  gamma: number;
  vega: number;
  theta: number;
  /** $ PnL for a +1 move in spot (first order + gamma) */
  dollarDeltaUp: number;
  dollarDeltaDown: number;
  /** $ PnL for ±5 vol points */
  vega5: number;
  value: number;
}

export interface Portfolio {
  rows: PosRow[];
  perUnderlying: Record<string, Book>;
  total: Book;
}

const emptyBook = (): Book => ({ delta: 0, gamma: 0, vega: 0, theta: 0, dollarDeltaUp: 0, dollarDeltaDown: 0, vega5: 0, value: 0 });

export function contractsBySymbol(chains: Record<string, Chain>): Record<string, Contract> {
  const out: Record<string, Contract> = {};
  for (const ch of Object.values(chains)) for (const c of ch.contracts) out[c.symbol] = c;
  return out;
}

export function portfolio(
  chains: Record<string, Chain>,
  positions: Record<string, number>,
  inputs: Record<string, RiskInputs | undefined>,
  T: number,
  multiplier = 1,
): Portfolio {
  const bySym = contractsBySymbol(chains);
  const rows: PosRow[] = [];
  const perUnderlying: Record<string, Book> = {};
  const total = emptyBook();
  for (const [sym, qty] of Object.entries(positions)) {
    const c = bySym[sym];
    if (!c || !qty) continue;
    const inp = inputs[c.underlying];
    if (!inp || !(inp.spot > 0) || !(inp.vol > 0)) continue;
    const g = greeks(c.kind, inp.spot, c.strike, inp.vol, T);
    const row: PosRow = {
      symbol: sym, underlying: c.underlying, qty, fair: g.price, mark: mid(c),
      delta: g.delta * qty * multiplier, gamma: g.gamma * qty * multiplier, vega: g.vegaPerPoint * qty * multiplier, theta: g.thetaPerDay * qty * multiplier,
    };
    rows.push(row);
    const b = (perUnderlying[c.underlying] ??= emptyBook());
    for (const bk of [b, total]) {
      bk.delta += row.delta;
      bk.gamma += row.gamma;
      bk.vega += row.vega;
      bk.theta += row.theta;
      bk.dollarDeltaUp += row.delta + 0.5 * row.gamma;
      bk.dollarDeltaDown += -row.delta + 0.5 * row.gamma;
      bk.vega5 += row.vega * 5;
      bk.value += g.price * qty * multiplier;
    }
  }
  return { rows, perUnderlying, total };
}

export interface Breach {
  underlying: string;
  what: 'delta' | 'vega';
  value: number;
  cap: number;
}

export function capBreaches(p: Portfolio, caps: Caps): Breach[] {
  const out: Breach[] = [];
  for (const [u, b] of Object.entries(p.perUnderlying)) {
    if (Math.abs(b.delta) > caps.maxAbsDeltaPerUnderlying) out.push({ underlying: u, what: 'delta', value: b.delta, cap: caps.maxAbsDeltaPerUnderlying });
    if (Math.abs(b.vega) > caps.maxAbsVegaPts) out.push({ underlying: u, what: 'vega', value: b.vega, cap: caps.maxAbsVegaPts });
  }
  return out;
}

/** FLATTEN NOW: |delta| or |vega| above `fraction` of the caps on any underlying. */
export function needsFlatten(p: Portfolio, caps: Caps, fraction = 0.1): boolean {
  return Object.values(p.perUnderlying).some(
    (b) => Math.abs(b.delta) > fraction * caps.maxAbsDeltaPerUnderlying || Math.abs(b.vega) > fraction * caps.maxAbsVegaPts,
  );
}

export interface CloseOrder {
  symbol: string;
  underlying: string;
  side: Side;
  qty: number;
  price: number | null;
  spreadCost: number; // $ given up vs mid (or fair when no mid)
  riskScore: number;
  groupId?: string;
  reason: string;
}

export function flattenOrders(
  chains: Record<string, Chain>,
  positions: Record<string, number>,
  inputs: Record<string, RiskInputs | undefined>,
  T: number,
  caps: Caps = DEFAULT_CAPS,
  perTicketCap = 300,
): { orders: CloseOrder[]; totalSpreadCost: number } {
  const p = portfolio(chains, positions, inputs, T);
  const bySym = contractsBySymbol(chains);
  const orders: CloseOrder[] = [];
  // pair synthetic forwards (long C + short P, or the reverse, same strike) so both legs close back to back
  const pairOf: Record<string, string> = {};
  for (const ch of Object.values(chains)) {
    for (const r of ch.rows) {
      if (!r.call || !r.put) continue;
      const qc = positions[r.call.symbol] ?? 0;
      const qp = positions[r.put.symbol] ?? 0;
      if (qc && qp && Math.sign(qc) === -Math.sign(qp)) {
        const gid = `flat-syn-${r.call.symbol}`;
        pairOf[r.call.symbol] = gid;
        pairOf[r.put.symbol] = gid;
      }
    }
  }
  for (const row of p.rows) {
    const c = bySym[row.symbol];
    const side: Side = row.qty > 0 ? 'SELL' : 'BUY';
    const px = side === 'SELL' ? c.bid : c.ask;
    const ref = mid(c) ?? row.fair;
    let remaining = Math.abs(row.qty);
    const b = p.perUnderlying[row.underlying];
    // risk reduction: share of this position's greeks in the direction of the book's exposure, scaled by caps
    const dRed = b && Math.sign(b.delta) === Math.sign(row.delta) ? Math.abs(row.delta) / caps.maxAbsDeltaPerUnderlying : -Math.abs(row.delta) / caps.maxAbsDeltaPerUnderlying;
    const vRed = b && Math.sign(b.vega) === Math.sign(row.vega) ? Math.abs(row.vega) / caps.maxAbsVegaPts : -Math.abs(row.vega) / caps.maxAbsVegaPts;
    while (remaining > 0) {
      const q = Math.min(remaining, perTicketCap);
      remaining -= q;
      orders.push({
        symbol: row.symbol, underlying: row.underlying, side, qty: q, price: px,
        spreadCost: px != null ? Math.abs(ref - px) * q : 0,
        riskScore: (dRed + vRed) * (q / Math.abs(row.qty)),
        groupId: pairOf[row.symbol],
        reason: `close ${row.qty > 0 ? 'long' : 'short'} ${Math.abs(row.qty)} (Δ ${row.delta.toFixed(1)}, vega ${row.vega.toFixed(1)})`,
      });
    }
  }
  // order: highest risk reduction first, keeping paired legs together
  orders.sort((a, b) => b.riskScore - a.riskScore);
  const out: CloseOrder[] = [];
  const used = new Set<CloseOrder>();
  for (const o of orders) {
    if (used.has(o)) continue;
    out.push(o);
    used.add(o);
    if (o.groupId) for (const m of orders) if (!used.has(m) && m.groupId === o.groupId) { out.push(m); used.add(m); }
  }
  return { orders: out, totalSpreadCost: out.reduce((s, o) => s + o.spreadCost, 0) };
}
