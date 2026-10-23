// Bridge protocol between the MAIN-world hooks and the isolated-world overlay.

export const BRIDGE_TAG = '__derivOverlay';

export type BridgeKind = 'ws-open' | 'ws-close' | 'ws-in' | 'ws-out' | 'http' | 'http-req' | 'hooks-ready' | 'overlay-ready';

export interface BinaryInfo {
  binary: true;
  size: number;
}

export interface BridgePayload {
  url?: string;
  data?: string | BinaryInfo;
  json?: unknown;
  method?: string;
  status?: number;
  body?: string | null;
  t?: number;
  code?: number;
}

export interface BridgeMessage {
  [BRIDGE_TAG]: 1;
  kind: BridgeKind;
  payload: BridgePayload;
  /** per-page sequence number, used to de-duplicate the replay of messages buffered before the overlay loaded */
  n?: number;
}

/** Messages buffered by the hooks until the overlay (document_idle) announces it is listening. */
export const BRIDGE_BUFFER_MAX = 3000;

/**
 * Same window only. Chrome always sets `source` to the posting window; jsdom (tests) leaves it null with an empty
 * origin, which never happens for a real cross-window message, so that combination is accepted too.
 */
export function fromSameWindow(ev: MessageEvent, win: Window): boolean {
  if (ev.source === win) return true;
  try {
    return ev.source == null && (ev.origin === win.location.origin || ev.origin === '');
  } catch {
    return false;
  }
}

export function isBridgeMessage(ev: MessageEvent, win: Window = window): ev is MessageEvent<BridgeMessage> {
  try {
    const d = ev.data as Record<string, unknown> | null;
    return fromSameWindow(ev, win) && !!d && typeof d === 'object' && d[BRIDGE_TAG] === 1 && typeof d.kind === 'string';
  } catch {
    return false;
  }
}

/** Skip anything auth/admin related entirely: we never look at those. */
export function isSensitiveUrl(url: string): boolean {
  return /\/(auth|admin)(\/|\?|$)/i.test(url) || /token|session|cookie/i.test(url.split('?')[0]);
}
