// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { safeClick, safeSubmit, safeTabClick, submitLog, submitRefusal, SubmitContext } from '../../src/ticket/guard';
import { fillChain, loadMockMarkup } from '../helpers/mockPage';

const ticket = { symbol: 'OIL_0626_C100', side: 'BUY' as const, qty: 50, price: 5.66 };
const good = (): SubmitContext => ({
  armed: true, ticket,
  form: { symbol: 'OIL_0626_C100', qty: '50', price: '5.66', submitText: 'Buy 50 OIL_0626_C100' },
  rateUsed: 3, rateCap: 36,
});
const btnByText = (t: string) => [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === t)!;

describe('submitRefusal: every condition must hold', () => {
  it('passes a verified form inside the budget', () => {
    expect(submitRefusal(good())).toBeNull();
  });
  it('refuses when not armed', () => {
    expect(submitRefusal({ ...good(), armed: false })).toMatch(/off or paused/);
  });
  it('refuses when the rate budget is used up', () => {
    expect(submitRefusal({ ...good(), rateUsed: 36 })).toMatch(/rate budget: 36\/36/);
  });
  it('refuses a form that does not match the ticket', () => {
    expect(submitRefusal({ ...good(), form: { ...good().form, qty: '5' } })).toMatch(/QTY 5 ≠ ticket 50/);
    expect(submitRefusal({ ...good(), form: { ...good().form, price: '5.65' } })).toMatch(/PRICE 5.65/);
    expect(submitRefusal({ ...good(), form: { ...good().form, symbol: 'OIL_0626_P100' } })).toMatch(/form shows OIL_0626_P100/);
    expect(submitRefusal({ ...good(), form: { ...good().form, submitText: 'Sell 50 OIL_0626_C100' } })).toMatch(/says SELL/);
    expect(submitRefusal({ ...good(), form: { ...good().form, submitText: 'Buy 40 OIL_0626_C100' } })).toMatch(/says 40/);
    expect(submitRefusal({ ...good(), form: { ...good().form, symbol: null } })).toMatch(/no contract/);
  });
  it('accepts a submit button without qty/symbol in its text, and tolerates formatting', () => {
    expect(submitRefusal({ ...good(), form: { ...good().form, submitText: 'Buy' } })).toBeNull();
    expect(submitRefusal({ ...good(), form: { ...good().form, qty: ' 50 ', price: '$5.66' } })).toBeNull();
  });
});

describe('safeSubmit / safeTabClick on the mock page markup', () => {
  let submits = 0;
  beforeEach(() => {
    loadMockMarkup();
    fillChain(document, [{ K: 100, c: [10, 5.45, 5.66, 20], p: [11, 5.5, 5.7, 30] }]);
    submits = 0;
    document.querySelector('form')!.addEventListener('submit', (e) => { e.preventDefault(); submits++; });
    (document.querySelector('input.qty') as HTMLInputElement).value = '50';
    (document.querySelector('input.price') as HTMLInputElement).value = '5.66';
    submitLog.length = 0;
  });
  it('safeClick still refuses the submit button whatever the arming state', () => {
    const sub = document.querySelector('button.submit')!;
    expect(safeClick(sub, 'auto')).toBe(false);
    expect(submits).toBe(0);
  });
  it('safeSubmit clicks it only when armed, verified and inside the budget', () => {
    const sub = document.querySelector('button.submit')!;
    expect(safeSubmit(sub, { ...good(), armed: false }).ok).toBe(false);
    expect(safeSubmit(sub, { ...good(), rateUsed: 40 }).ok).toBe(false);
    expect(safeSubmit(sub, { ...good(), form: { ...good().form, qty: '49' } }).ok).toBe(false);
    expect(submits).toBe(0);
    const r = safeSubmit(sub, good());
    expect(r).toEqual({ ok: true, reason: 'clicked' });
    expect(submits).toBe(1);
    expect(submitLog.filter((x) => !x.ok)).toHaveLength(3);
    expect(submitLog.filter((x) => x.ok)).toHaveLength(1);
  });
  it('safeSubmit never clicks confirm dialogs, cancel buttons or non-submit controls', () => {
    const dlg = document.createElement('div');
    dlg.innerHTML = '<button type="submit">Confirm</button><button type="button">Cancel all</button>';
    document.body.appendChild(dlg);
    const [confirm, cancel] = [...dlg.querySelectorAll('button')];
    expect(safeSubmit(confirm, good()).reason).toMatch(/confirm/);
    expect(safeSubmit(cancel, good()).reason).toMatch(/not the order form submit button|confirm/);
    expect(safeSubmit(btnByText('BUY'), good()).reason).toMatch(/not the order form submit button/);
    expect(safeSubmit(null, good()).ok).toBe(false);
    expect(submits).toBe(0);
  });
  it('safeTabClick allows only an armed click on a product tab outside the form', () => {
    let tabClicks = 0;
    const oil = btnByText('OIL');
    oil.addEventListener('click', () => tabClicks++);
    expect(safeTabClick(oil, ['OIL', 'PLANE'], false)).toBe(false);
    expect(safeTabClick(btnByText('BUY'), ['OIL', 'PLANE'], true)).toBe(false); // in the form
    expect(safeTabClick(btnByText('50'), ['OIL', 'PLANE'], true)).toBe(false); // not an underlying
    expect(safeTabClick(document.querySelector('button.submit'), ['OIL', 'PLANE'], true)).toBe(false);
    expect(tabClicks).toBe(0);
    expect(safeTabClick(oil, ['OIL', 'PLANE'], true)).toBe(true);
    expect(tabClicks).toBe(1);
    expect(submits).toBe(0);
  });
});
