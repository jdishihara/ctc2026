// Hard guard for every synthetic click. Only the exact side/type toggles and registered chain cells may be clicked.
// Anything that looks like an order submission (or a confirm dialog) is refused and logged by safeClick.
//
// One deliberate, narrow exception: safeSubmit() clicks the order form's submit button, and only when the auto-pilot is
// armed (Config auto.submit on, not paused), the form has just been verified to hold exactly the ticket we loaded, and
// the order-rate budget allows it. It never clicks confirm dialogs or anything else. safeTabClick() may click a product
// tab (a button whose whole text is an underlying's name, outside any form) under the same arming condition.

export interface GuardConfig {
  toggles: string[]; // exact texts, e.g. BUY SELL Limit Market
}

export const DEFAULT_GUARD: GuardConfig = { toggles: ['BUY', 'SELL', 'Limit', 'Market'] };

const chainCells = new WeakSet<Element>();
export const guardLog: { t: number; text: string; reason: string }[] = [];

/** Only cells located by the chain reader are registered. */
export function registerChainCell(el: Element): void {
  chainCells.add(el);
}
export function isChainCell(el: Element): boolean {
  return chainCells.has(el);
}

const SUBMIT_LIKE = /^(buy|sell|place|submit|confirm|send)\b.*\d/i;
const SUBMIT_WORDS = /\b(confirm|submit|place order|send)\b/i;

export function isSubmitControl(el: Element, cfg: GuardConfig = DEFAULT_GUARD): boolean {
  const text = (el.textContent ?? '').replace(/\s+/g, ' ').trim();
  const tag = el.tagName.toLowerCase();
  const type = (el.getAttribute('type') ?? '').toLowerCase();
  const isToggle = cfg.toggles.includes(text);
  // <button> without a type inside a form defaults to submit.
  const effectiveSubmit = type === 'submit' || (tag === 'button' && !type && !!el.closest('form')) || (tag === 'input' && (type === 'submit' || type === 'image'));
  if (effectiveSubmit) return true;
  if (el.closest('form') && !isToggle && !isChainCell(el)) return true;
  if (SUBMIT_LIKE.test(text) || SUBMIT_WORDS.test(text)) return true;
  if (!isToggle && !isChainCell(el)) return true;
  // a "toggle" or cell that contains a submit control is not safe either
  if (el.querySelector('button[type=submit], input[type=submit], form')) return true;
  return false;
}

export function safeClick(el: Element | null, why = '', cfg: GuardConfig = DEFAULT_GUARD): boolean {
  if (!el) return false;
  try {
    if (isSubmitControl(el, cfg)) {
      const text = (el.textContent ?? '').trim().slice(0, 60);
      guardLog.push({ t: Date.now(), text, reason: why });
      if (guardLog.length > 100) guardLog.shift();
      console.warn('[deriv-overlay] guard refused click on', JSON.stringify(text), why);
      return false;
    }
    const win = el.ownerDocument.defaultView;
    const opts: MouseEventInit = { bubbles: true, cancelable: true, composed: true, button: 0 };
    const PE = (win as unknown as { PointerEvent?: typeof PointerEvent })?.PointerEvent;
    if (PE) el.dispatchEvent(new PE('pointerdown', opts));
    el.dispatchEvent(new (win?.MouseEvent ?? MouseEvent)('mousedown', opts));
    if (PE) el.dispatchEvent(new PE('pointerup', opts));
    el.dispatchEvent(new (win?.MouseEvent ?? MouseEvent)('mouseup', opts));
    el.dispatchEvent(new (win?.MouseEvent ?? MouseEvent)('click', opts));
    return true;
  } catch {
    return false;
  }
}

export interface SubmitContext {
  /** Config auto.submit && !paused */
  armed: boolean;
  /** what the auto-pilot loaded */
  ticket: { symbol: string; side: 'BUY' | 'SELL'; qty: number; price: number };
  /** what the order panel shows right now */
  form: { symbol: string | null; qty: string | null; price: string | null; submitText: string };
  /** observed order actions in the last minute and our own cap */
  rateUsed: number;
  rateCap: number;
}

export const submitLog: { t: number; text: string; ok: boolean; reason: string }[] = [];

const num = (x: string | null | undefined) => Number(String(x ?? '').replace(/[,$\s]/g, ''));

