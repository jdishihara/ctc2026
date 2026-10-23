// Locate the order panel and its controls by visible text (patterns live in Config.dom).
import { DomHints } from '../core/config';
import { findByExactText, isVisible, textOf } from '../core/dom-readers';

export interface OrderPanel {
  root: Element;
  symbol: string | null;
  qtyInput: HTMLInputElement | null;
  priceInput: HTMLInputElement | null;
  buy: Element | null;
  sell: Element | null;
  limit: Element | null;
  market: Element | null;
  submit: Element | null;
}

function inputNear(label: Element, within: Element): HTMLInputElement | null {
  // closest input that follows the label inside the smallest shared ancestor
  let cur: Element | null = label;
  for (let up = 0; up < 4 && cur && cur !== within.parentElement; up++) {
    const inputs = Array.from(cur.querySelectorAll('input')) as HTMLInputElement[];
    const after = inputs.find((i) => label.compareDocumentPosition(i) & Node.DOCUMENT_POSITION_FOLLOWING);
    if (after) return after;
    cur = cur.parentElement;
  }
  // <label for=...> association
  const forId = label.getAttribute('for');
  if (forId) {
    const el = label.ownerDocument.getElementById(forId);
    if (el instanceof label.ownerDocument.defaultView!.HTMLInputElement) return el;
  }
  return null;
}

const buttonish = (el: Element) => el.tagName === 'BUTTON' || el.getAttribute('role') === 'button' || el.getAttribute('role') === 'tab' || el.tagName === 'A' || el.tagName === 'LABEL' || el.tagName === 'INPUT';

function clickableByText(root: Element, text: string, skip?: (el: Element) => boolean): Element | null {
  const els = findByExactText(root, text, true, skip).filter(isVisible);
  // prefer actual buttons; climb from a span inside a button
  for (const e of els) {
    const b = e.closest('button,[role=button],[role=tab]');
    if (b && root.contains(b) && textOf(b) === text) return b;
  }
  return els.find(buttonish) ?? els[0] ?? null;
}

export function findOrderPanel(doc: ParentNode, hints: DomHints, symbolRe: RegExp, skip?: (el: Element) => boolean): OrderPanel | null {
  const qtyLabels = findByExactText(doc, hints.qtyLabel, false, skip).filter(isVisible);
  for (const ql of qtyLabels) {
    // the panel = smallest ancestor that also contains the BUY and SELL toggles
    let root: Element | null = ql.parentElement;
    while (root && !(findByExactText(root, hints.buyText, true, skip).length && findByExactText(root, hints.sellText, true, skip).length)) root = root.parentElement;
    if (!root) continue;
    const qtyInput = inputNear(ql, root);
    const priceLabel = findByExactText(root, hints.priceLabel, false, skip).find(isVisible) ?? null;
    const priceInput = priceLabel ? inputNear(priceLabel, root) : null;
    let symbol: string | null = null;
    // the panel's contract label; widen to the parent if the label sits just outside the form
    for (const scope of [root, root.parentElement].filter(Boolean) as Element[]) {
      for (const el of Array.from(scope.querySelectorAll('*'))) {
        if (el.children.length) continue;
        const t = textOf(el);
        if (symbolRe.test(t)) {
          symbol = t;
          break;
        }
      }
      if (symbol) break;
    }
    const submit =
      Array.from(root.querySelectorAll('button,[role=button],input[type=submit]')).find((b) => /^(buy|sell)\b.*\d/i.test(textOf(b)) || (b.getAttribute('type') ?? '').toLowerCase() === 'submit') ?? null;
    return {
      root, symbol, qtyInput, priceInput, submit,
      buy: clickableByText(root, hints.buyText, skip),
      sell: clickableByText(root, hints.sellText, skip),
      limit: clickableByText(root, hints.limitText, skip),
      market: clickableByText(root, hints.marketText, skip),
    };
  }
  return null;
}
