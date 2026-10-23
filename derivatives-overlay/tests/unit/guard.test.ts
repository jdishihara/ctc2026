// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { DEFAULT_CONFIG } from '../../src/core/config';
import { findChain } from '../../src/core/dom-readers';
import { isSubmitControl, registerChainCell, safeClick, safeKey } from '../../src/ticket/guard';
import { findOrderPanel } from '../../src/ticket/selectors';
import { compileSymbolRegex, DEFAULT_OPTION_REGEX } from '../../src/engine/chain';
import { fillChain, loadMockMarkup } from '../helpers/mockPage';

const hints = DEFAULT_CONFIG.dom;
const btnByText = (t: string) => [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === t)!;

describe('click guard on the mock page markup', () => {
  let submits = 0;
  let clicks: string[] = [];
  document.addEventListener('click', (e) => clicks.push((e.target as Element).textContent?.trim() ?? ''));
  beforeEach(() => {
    loadMockMarkup();
    fillChain(document, [{ K: 100, c: [10, 5.45, 5.66, 20], p: [11, 5.5, 5.7, 30] }]);
    submits = 0;
    clicks = [];
    document.querySelector('form')!.addEventListener('submit', (e) => { e.preventDefault(); submits++; });
  });

  it('blocks the submit button "Buy 50 OIL_0626_C100"', () => {
    const sub = document.querySelector('button.submit')!;
    expect(sub.textContent).toBe('Buy 50 OIL_0626_C100');
    expect(isSubmitControl(sub)).toBe(true);
    expect(safeClick(sub, 'test')).toBe(false);
    expect(submits).toBe(0);
    expect(clicks).toEqual([]);
  });
  it('blocks a Confirm dialog button and any type=submit button', () => {
    const dlg = document.createElement('div');
    dlg.setAttribute('role', 'dialog');
    dlg.innerHTML = '<p>Send order?</p><button type="button">Confirm</button><button type="submit">OK</button><button>Yes</button>';
    document.body.appendChild(dlg);
    const [confirm, ok, yes] = [...dlg.querySelectorAll('button')];
    expect(isSubmitControl(confirm)).toBe(true);
    expect(isSubmitControl(ok)).toBe(true);
    expect(isSubmitControl(yes)).toBe(true);
    expect(safeClick(confirm)).toBe(false);
    const plainSubmit = document.createElement('button');
    plainSubmit.type = 'submit';
    plainSubmit.textContent = 'BUY';
    document.body.appendChild(plainSubmit);
    expect(isSubmitControl(plainSubmit)).toBe(true);
    const implicit = document.createElement('button'); // no type attribute inside a form = submit
    implicit.textContent = 'SELL';
    document.querySelector('form')!.appendChild(implicit);
    expect(isSubmitControl(implicit)).toBe(true);
    expect(safeClick(implicit)).toBe(false);
    expect(submits).toBe(0);
  });
  it('blocks other page controls (quick qty, product tabs, cancel, submit-like text)', () => {
    expect(isSubmitControl(btnByText('50'))).toBe(true);
    expect(isSubmitControl(btnByText('OIL'))).toBe(true);
    const sell = document.createElement('div');
    sell.textContent = 'Sell 10 PLANE_0626_C40';
    document.body.appendChild(sell);
    expect(isSubmitControl(sell)).toBe(true);
    const place = document.createElement('span');
    place.textContent = 'Place order';
    document.body.appendChild(place);
    expect(isSubmitControl(place)).toBe(true);
    const td = document.querySelector('.chain td.px')!; // not registered by the chain reader
    expect(isSubmitControl(td)).toBe(true);
  });
  it('allows exactly the BUY/SELL/Limit/Market toggles and registered chain cells', () => {
    for (const t of ['BUY', 'SELL', 'Limit', 'Market']) {
      const b = btnByText(t);
      expect(isSubmitControl(b), t).toBe(false);
      expect(safeClick(b, t)).toBe(true);
    }
    const chain = findChain(document.body, hints)!;
    expect(chain.rows).toHaveLength(1);
    const ask = chain.rows[0].C.ask.el;
    registerChainCell(ask);
    expect(isSubmitControl(ask)).toBe(false);
    expect(safeClick(ask)).toBe(true);
    expect(clicks).toEqual(['BUY', 'SELL', 'Limit', 'Market', '5.66']);
    expect(submits).toBe(0);
  });
  it('never dispatches Enter', () => {
    const qty = document.querySelector('input.qty')!;
    let enters = 0;
    qty.addEventListener('keydown', (e) => { if ((e as KeyboardEvent).key === 'Enter') enters++; });
    expect(safeKey(qty, 'Enter')).toBe(false);
    expect(safeKey(qty, 'NumpadEnter')).toBe(false);
    expect(enters).toBe(0);
  });
  it('finds the order panel controls by text', () => {
    const p = findOrderPanel(document.body, hints, compileSymbolRegex(DEFAULT_OPTION_REGEX))!;
    expect(p.symbol).toBe('OIL_0626_C100');
    expect(p.qtyInput?.className).toBe('qty');
    expect(p.priceInput?.className).toBe('price'); // not the IV tab's PRICE input
    expect(p.submit?.textContent).toBe('Buy 50 OIL_0626_C100');
    expect(p.buy?.textContent).toBe('BUY');
    expect(p.limit?.textContent).toBe('Limit');
  });
});
