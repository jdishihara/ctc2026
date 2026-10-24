// Event schedule and phase logic. All times are naive exchange time.
import { dayStart, fmtDate, hmsToSec, isWeekday, parseNaiveSec, secOfDay } from './tradingTime';

export interface EventSpec {
  n: number;
  date: string; // YYYY-MM-DD
  news: string; // HH:MM[:SS]
  move: string;
  snap: string;
  round: 1 | 2 | 3;
}

export type Phase = 'WAITING' | 'NEWS' | 'UNDERLYING_MOVED' | 'SNAPPED' | 'ENDED' | 'CLOSED';

export const DEFAULT_SCHEDULE: EventSpec[] = [
  { n: 1, date: '2026-06-01', news: '09:30:00', move: '10:22:00', snap: '11:14:00', round: 1 },
  { n: 2, date: '2026-06-01', news: '11:40:00', move: '12:32:00', snap: '13:24:00', round: 1 },
  { n: 3, date: '2026-06-01', news: '13:50:00', move: '14:42:00', snap: '15:34:00', round: 1 },
  { n: 4, date: '2026-06-02', news: '09:30:00', move: '10:22:00', snap: '11:14:00', round: 2 },
  { n: 5, date: '2026-06-02', news: '11:40:00', move: '12:32:00', snap: '13:24:00', round: 2 },
  { n: 6, date: '2026-06-02', news: '13:50:00', move: '14:42:00', snap: '15:34:00', round: 2 },
  { n: 7, date: '2026-06-03', news: '09:30:00', move: '10:09:00', snap: '10:48:00', round: 3 },
  { n: 8, date: '2026-06-03', news: '11:07:30', move: '11:46:30', snap: '12:25:30', round: 3 },
  { n: 9, date: '2026-06-03', news: '12:45:00', move: '13:24:00', snap: '14:03:00', round: 3 },
  { n: 10, date: '2026-06-03', news: '14:22:30', move: '15:01:30', snap: '15:40:30', round: 3 },
];

export interface PhaseInfo {
  event: EventSpec | null;
  phase: Phase;
  nextPhase: Phase | null;
  simSecondsToNext: number | null;
  replay: boolean;
  /** seconds since the current phase began (exchange time) */
  simSecondsInPhase: number | null;
}

export interface PhaseOpts {
  open?: string;
  close?: string;
}

/**
 * Phase at a naive exchange time. When the date is not on the schedule (testnet replays with 1800-xx-xx dates),
 * time of day is matched against the first scheduled day and `replay` is set.
 */
export function phaseAt(nowSec: number, schedule: EventSpec[] = DEFAULT_SCHEDULE, opts: PhaseOpts = {}): PhaseInfo {
  const open = hmsToSec(opts.open ?? '09:30');
  const close = hmsToSec(opts.close ?? '16:00');
  const dates = [...new Set(schedule.map((e) => e.date))].sort();
  const date = fmtDate(nowSec);
  const tod = secOfDay(nowSec);
  let replay = false;
  let dayEvents = schedule.filter((e) => e.date === date);
  if (!dayEvents.length) {
    const first = dates[0];
    const last = dates[dates.length - 1];
    if (first && date > first && date <= last) {
      // a scheduled-period day with no events (should not happen with the packet schedule)
      return { event: null, phase: 'CLOSED', nextPhase: null, simSecondsToNext: null, replay, simSecondsInPhase: null };
    }
    if (first && date > last && date < '2100-01-01' && date >= '2026-01-01') {
      return { event: schedule[schedule.length - 1] ?? null, phase: 'ENDED', nextPhase: null, simSecondsToNext: null, replay, simSecondsInPhase: null };
    }
    if (first && date < first && date >= '2026-01-01') {
      return { event: null, phase: 'CLOSED', nextPhase: 'NEWS', simSecondsToNext: null, replay, simSecondsInPhase: null };
    }
    replay = true;
    dayEvents = schedule.filter((e) => e.date === first);
  }
  const ev = [...dayEvents].sort((a, b) => hmsToSec(a.news) - hmsToSec(b.news));
  const isLastDay = !replay && date === dates[dates.length - 1];
  if (!ev.length) return { event: null, phase: 'CLOSED', nextPhase: null, simSecondsToNext: null, replay, simSecondsInPhase: null };

  const firstNews = hmsToSec(ev[0].news);
  if (tod < Math.min(open, firstNews)) {
    return { event: ev[0], phase: 'CLOSED', nextPhase: 'NEWS', simSecondsToNext: firstNews - tod, replay, simSecondsInPhase: null };
  }
  if (tod >= close) {
    const lastEv = ev[ev.length - 1];
    const ended = isLastDay || (!replay && lastEv.n === Math.max(...schedule.map((e) => e.n)));
    return { event: lastEv, phase: ended ? 'ENDED' : 'CLOSED', nextPhase: ended ? null : 'NEWS', simSecondsToNext: null, replay, simSecondsInPhase: tod - close };
  }
  if (tod < firstNews) {
    return { event: ev[0], phase: 'WAITING', nextPhase: 'NEWS', simSecondsToNext: firstNews - tod, replay, simSecondsInPhase: tod - open };
  }
  let i = 0;
  while (i + 1 < ev.length && hmsToSec(ev[i + 1].news) <= tod) i++;
  const e = ev[i];
  const news = hmsToSec(e.news);
  const move = hmsToSec(e.move);
  const snap = hmsToSec(e.snap);
  if (tod < move) return { event: e, phase: 'NEWS', nextPhase: 'UNDERLYING_MOVED', simSecondsToNext: move - tod, replay, simSecondsInPhase: tod - news };
  if (tod < snap) return { event: e, phase: 'UNDERLYING_MOVED', nextPhase: 'SNAPPED', simSecondsToNext: snap - tod, replay, simSecondsInPhase: tod - move };
  const next = ev[i + 1];
  if (next) return { event: e, phase: 'SNAPPED', nextPhase: 'NEWS', simSecondsToNext: hmsToSec(next.news) - tod, replay, simSecondsInPhase: tod - snap };
  return { event: e, phase: 'SNAPPED', nextPhase: isLastDay ? 'ENDED' : 'CLOSED', simSecondsToNext: close - tod, replay, simSecondsInPhase: tod - snap };
}

