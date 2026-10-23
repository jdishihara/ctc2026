import { render } from 'preact';
import { useEffect, useRef, useState } from 'preact/hooks';
import { Tab, TABS } from '../state/store';
import { Controller, ticketText } from './controller';
import { cls, f, money } from './fmt';
import { Header } from './Header';
import { ArbTab } from './tabs/Arb';
import { CaptureTab } from './tabs/Capture';
import { ConfigTab } from './tabs/Config';
import { EdgeTab } from './tabs/Edge';
import { RiskTab } from './tabs/Risk';
import { TimelineTab } from './tabs/Timeline';
import { VolTab } from './tabs/Vol';

/** Re-render at most 5 times per second. */
function useThrottledStore(c: Controller) {
  const [, setN] = useState(0);
  useEffect(() => {
    let pending = false;
    let last = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const fire = () => {
      pending = false;
      last = Date.now();
      setN((n) => n + 1);
    };
    const unsub = c.store.subscribe(() => {
      if (pending) return;
      pending = true;
      const wait = Math.max(0, 200 - (Date.now() - last));
      timer = setTimeout(fire, wait);
    });
    return () => {
      unsub();
      if (timer) clearTimeout(timer);
    };
  }, [c]);
}

function TicketCard({ c }: { c: Controller }) {
  const l = c.store.s.loaded;
  if (!l) return null;
  const t = l.ticket;
  const age = (Date.now() - l.t) / 1000;
  if (age > 45) return null;
  return (
    <div class={cls('ticket', l.ok === true && 'ok', l.ok === false && 'fail')}>
      <div class="row">
        <b class={t.side === 'BUY' ? 'bid' : 'ask'}>{t.side}</b>
        <b>{t.qty}</b>
        <b>{t.symbol}</b>
        <span>@ {t.price}</span>
        <span class="sp" />
        <button onClick={() => c.copy(ticketText(t))}>copy</button>
      </div>
      <div class="small muted">{t.reason}{t.groupId ? ' · linked leg' : ''} · exp {money(t.expectedPnL)}</div>
      <div class={cls('small', l.ok === false && 'err', l.ok === true && 'pos')}>{l.message}</div>
    </div>
  );
}

export function App({ c }: { c: Controller }) {
  useThrottledStore(c);
  const { s, d } = c.store;
  const ui = s.ui;
  const rootRef = useRef<HTMLDivElement>(null);

  const onDragStart = (e: PointerEvent) => {
    const tgt = e.target as HTMLElement;
    if (tgt.closest('button,select,input')) return;
    const el = rootRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const ox = e.clientX - r.left;
    const oy = e.clientY - r.top;
    const move = (ev: PointerEvent) => {
      ui.x = Math.max(0, Math.min(window.innerWidth - 60, ev.clientX - ox));
      ui.y = Math.max(0, Math.min(window.innerHeight - 30, ev.clientY - oy));
      el.style.left = `${ui.x}px`;
      el.style.top = `${ui.y}px`;
      el.style.bottom = 'auto';
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      c.saveUi();
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  if (ui.hidden) {
    return <div class="badge" onClick={() => { ui.hidden = false; c.saveUi(); c.store.changed(true); }}>Δ overlay (Alt+O)</div>;
  }
  const captureOnly = d.mode === 'capture-only';
  if (captureOnly && !ui.captureOpen) {
    return <div class="badge" title={d.modeReason} onClick={() => { ui.captureOpen = true; ui.collapsed = false; c.store.changed(true); }}>Overlay: capture only</div>;
  }
  const pos = ui.x != null && ui.y != null ? { left: `${ui.x}px`, top: `${ui.y}px` } : { left: '12px', bottom: '12px' };
  const tabs: Tab[] = captureOnly ? ['Capture', 'Config'] : TABS;
  const tab = tabs.includes(ui.tab) ? ui.tab : tabs[0];
  const setTab = (t: Tab) => {
    ui.tab = t;
    c.saveUi();
    c.store.changed(true);
  };
  const breach = d.breaches[0];
  return (
    <div class={cls('root', ui.collapsed && 'collapsed')} style={pos} ref={rootRef}>
      <Header c={c} onDragStart={onDragStart} />
      {d.flattenNow && <div class="banner flat">FLATTEN NOW · Alt+F</div>}
      {breach && <div class="banner breach">CAP BREACH: {breach.underlying} {breach.what} {f(breach.value, 0)} (cap {breach.cap})</div>}
      {s.toast && <div class={`banner toast-${s.toast.level}`}>{s.toast.text}</div>}
      <TicketCard c={c} />
      {!ui.collapsed && (
        <>
          <div class="tabs">
            {tabs.map((t) => (
              <button class={cls(tab === t && 'on')} onClick={() => setTab(t)}>{t}</button>
            ))}
            <span class="sp" />
            <button class={cls(ui.pinned && 'on')} title="Pin tab: stop auto-switching on phase changes" onClick={() => { ui.pinned = !ui.pinned; c.saveUi(); c.store.changed(true); }}>📌</button>
          </div>
          <div class="body">
            {tab === 'Edge' && <EdgeTab c={c} />}
            {tab === 'Arb' && <ArbTab c={c} />}
            {tab === 'Vol' && <VolTab c={c} />}
            {tab === 'Risk' && <RiskTab c={c} />}
            {tab === 'Timeline' && <TimelineTab c={c} />}
            {tab === 'Capture' && <CaptureTab c={c} />}
            {tab === 'Config' && <ConfigTab c={c} />}
          </div>
        </>
      )}
    </div>
  );
}

export function mountApp(c: Controller, container: Element): void {
  render(<App c={c} />, container);
}
