// Event schedule and phase logic. All times are naive exchange time.
import { dayStart, fmtDate, hmsToSec, parseNaiveSec, secOfDay } from './tradingTime';

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
