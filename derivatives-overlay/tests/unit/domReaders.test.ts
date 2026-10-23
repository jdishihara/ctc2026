// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { DEFAULT_CONFIG } from '../../src/core/config';
import { findChain, readFairT, readHeaderClock, readLatest, readPositions, readSpot } from '../../src/core/dom-readers';
import { compileSymbolRegex, DEFAULT_OPTION_REGEX } from '../../src/engine/chain';
import { fillChain, loadMockMarkup } from '../helpers/mockPage';

const hints = DEFAULT_CONFIG.dom;

describe('DOM readers (by visible text)', () => {
  beforeEach(() => {
    loadMockMarkup();
    fillChain(document, [
      { K: 60, c: [12, 40.0, 40.2, 15], p: [10, 0.01, 0.05, 5] },
      { K: 100, c: [10, 5.45, 5.66, 20], p: [11, 5.5, 5.7, 30] },
      { K: 140, c: [8, 0.01, 0.06, 9], p: [7, 40.0, 40.3, 11] },
    ]);
  });
  it('reads the chain with column mapping from the header labels', () => {
    const ch = findChain(document.body, hints)!;
    expect(ch.rows.map((r) => r.strike)).toEqual([60, 100, 140]);
    const r = ch.rows[1];
    expect([r.C.bidSize.value, r.C.bid.value, r.C.ask.value, r.C.askSize.value]).toEqual([10, 5.45, 5.66, 20]);
    expect([r.P.bidSize.value, r.P.bid.value, r.P.ask.value, r.P.askSize.value]).toEqual([11, 5.5, 5.7, 30]);
  });
  it('reads spot, header clock, LATEST, Fair-tab T (only when visible) and positions', () => {
    document.querySelector('.spot')!.textContent = '99.89';
    expect(readSpot(document.body, hints)).toBe(99.89);
    document.querySelector('.time')!.textContent = '10:22:05';
    expect(readHeaderClock(document.body, hints)).toBe(10 * 3600 + 22 * 60 + 5);
    document.querySelector('.ltime')!.textContent = '09:30:00';
    document.querySelector('.ltext')!.textContent = 'OIL jumps to 104.20; implied vol now 62%';
    document.querySelector('.learlier')!.textContent = '3 earlier';
    expect(readLatest(document.body, hints)).toBe('OIL jumps to 104.20; implied vol now 62%');
    document.querySelector('.ft')!.textContent = '0.0794 yr (20.00 trading days)';
    expect(readFairT(document.body, hints)).toBeNull(); // Fair tab hidden
    document.querySelector('.fairbody')!.classList.remove('hidden');
    expect(readFairT(document.body, hints)).toEqual({ years: 0.0794, days: 20 });
    document.querySelector('.positions')!.innerHTML = '<div class="item"><span>OIL_0626_C100</span><span>+50</span><span>@ 5.66</span></div><div class="item"><span>PLANE_0626_P40</span><span>-25</span><span>@ 3.10</span></div>';
    expect(readPositions(document.body, hints, compileSymbolRegex(DEFAULT_OPTION_REGEX))).toEqual({ OIL_0626_C100: 50, PLANE_0626_P40: -25 });
  });
  it('div-grid chains work too', () => {
    document.body.innerHTML = `<div><div class="h"><span>BID SZ</span><span>BID</span><span>ASK</span><span>ASK SZ</span><span>STRIKE</span><span>BID SZ</span><span>BID</span><span>ASK</span><span>ASK SZ</span></div>
      <div class="rows"><div><i>3</i><i>1.10</i><i>1.20</i><i>4</i><i>40</i><i>5</i><i>1.30</i><i>1.40</i><i>6</i></div></div></div>`;
    const ch = findChain(document.body, hints)!;
    expect(ch.rows[0].strike).toBe(40);
    expect(ch.rows[0].P.ask.value).toBe(1.4);
  });
});
