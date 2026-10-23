export const f = (x: number | null | undefined, d = 2) => (x == null || !Number.isFinite(x) ? '—' : x.toFixed(d));
export const pct = (x: number | null | undefined, d = 1) => (x == null || !Number.isFinite(x) ? '—' : (x * 100).toFixed(d) + '%');
export const signed = (x: number | null | undefined, d = 2) => (x == null || !Number.isFinite(x) ? '—' : (x > 0 ? '+' : '') + x.toFixed(d));
export const money = (x: number | null | undefined) => (x == null || !Number.isFinite(x) ? '—' : (x < 0 ? '-$' : '$') + Math.abs(x).toFixed(0));
export function mmss(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec)) return '—';
  const s = Math.max(0, Math.ceil(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
export const cls = (...xs: (string | false | null | undefined)[]) => xs.filter(Boolean).join(' ');
