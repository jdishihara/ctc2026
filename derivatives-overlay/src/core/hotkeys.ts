// Overlay hotkeys. Matched on event.code because macOS Option changes event.key.

export type HotkeyAction =
  | 'nextTicket' | 'nextFlatten' | 'accept' | 'focusOIL' | 'focusPLANE' | 'toggle' | 'focusSpot' | 'focusVol' | 'capture' | 'autoPause' | 'confirmPending' | 'skipPending' | 'blur';

const ALT_MAP: Record<string, HotkeyAction> = {
  KeyN: 'nextTicket', KeyF: 'nextFlatten', KeyA: 'accept', Digit1: 'focusOIL', Digit2: 'focusPLANE',
  KeyO: 'toggle', KeyS: 'focusSpot', KeyV: 'focusVol', KeyC: 'capture', KeyP: 'autoPause', KeyY: 'confirmPending', KeyX: 'skipPending',
};

export function hotkeyFor(e: Pick<KeyboardEvent, 'code' | 'altKey' | 'ctrlKey' | 'metaKey' | 'shiftKey'>): HotkeyAction | null {
  if (e.code === 'Escape' && !e.altKey && !e.ctrlKey && !e.metaKey) return 'blur';
  if (!e.altKey || e.ctrlKey || e.metaKey) return null;
  return ALT_MAP[e.code] ?? null;
}

/** True when focus is in a text field of the exchange page (not our overlay). */
export function inExchangeInput(e: Event, overlayHost: Element | null): boolean {
  const path = (e.composedPath?.() ?? []) as EventTarget[];
  if (overlayHost && path.includes(overlayHost)) return false;
  const t = (path[0] ?? e.target) as Element | null;
  if (!t || !(t as Element).tagName) return false;
  const tag = (t as Element).tagName.toLowerCase();
  return tag === 'input' || tag === 'textarea' || tag === 'select' || (t as HTMLElement).isContentEditable === true;
}

export function installHotkeys(win: Window, overlayHost: Element | null, handler: (a: HotkeyAction, e: KeyboardEvent) => void): () => void {
  const onKey = (e: KeyboardEvent) => {
    try {
      const a = hotkeyFor(e);
      if (!a) return;
      if (a === 'blur') return handler(a, e); // never swallow Escape: the page may use it to close dialogs
      if (inExchangeInput(e, overlayHost)) return;
      e.preventDefault();
      e.stopPropagation();
      handler(a, e);
    } catch {
      /* ignore */
    }
  };
  win.addEventListener('keydown', onKey, true);
  return () => win.removeEventListener('keydown', onKey, true);
}
