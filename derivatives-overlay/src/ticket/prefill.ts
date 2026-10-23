// Prefill the exchange order form for a ticket. Never submits: the human reviews and clicks Buy/Sell.
import { DomHints } from '../core/config';
import { findChain, textOf } from '../core/dom-readers';
import { Ticket } from '../engine/tickets';
import { GuardConfig, registerChainCell, safeClick } from './guard';
import { findOrderPanel } from './selectors';

export interface PrefillResult {
  ok: boolean;
  step: 'chain' | 'cell' | 'verify' | 'side' | 'type' | 'inputs' | 'done' | 'disabled';
  message: string;
}

export interface PrefillCtx {
  doc: Document;
  hints: DomHints;
  symbolRe: RegExp;
  strikeOf: (symbol: string) => { strike: number; kind: 'C' | 'P' } | null;
  skip?: (el: Element) => boolean; // exclude our own overlay
  verifyMs?: number;
  /** which underlying the visible chain shows (by its strikes), when it can be told */
  visibleUnderlying?: (strikes: number[]) => string | null;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** React-safe value setter: native setter + input/change events. */
export function setInputValue(input: HTMLInputElement, value: string): boolean {
  try {
    const win = input.ownerDocument.defaultView as (Window & typeof globalThis) | null;
    const proto = win?.HTMLInputElement?.prototype ?? HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(input, value);
    else input.value = value;
    const Ev = win?.Event ?? Event;
    input.dispatchEvent(new Ev('input', { bubbles: true }));
    input.dispatchEvent(new Ev('change', { bubbles: true }));
    return true;
  } catch {
    return false;
  }
}

const sameNum = (a: string, b: string) => {
  const x = Number(String(a).replace(/[,$\s]/g, ''));
  const y = Number(String(b).replace(/[,$\s]/g, ''));
  return Number.isFinite(x) && Number.isFinite(y) && Math.abs(x - y) < 1e-9;
};

export function fmtPrice(p: number): string {
  return String(Number(p.toFixed(6)));
}

export async function prefillTicket(t: Ticket, ctx: PrefillCtx): Promise<PrefillResult> {
  const guard: GuardConfig = { toggles: [ctx.hints.buyText, ctx.hints.sellText, ctx.hints.limitText, ctx.hints.marketText] };
  const meta = ctx.strikeOf(t.symbol);
  if (!meta) return { ok: false, step: 'chain', message: `unknown contract ${t.symbol}` };

  // 1. select the contract by clicking its chain price cell (ask for a buy, bid for a sell)
  let panel = findOrderPanel(ctx.doc, ctx.hints, ctx.symbolRe, ctx.skip);
  if (panel?.symbol !== t.symbol) {
    const chain = findChain(ctx.doc, ctx.hints, ctx.skip);
    if (!chain) return { ok: false, step: 'chain', message: 'chain table not found (open the Chain view)' };
    const shown = ctx.visibleUnderlying?.(chain.rows.map((r) => r.strike)) ?? null;
    if (shown && shown !== t.underlying) return { ok: false, step: 'chain', message: `the chain shows ${shown}: switch the product tab to ${t.underlying}, then load again` };
    const row = chain.rows.find((r) => Math.abs(r.strike - meta.strike) < 1e-9);
    if (!row) return { ok: false, step: 'chain', message: `strike ${meta.strike} not in the visible chain; switch the product tab to ${t.underlying}` };
    const cell = t.side === 'BUY' ? row[meta.kind].ask.el : row[meta.kind].bid.el;
    if (!cell) return { ok: false, step: 'cell', message: 'price cell not found' };
    registerChainCell(cell);
    if (!safeClick(cell, 'select contract', guard)) return { ok: false, step: 'cell', message: 'guard refused the chain cell click' };
    const deadline = Date.now() + (ctx.verifyMs ?? 500);
    for (;;) {
      await sleep(25);
      panel = findOrderPanel(ctx.doc, ctx.hints, ctx.symbolRe, ctx.skip);
      if (panel?.symbol === t.symbol) break;
      if (Date.now() > deadline) {
        return { ok: false, step: 'verify', message: `order panel shows ${panel?.symbol ?? 'nothing'}, expected ${t.symbol}; is the ${t.underlying} chain showing?` };
      }
    }
  }
  if (!panel) return { ok: false, step: 'verify', message: 'order panel not found' };

  // 2. side toggle, then Limit
  const sideEl = t.side === 'BUY' ? panel.buy : panel.sell;
  if (!sideEl || !safeClick(sideEl, 'side toggle', guard)) return { ok: false, step: 'side', message: `could not set side ${t.side}: click ${t.side} yourself` };
  await sleep(20);
  panel = findOrderPanel(ctx.doc, ctx.hints, ctx.symbolRe, ctx.skip) ?? panel;
  if (!panel.limit || !safeClick(panel.limit, 'limit toggle', guard)) return { ok: false, step: 'type', message: 'could not select Limit: click it yourself' };
  await sleep(20);
  panel = findOrderPanel(ctx.doc, ctx.hints, ctx.symbolRe, ctx.skip) ?? panel;

  // 3. qty and price via the React-safe setter, then verify
  if (!panel.qtyInput || !panel.priceInput) return { ok: false, step: 'inputs', message: 'QTY/PRICE inputs not found' };
  const qty = String(t.qty);
  const px = fmtPrice(t.price);
  setInputValue(panel.qtyInput, qty);
  setInputValue(panel.priceInput, px);
  await sleep(30);
  panel = findOrderPanel(ctx.doc, ctx.hints, ctx.symbolRe, ctx.skip) ?? panel;
  const qOk = panel.qtyInput && sameNum(panel.qtyInput.value, qty);
  const pOk = panel.priceInput && sameNum(panel.priceInput.value, px);
  if (!qOk || !pOk) {
    return { ok: false, step: 'inputs', message: `verify failed (QTY ${panel.qtyInput?.value ?? '?'} / PRICE ${panel.priceInput?.value ?? '?'})` };
  }
  if (panel.symbol !== t.symbol) return { ok: false, step: 'verify', message: `contract changed to ${panel.symbol}` };

  // 4. highlight the submit button (outline only, never clicked)
  const sub = panel.submit as HTMLElement | null;
  if (sub) {
    try {
      const prev = sub.style.outline;
      sub.style.outline = '3px solid #e8707a';
      sub.style.outlineOffset = '2px';
      setTimeout(() => {
        sub.style.outline = prev;
        sub.style.outlineOffset = '';
      }, 1600);
    } catch {
      /* ignore */
    }
  }
  return { ok: true, step: 'done', message: `Ready: review and click ${sub ? `"${textOf(sub)}"` : 'Buy/Sell'} yourself` };
}
