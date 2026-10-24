import { Controller } from './controller';
import { cls, f, mmss } from './fmt';

const NEXT_LABEL: Record<string, string> = { NEWS: 'NEWS IN', UNDERLYING_MOVED: 'MOVE IN', SNAPPED: 'SNAP IN', CLOSED: 'CLOSE IN', ENDED: 'END IN' };

export function Header({ c, onDragStart }: { c: Controller; onDragStart: (e: PointerEvent) => void }) {
  const { s, d, cfg } = c.store;
  const ph = d.phase;
  const ev = ph?.event;
  const label = ph?.nextPhase ? NEXT_LABEL[ph.nextPhase] ?? `${ph.nextPhase} IN` : '';
  const hot = d.realToNext != null && d.realToNext < 15;
  const rate = d.rate;
  const qa = d.quoteAge;
  const autoOn = cfg.auto.submit;
  const paused = s.auto.paused;
  return (
    <div class="hdr" onPointerDown={(e) => onDragStart(e as unknown as PointerEvent)}>
      <div class="hrow">
        <span class="title">Δ Overlay</span>
        <span class="tag">{d.mode === 'derivatives' ? 'DERIVATIVES' : 'CAPTURE ONLY'}</span>
        {d.replay && <span class="tag warn">REPLAY</span>}
        {autoOn && d.mode === 'derivatives' && (
          <span class={cls('autobadge', paused ? 'paused' : 'live')} title={cfg.auto.submitVia === 'api' ? 'auto-submit: the overlay posts orders to the exchange API itself. Alt+P pauses.' : 'auto-submit: the overlay clicks the submit button itself. Alt+P pauses.'}>
            {paused ? 'AUTO PAUSED' : 'AUTO ON'}
          </span>
        )}
        <span class="muted small" title={d.modeReason}>{s.caseName ?? ''}</span>
        <span class="sp" />
        <button title="Collapse" onClick={(e) => { e.stopPropagation(); s.ui.collapsed = !s.ui.collapsed; c.saveUi(); c.store.changed(true); }}>{s.ui.collapsed ? '▢' : '—'}</button>
        <button title="Hide (Alt+O)" onClick={(e) => { e.stopPropagation(); if (d.mode === 'capture-only') s.ui.captureOpen = false; else s.ui.hidden = true; c.saveUi(); c.store.changed(true); }}>×</button>
      </div>
      <div class="hrow">
        <span>{ev ? `E${ev.n} · R${ev.round}` : 'no event'}</span>
        <span class={cls('tag', ph?.phase === 'NEWS' && 'warn', ph?.phase === 'SNAPPED' && 'good')}>{ph?.phase ?? '—'}</span>
        <span class={cls('count', hot && 'hot')}>{label} {mmss(d.realToNext)}</span>
        <span class="sp" />
        <span class={cls('tag', d.clockStale && 'bad')} title="clock source">clk {d.clockSrc}{d.clockStale ? ' stale' : ''}</span>
      </div>
      <div class="hrow small">
        <span class="tag" title="time to expiry and its source">T {f(d.T.days, 2)}d · {d.T.src}{d.r ? ` · r ${(d.r * 100).toFixed(2)}%` : ''}</span>
        <span class={cls('tag', rate.level === 'amber' && 'warn', rate.level === 'red' && 'bad')} title="observed order actions in the last 60 s">orders {rate.used}/{rate.limit}</span>
        <span class={cls('tag', (qa == null || qa > cfg.thresholds.staleQuoteSec) && 'bad')}>quotes {qa == null ? '—' : `${f(qa, 1)}s`}</span>
        <span class={cls('tag', cfg.auto.confirm ? 'good' : 'warn')} title="auto-confirm: parsed targets are accepted without Alt+A when complete and sane">confirm {cfg.auto.confirm ? 'auto' : 'manual'}</span>
        <button class={cls('autobtn', autoOn && 'on')} onPointerDown={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); c.setAutoSubmit(!autoOn); }}
          title={autoOn ? 'Disarm: back to Alt+N and clicking by hand' : 'Arm auto-submit: the overlay loads and submits tickets itself (Alt+P pauses)'}>
          {autoOn ? 'disarm' : 'arm auto'}
        </button>
        <span class="sp" />
        <select value={cfg.focus ?? ''} onPointerDown={(e) => e.stopPropagation()} onChange={(e) => c.patchConfig({ focus: (e.target as HTMLSelectElement).value || null })} title="focus underlying">
          <option value="">both</option>
          {cfg.underlyings.map((u) => <option value={u}>{u}</option>)}
        </select>
      </div>
    </div>
  );
}