/** Why the submit would be refused, or null when every condition holds. Pure: no DOM access beyond the inputs. */
export function submitRefusal(ctx: SubmitContext): string | null {
  if (!ctx.armed) return 'auto-submit is off or paused';
  if (!(ctx.rateUsed < ctx.rateCap)) return `rate budget: ${ctx.rateUsed}/${ctx.rateCap} order actions in the last minute`;
  const t = ctx.ticket;
  const f = ctx.form;
  if (!t || !(t.qty > 0) || !(t.price > 0)) return 'ticket has no positive qty/price';
  if (f.symbol !== t.symbol) return `form shows ${f.symbol ?? 'no contract'}, ticket is ${t.symbol}`;
  if (!Number.isFinite(num(f.qty)) || Math.abs(num(f.qty) - t.qty) > 1e-9) return `form QTY ${f.qty ?? '?'} ≠ ticket ${t.qty}`;
  if (!Number.isFinite(num(f.price)) || Math.abs(num(f.price) - t.price) > 1e-9) return `form PRICE ${f.price ?? '?'} ≠ ticket ${t.price}`;
  const m = /^(buy|sell)\b(?:\s+(\d[\d,]*))?(?:\s+(\S+))?/i.exec(f.submitText.trim());
  if (m) {
    if (m[1].toUpperCase() !== t.side) return `submit button says ${m[1].toUpperCase()}, ticket is ${t.side}`;
    if (m[2] && Math.abs(num(m[2]) - t.qty) > 1e-9) return `submit button says ${m[2]}, ticket qty is ${t.qty}`;
    if (m[3] && m[3] !== t.symbol) return `submit button says ${m[3]}, ticket is ${t.symbol}`;
  }
  return null;
}

/** The only path that clicks a submit button. Refuses unless submitRefusal() is null; logs every attempt. */
export function safeSubmit(el: Element | null, ctx: SubmitContext): { ok: boolean; reason: string } {
  const text = (el?.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 60);
  const log = (ok: boolean, reason: string) => {
    submitLog.push({ t: Date.now(), text, ok, reason });
    if (submitLog.length > 200) submitLog.shift();
    if (!ok) console.warn('[deriv-overlay] auto-submit refused', JSON.stringify(text), reason);
    return { ok, reason };
  };
  if (!el) return log(false, 'no submit button');
  const refusal = submitRefusal(ctx);
  if (refusal) return log(false, refusal);
  const tag = el.tagName.toLowerCase();
  const type = (el.getAttribute('type') ?? '').toLowerCase();
  const looksSubmit = type === 'submit' || (tag === 'button' && !type && !!el.closest('form')) || /^(buy|sell)\s+\d/i.test(text);
  if (!looksSubmit) return log(false, 'element is not the order form submit button');
  if (/\b(confirm|cancel|delete|all)\b/i.test(text)) return log(false, 'refusing confirm/cancel-like button');
  try {
    (el as HTMLElement).click();
    return log(true, 'clicked');
  } catch (e) {
    return log(false, `click failed: ${e}`);
  }
}

/** Click a product tab (OIL / PLANE) for the auto-pilot: the whole text must be an underlying's name and it must not sit in a form. */
export function safeTabClick(el: Element | null, underlyings: string[], armed: boolean): boolean {
  if (!el || !armed) return false;
  const text = (el.textContent ?? '').replace(/\s+/g, ' ').trim();
  if (!underlyings.includes(text)) return false;
  if (el.closest('form')) return false;
  const tag = el.tagName.toLowerCase();
  const type = (el.getAttribute('type') ?? '').toLowerCase();
  if (type === 'submit') return false;
  if (!(tag === 'button' || tag === 'a' || el.getAttribute('role') === 'tab' || el.getAttribute('role') === 'button')) return false;
  if (el.querySelector('button, input, form')) return false;
  try {
    (el as HTMLElement).click();
    return true;
  } catch {
    return false;
  }
}

/** Keyboard dispatch is limited to harmless keys; Enter (which can submit forms) is always refused. */
export function safeKey(el: Element, key: string): boolean {
  if (/^(enter|numpadenter)$/i.test(key)) {
    guardLog.push({ t: Date.now(), text: key, reason: 'Enter is never dispatched' });
    return false;
  }
  const win = el.ownerDocument.defaultView;
  el.dispatchEvent(new (win?.KeyboardEvent ?? KeyboardEvent)('keydown', { key, bubbles: true }));
  el.dispatchEvent(new (win?.KeyboardEvent ?? KeyboardEvent)('keyup', { key, bubbles: true }));
  return true;
}
