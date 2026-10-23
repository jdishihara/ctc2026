// Ring buffer of observed traffic plus a per-kind summary for the Capture tab. Local only; downloads on click.

export interface CaptureEntry {
  t: number; // local receipt ms
  key: string;
  dir: string;
  url?: string;
  raw: string;
  highlights: string[];
}

export interface KindStat {
  key: string;
  count: number;
  first: number;
  last: number;
  recent: number[]; // receipt times in the last 10 s
  example: string;
  highlights: Set<string>;
}

const MAX_RAW = 20_000;

export class Capture {
  readonly buf: (CaptureEntry | undefined)[];
  private head = 0;
  private size = 0;
  readonly kinds = new Map<string, KindStat>();
  version = 0;

  constructor(public capacity = 5000) {
    this.buf = new Array(capacity);
  }

  add(e: CaptureEntry): void {
    const raw = e.raw.length > MAX_RAW ? e.raw.slice(0, MAX_RAW) + '…[truncated]' : e.raw;
    const entry = { ...e, raw };
    this.buf[this.head] = entry;
    this.head = (this.head + 1) % this.capacity;
    this.size = Math.min(this.size + 1, this.capacity);
    let k = this.kinds.get(e.key);
    if (!k) {
      k = { key: e.key, count: 0, first: e.t, last: e.t, recent: [], example: raw, highlights: new Set() };
      this.kinds.set(e.key, k);
    }
    k.count++;
    k.last = e.t;
    k.example = raw;
    k.recent.push(e.t);
    while (k.recent.length && k.recent[0] < e.t - 10_000) k.recent.shift();
    for (const h of e.highlights) k.highlights.add(h);
    this.version++;
  }

  entries(): CaptureEntry[] {
    const out: CaptureEntry[] = [];
    for (let i = 0; i < this.size; i++) {
      const e = this.buf[(this.head - this.size + i + this.capacity) % this.capacity];
      if (e) out.push(e);
    }
    return out;
  }

  get length(): number {
    return this.size;
  }

  ratePerSec(key: string, now = Date.now()): number {
    const k = this.kinds.get(key);
    if (!k) return 0;
    return k.recent.filter((t) => t > now - 10_000).length / 10;
  }

  clear(): void {
    this.buf.fill(undefined);
    this.head = 0;
    this.size = 0;
    this.kinds.clear();
    this.version++;
  }

  toJSON(meta: Record<string, unknown> = {}): string {
    return JSON.stringify(
      {
        meta: { ...meta, exportedAt: new Date().toISOString(), count: this.size },
        kinds: [...this.kinds.values()].map((k) => ({ key: k.key, count: k.count, first: k.first, last: k.last, example: k.example, highlights: [...k.highlights] })),
        entries: this.entries(),
      },
      null,
      1,
    );
  }

  /** Trigger a local download via Blob + <a download>. Must be called from a user click. */
  download(caseName: string, doc: Document = document): string {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const safe = (caseName || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'unknown';
    const name = `ctc-capture-${safe}-${stamp}.json`;
    const blob = new Blob([this.toJSON({ case: caseName })], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = doc.createElement('a');
    a.href = url;
    a.download = name;
    a.style.display = 'none';
    (doc.body || doc.documentElement).appendChild(a);
    a.click(); // a download link, not an exchange control
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    return name;
  }
}
