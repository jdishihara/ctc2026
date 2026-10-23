import { Controller } from '../controller';
import { cls, f, money } from '../fmt';

export function ArbTab({ c }: { c: Controller }) {
  const { d, cfg } = c.store;
  const flags = d.arbs.filter((a) => !cfg.focus || a.underlying === cfg.focus);
  return (
    <div>
      <div class="muted small">Executable-price checks (ε = {cfg.thresholds.arbEps}). Box, monotonicity, vertical and butterfly flags are riskless; parity and IV outliers depend on the spot being right.</div>
      {!flags.length && <div class="box muted">No violations right now.</div>}
      {flags.map((a) => (
        <div class={cls('box')}>
          <div class="row">
            <span class={cls('tag', a.riskless ? 'good' : 'warn')}>{a.kind}{a.spotDependent ? ' · spot-dependent' : ''}</span>
            <b>{a.underlying}</b>
            <span class="sp" />
            <span>edge {f(a.edgePerUnit, 3)} × {a.maxSize} = {money(a.expectedPnL)}</span>
          </div>
          <div class="small">{a.description}</div>
          <div class="small muted">
            {a.legs.map((l) => `${l.side} ${l.ratio > 1 ? l.ratio + '×' : ''}${l.symbol}@${l.price}`).join(' · ')}
          </div>
          <div class="row"><span class="sp" /><button class="primary" onClick={() => c.store.queueArb(a)}>Queue tickets</button></div>
        </div>
      ))}
    </div>
  );
}
