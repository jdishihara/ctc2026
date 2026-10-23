// Classifies bridge messages into stable "kinds" (ws:quote, ws:news:headline, http:GET /api/v1/positions, ...)
// and flags interesting ones. Pure and defensive: never throws.

export interface Classified {
  key: string;
  dir: 'in' | 'out' | 'http' | 'req' | 'meta';
  type: string; // quote | trade | subscription_ack | news | orderbook | unknown | binary | malformed | http | ...
  json?: unknown;
  dup?: boolean;
  highlights: string[];
  seq?: number;
}

export const KNOWN_WS_TYPES = new Set(['quote', 'trade', 'subscription_ack', 'news', 'orderbook', 'book', 'snapshot', 'error', 'heartbeat', 'pong']);

const BOOK_KEYS = /^(bids|asks|levels|book|depth)$/i;
const VOL_WORDS = /\b(analyst|implied[ _]?vol|volatility|vol|iv|sigma)\b/i;

export function urlPath(url: string): string {
  try {
    return new URL(url, 'http://x').pathname;
  } catch {
    return String(url).split('?')[0];
  }
}

function hasKeyDeep(o: unknown, re: RegExp, depth = 0): boolean {
  if (!o || typeof o !== 'object' || depth > 4) return false;
  for (const [k, v] of Object.entries(o as Record<string, unknown>)) {
    if (re.test(k)) return true;
    if (v && typeof v === 'object' && hasKeyDeep(v, re, depth + 1)) return true;
  }
  return false;
}

function mentionsVol(raw: string): boolean {
  return VOL_WORDS.test(raw);
}

export class FrameClassifier {
  private seqs = new Set<number>();
  private seqOrder: number[] = [];
  readonly knownTypes = new Set(KNOWN_WS_TYPES);

  classifyWs(dir: 'in' | 'out', data: unknown, json?: unknown): Classified {
    try {
      if (data && typeof data === 'object' && (data as { binary?: boolean }).binary) {
        return { key: `ws-${dir}:binary`, dir, type: 'binary', highlights: [] };
      }
      const raw = typeof data === 'string' ? data : '';
      let j = json;
      if (j === undefined) {
        try {
          j = JSON.parse(raw);
        } catch {
          return { key: dir === 'in' ? 'ws:malformed' : 'ws-out:malformed', dir, type: 'malformed', highlights: ['malformed'] };
        }
      }
      if (dir === 'out') {
        const action = j && typeof j === 'object' ? String((j as Record<string, unknown>).action ?? (j as Record<string, unknown>).type ?? 'frame') : 'frame';
        return { key: `ws-out:${action}`, dir, type: action, json: j, highlights: [] };
      }
      const o = (j && typeof j === 'object' ? j : {}) as Record<string, unknown>;
      const type = typeof o.type === 'string' ? o.type : Array.isArray(j) ? 'array' : 'untyped';
      const highlights: string[] = [];
      if (!this.knownTypes.has(type)) highlights.push('new-type');
      if (type !== 'quote' && type !== 'trade' && hasKeyDeep(j, BOOK_KEYS)) highlights.push('orderbook-like');
      if (type !== 'quote' && type !== 'trade' && mentionsVol(raw)) highlights.push('vol/analyst');
      if (type === 'news') {
        const msg = (o.message && typeof o.message === 'object' ? o.message : o) as Record<string, unknown>;
        const sub = typeof msg.type === 'string' ? msg.type : typeof msg.headline === 'string' ? 'headline' : 'untyped';
        const seq = typeof msg.seq === 'number' ? msg.seq : typeof o.seq === 'number' ? o.seq : undefined;
        let dup = false;
        if (seq != null) {
          dup = this.seqs.has(seq);
          if (!dup) {
            this.seqs.add(seq);
            this.seqOrder.push(seq);
            if (this.seqOrder.length > 5000) this.seqs.delete(this.seqOrder.shift() as number);
          }
        }
        return { key: `ws:news:${sub}`, dir, type, json: j, dup, seq, highlights };
      }
      return { key: `ws:${type}`, dir, type, json: j, highlights };
    } catch {
      return { key: 'ws:malformed', dir, type: 'malformed', highlights: ['malformed'] };
    }
  }

  classifyHttp(method: string, url: string, json?: unknown, raw?: string, isReq = false): Classified {
    const key = `${isReq ? 'req' : 'http'}:${(method || 'GET').toUpperCase()} ${urlPath(url)}`;
    const highlights: string[] = [];
    try {
      if (hasKeyDeep(json, BOOK_KEYS)) highlights.push('orderbook-like');
      if (raw && /news|headline|analyst/i.test(url + ' ' + raw.slice(0, 4000)) && mentionsVol(raw.slice(0, 4000))) highlights.push('vol/analyst');
    } catch {
      /* ignore */
    }
    return { key, dir: isReq ? 'req' : 'http', type: 'http', json, highlights };
  }
}
