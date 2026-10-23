// Naive (timezone-free) exchange time. Exchange timestamps like "2026-06-01T09:30:00" carry no zone, so we never
// pass them to new Date(string). Internally a naive time is "seconds since 1970-01-01 00:00 on a UTC calendar".

export interface NaiveTime {
  y: number; m: number; d: number; hh: number; mm: number; ss: number;
}

export function parseNaive(s: string): NaiveTime | null {
  const m = /^\s*(\d{4})-(\d{2})-(\d{2})[T ](\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?/.exec(s ?? '');
  if (!m) return null;
  const frac = m[7] ? Number('0.' + m[7]) : 0;
  return { y: +m[1], m: +m[2], d: +m[3], hh: +m[4], mm: +m[5], ss: (m[6] ? +m[6] : 0) + frac };
}

export function toSec(t: NaiveTime): number {
  return Date.UTC(t.y, t.m - 1, t.d, t.hh, t.mm, 0) / 1000 + t.ss;
}

export function fromSec(sec: number): NaiveTime {
  const whole = Math.floor(sec);
  const dt = new Date(whole * 1000);
  return {
    y: dt.getUTCFullYear(), m: dt.getUTCMonth() + 1, d: dt.getUTCDate(),
    hh: dt.getUTCHours(), mm: dt.getUTCMinutes(), ss: dt.getUTCSeconds() + (sec - whole),
  };
}

export function parseNaiveSec(s: string): number | null {
  const t = parseNaive(s);
  return t ? toSec(t) : null;
}

const pad = (n: number) => String(Math.floor(n)).padStart(2, '0');
export function fmtDate(sec: number): string {
  const t = fromSec(sec);
  return `${t.y}-${pad(t.m)}-${pad(t.d)}`;
}
export function fmtTime(sec: number): string {
  const t = fromSec(sec);
  return `${pad(t.hh)}:${pad(t.mm)}:${pad(t.ss)}`;
}
export function dayStart(sec: number): number {
  return Math.floor(sec / 86400) * 86400;
}
export function secOfDay(sec: number): number {
  return sec - dayStart(sec);
}
/** "HH:MM[:SS]" -> seconds after midnight */
export function hmsToSec(s: string): number {
  const [h, m, x] = s.split(':').map(Number);
  return h * 3600 + m * 60 + (x || 0);
}
export function isWeekday(sec: number): boolean {
  const wd = new Date(dayStart(sec) * 1000).getUTCDay();
  return wd >= 1 && wd <= 5;
}

export interface SessionSpec {
  expiry: string; // naive "2026-06-26T16:00:00"
  open: string; // "09:30"
  close: string; // "16:00"
  holidays?: string[]; // "YYYY-MM-DD"
}

export const DEFAULT_SESSION: SessionSpec = { expiry: '2026-06-26T16:00:00', open: '09:30', close: '16:00', holidays: [] };

/** Trading days left until expiry: today's remaining session fraction plus full sessions after today. */
export function tradingDaysRemaining(nowSec: number, spec: SessionSpec = DEFAULT_SESSION): number {
  const exp = parseNaiveSec(spec.expiry);
  if (exp == null || nowSec >= exp) return 0;
  const open = hmsToSec(spec.open);
  const close = hmsToSec(spec.close);
  const len = close - open;
  const hol = new Set(spec.holidays ?? []);
  const isSession = (daySec: number) => isWeekday(daySec) && !hol.has(fmtDate(daySec));
  const today = dayStart(nowSec);
  const expDay = dayStart(exp);
  let days = 0;
  if (isSession(today)) {
    const endToday = today === expDay ? Math.min(close, secOfDay(exp)) : close;
    const t = Math.min(Math.max(secOfDay(nowSec), open), endToday);
    days += Math.max(endToday - t, 0) / len;
  }
  for (let d = today + 86400; d <= expDay; d += 86400) {
    if (!isSession(d)) continue;
    days += d === expDay ? Math.max(Math.min(secOfDay(exp), close) - open, 0) / len : 1;
  }
  return days;
}

export function yearsFromDays(days: number): number {
  return days / 252;
}
