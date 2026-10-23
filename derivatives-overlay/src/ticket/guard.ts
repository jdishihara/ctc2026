// Hard guard for every synthetic click. Only the exact side/type toggles and registered chain cells may be clicked.
// Anything that looks like an order submission (or a confirm dialog) is refused and logged.

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