/**
 * Rebase the schedule onto the exchange's own dates. The live exchange runs a case on fictional dates of its choosing
 * (the testnet's Hurricane ran on 2026-08-03); the packet fixes only the layout: three 6.5 h trading days, ten events.
 * `elapsedActiveSec` (GET /competitions/current `elapsed_active_seconds`) says how far into the case we are; with the
 * schedule's own per-day real duration (fictional day length / that day's clock rate) it picks the day index, and every
 * date is shifted so that today is that day. Returns null when today is already a scheduled date (nothing to do).
 * Without `elapsedActiveSec` today is taken as day 1 (the case start is when a new date is first seen).
 */
export function rebaseSchedule(
  schedule: EventSpec[], nowSec: number, elapsedActiveSec: number | null, rates: { rounds12: number; round3: number }, opts: PhaseOpts = {},
): EventSpec[] | null {
  const dates = [...new Set(schedule.map((e) => e.date))].sort();
  const today = fmtDate(nowSec);
  if (!dates.length || dates.includes(today)) return null;
  const dayLen = hmsToSec(opts.close ?? '16:00') - hmsToSec(opts.open ?? '09:30');
  const realPerDay = dates.map((d) => {
    const round = schedule.find((e) => e.date === d)?.round ?? 1;
    const rate = round === 3 ? rates.round3 : rates.rounds12;
    return rate > 0 ? dayLen / rate : Infinity;
  });
  let idx = 0;
  if (elapsedActiveSec != null && elapsedActiveSec > 0) {
    let cum = 0;
    for (idx = 0; idx < dates.length - 1; idx++) {
      cum += realPerDay[idx];
      if (elapsedActiveSec < cum) break;
    }
  }
  // trading days around today (weekends skipped; the exchange's calendar is unknown, so this is re-done if a later date is off)
  const step = (sec: number, dir: 1 | -1): number => {
    let d = sec + dir * 86400;
    while (!isWeekday(d)) d += dir * 86400;
    return d;
  };
  const todaySec = dayStart(nowSec);
  const newDates: string[] = new Array(dates.length);
  newDates[idx] = today;
  for (let i = idx - 1, d = todaySec; i >= 0; i--) { d = step(d, -1); newDates[i] = fmtDate(d); }
  for (let i = idx + 1, d = todaySec; i < dates.length; i++) { d = step(d, 1); newDates[i] = fmtDate(d); }
  return schedule.map((e) => ({ ...e, date: newDates[dates.indexOf(e.date)] ?? e.date }));
}

/** the clock rate the packet layout implies for a day: the whole session divided over that day's evenly spaced events */
export function packetRateForDate(schedule: EventSpec[], date: string, rates: { rounds12: number; round3: number }): number | null {
  const e = schedule.find((x) => x.date === date);
  if (!e) return null;
  return e.round === 3 ? rates.round3 : rates.rounds12;
}

/**
 * The move and snap boundaries are real-time offsets from the news (packet: +1 min, +2 min). The schedule's fictional
 * times assume the packet's clock rate; when the exchange runs a different rate today, recompute today's move/snap from
 * the live rate. Returns the same array when nothing changes (rate within 5 % of the packet's, or no events today).
 */
export function withLiveRate(
  schedule: EventSpec[], liveRate: number, date: string, offsets: { move: number; snap: number }, rates: { rounds12: number; round3: number },
): EventSpec[] {
  const packet = packetRateForDate(schedule, date, rates);
  if (!(liveRate > 0) || packet == null || Math.abs(liveRate / packet - 1) < 0.05) return schedule;
  const hms = (sec: number) => {
    const s = Math.round(sec);
    return `${String(Math.floor(s / 3600)).padStart(2, '0')}:${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  };
  return schedule.map((e) => {
    if (e.date !== date) return e;
    const news = hmsToSec(e.news);
    return { ...e, move: hms(news + offsets.move * liveRate), snap: hms(news + offsets.snap * liveRate) };
  });
}

export function realSecondsToNext(info: PhaseInfo, clockRate: number): number | null {
  if (info.simSecondsToNext == null || !(clockRate > 0)) return null;
  return info.simSecondsToNext / clockRate;
}

/** Exchange-time (naive seconds) of an event boundary. */
export function eventTimeSec(e: EventSpec, which: 'news' | 'move' | 'snap'): number {
  return (parseNaiveSec(e.date + 'T00:00:00') ?? 0) + hmsToSec(e[which]);
}

export function roundOfEvent(n: number, schedule: EventSpec[] = DEFAULT_SCHEDULE): 1 | 2 | 3 | null {
  return schedule.find((e) => e.n === n)?.round ?? null;
}

export { dayStart };
