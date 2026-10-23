// MAIN-world observers. Runs at document_start. Wraps fetch, XMLHttpRequest and WebSocket to *observe*:
// responses are cloned, frames are copied, and everything is passed through unchanged. Every hook body is
// wrapped in try/catch so a bug here can never break the page. This file never sends anything to the network.
import { BRIDGE_BUFFER_MAX, BRIDGE_TAG, BridgeKind, BridgeMessage, BridgePayload, fromSameWindow, isSensitiveUrl } from '../core/bus';

type W = Window & typeof globalThis & { __derivOverlayHooked?: boolean };

export function installHooks(win: W = window as W): void {
  if (win.__derivOverlayHooked) return;
  try {
    Object.defineProperty(win, '__derivOverlayHooked', { value: true, enumerable: false, configurable: true });
  } catch {
    win.__derivOverlayHooked = true;
  }

  // The overlay script loads at document_idle, after the first requests and frames. Keep a bounded buffer until it
  // says it is listening, then replay; it de-duplicates by sequence number.
  let seq = 0;
  let overlayReady = false;
  let buffer: BridgeMessage[] = [];
  const post = (kind: BridgeKind, payload: BridgePayload) => {
    try {
      const msg: BridgeMessage = { [BRIDGE_TAG]: 1, kind, payload, n: ++seq };
      if (!overlayReady) {
        buffer.push(msg);
        if (buffer.length > BRIDGE_BUFFER_MAX) buffer.shift();
      }
      win.postMessage(msg, '*');
    } catch {
      /* never throw into the page */
    }
  };
  try {
    win.addEventListener('message', (ev: MessageEvent) => {
      try {
        const d = ev.data as BridgeMessage | null;
        if (!fromSameWindow(ev, win) || !d || d[BRIDGE_TAG] !== 1 || d.kind !== 'overlay-ready') return;
        const replay = buffer;
        buffer = [];
        overlayReady = true;
        for (const m of replay) win.postMessage(m, '*');
      } catch {
        /* ignore */
      }
    });
  } catch {
    /* ignore */
  }
  const tryJson = (text: string): unknown => {
    try {
      return JSON.parse(text);
    } catch {
      return undefined;
    }
  };
  const absUrl = (u: string) => {
    try {
      return new URL(u, win.location.href).href;
    } catch {
      return String(u);
    }
  };

  // ---- WebSocket ----
  try {
    const Orig = win.WebSocket;
    if (typeof Orig === 'function') {
      const Wrapped = function (this: unknown, url: string | URL, protocols?: string | string[]) {
        const ws = protocols === undefined ? new Orig(url) : new Orig(url, protocols);
        try {
          const u = absUrl(String(url));
          ws.addEventListener('open', () => post('ws-open', { url: u, t: Date.now() }));
          ws.addEventListener('close', (ev) => post('ws-close', { url: u, code: (ev as CloseEvent).code, t: Date.now() }));
          ws.addEventListener('message', (ev: MessageEvent) => {
            try {
              const d = ev.data;
              if (typeof d === 'string') post('ws-in', { url: u, data: d, json: tryJson(d), t: Date.now() });
              else post('ws-in', { url: u, data: { binary: true, size: (d && (d.byteLength ?? d.size)) || 0 }, t: Date.now() });
            } catch {
              /* ignore */
            }
          });
          const origSend = ws.send;
          ws.send = function (this: WebSocket, data: string | ArrayBufferLike | Blob | ArrayBufferView) {
            try {
              if (typeof data === 'string') post('ws-out', { url: u, data, json: tryJson(data), t: Date.now() });
              else post('ws-out', { url: u, data: { binary: true, size: (data as ArrayBuffer).byteLength ?? (data as Blob).size ?? 0 }, t: Date.now() });
            } catch {
              /* ignore */
            }
            return origSend.call(this, data);
          };
        } catch {
          /* observation failed; socket still works */
        }
        return ws;
      } as unknown as typeof WebSocket;
      Wrapped.prototype = Orig.prototype;
      for (const k of ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'] as const) {
        try {
          Object.defineProperty(Wrapped, k, { value: Orig[k], enumerable: true });
        } catch {
          /* ignore */
        }
      }
      win.WebSocket = Wrapped;
    }
  } catch {
    /* leave WebSocket untouched */
  }

  // ---- fetch ----
  try {
    const origFetch = win.fetch;
    if (typeof origFetch === 'function') {
      const wrappedFetch = function (this: unknown, input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
        let method = 'GET';
        let url = '';
        let req: Request | null = null;
        try {
          if (typeof input === 'string') url = input;
          else if (input instanceof URL) url = input.href;
          else if (input && typeof (input as Request).url === 'string') {
            req = input as Request;
            url = req.url;
            method = req.method || 'GET';
          }
          if (init?.method) method = init.method;
          method = method.toUpperCase();
          url = absUrl(url);
        } catch {
          /* ignore */
        }
        const skip = !url || isSensitiveUrl(url);
        try {
          if (!skip && method !== 'GET' && method !== 'HEAD') {
            const t = Date.now();
            const b = init?.body;
            if (typeof b === 'string' || b == null) {
              if (b == null && req) {
                req.clone().text().then((text) => post('http-req', { method, url, body: text, json: tryJson(text), t }), () => post('http-req', { method, url, body: null, t }));
              } else post('http-req', { method, url, body: (b as string) ?? null, json: typeof b === 'string' ? tryJson(b) : undefined, t });
            } else post('http-req', { method, url, body: null, t });
          }
        } catch {
          /* ignore */
        }
        const p = origFetch.call(win, input as RequestInfo, init);
        if (!skip) {
          p.then(
            (res) => {
              try {
                const ct = res.headers.get('content-type') || '';
                if (ct.includes('json') || url.includes('/api/')) {
                  res.clone().text().then(
                    (text) => post('http', { method, url, status: res.status, body: text.length > 200_000 ? text.slice(0, 200_000) : text, json: tryJson(text), t: Date.now() }),
                    () => undefined,
                  );
                }
              } catch {
                /* ignore */
              }
            },
            () => undefined,
          );
        }
        return p;
      };
      win.fetch = wrappedFetch as typeof fetch;
    }
  } catch {
    /* leave fetch untouched */
  }

  // ---- XMLHttpRequest ----
  try {
    const XHR = win.XMLHttpRequest;
    if (typeof XHR === 'function') {
      const meta = new WeakMap<XMLHttpRequest, { method: string; url: string }>();
      const origOpen = XHR.prototype.open;
      const origSend = XHR.prototype.send;
      XHR.prototype.open = function (this: XMLHttpRequest, method: string, url: string | URL, ...rest: unknown[]) {
        try {
          meta.set(this, { method: String(method || 'GET').toUpperCase(), url: absUrl(String(url)) });
        } catch {
          /* ignore */
        }
        return (origOpen as (...a: unknown[]) => void).call(this, method, url, ...rest);
      } as typeof XHR.prototype.open;
      XHR.prototype.send = function (this: XMLHttpRequest, body?: Document | XMLHttpRequestBodyInit | null) {
        try {
          const m = meta.get(this);
          if (m && !isSensitiveUrl(m.url)) {
            if (m.method !== 'GET' && m.method !== 'HEAD') {
              post('http-req', { method: m.method, url: m.url, body: typeof body === 'string' ? body : null, json: typeof body === 'string' ? tryJson(body) : undefined, t: Date.now() });
            }
            this.addEventListener('load', () => {
              try {
                let text: string | null = null;
                if (this.responseType === '' || this.responseType === 'text') text = this.responseText;
                else if (this.responseType === 'json') text = JSON.stringify(this.response);
                if (text != null) post('http', { method: m.method, url: m.url, status: this.status, body: text, json: tryJson(text), t: Date.now() });
              } catch {
                /* ignore */
              }
            });
          }
        } catch {
          /* ignore */
        }
        return origSend.call(this, body);
      };
    }
  } catch {
    /* leave XHR untouched */
  }

  post('hooks-ready', { t: Date.now(), url: win.location?.href });
}

if (typeof window !== 'undefined' && !(typeof process !== 'undefined' && process.env?.VITEST)) installHooks();
