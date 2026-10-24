import { EdgeRow } from '../../engine/fairValue';
import { ticketStillValid } from '../../engine/tickets';
import { Controller } from '../controller';
import { DraftInput } from '../DraftInput';
import { cls, f, money, pct } from '../fmt';
import { useState } from 'preact/hooks';
import { readiness, summarize } from '../../state/readiness';

function TargetInput({ c, u, field }: { c: Controller; u: string; field: 'spot' | 'vol' }) {
  const t = c.store.s.targets[u];
  const tf = t?.[field];
  const isVol = field === 'vol';
  const shown = tf?.value == null ? '' : isVol ? (tf.value * 100).toFixed(1) : tf.value.toFixed(2);
  return (
    <DraftInput
      class={cls('num', tf && !tf.confirmed && 'amber')}
      field={`${field}-${u}`}
      value={shown}
      placeholder={isVol ? 'vol %' : 'spot'}
      title={tf ? `${tf.src}${tf.confirmed ? ' (confirmed)' : ' (suggestion: Enter or Alt+A to accept)'}` : ''}
      onCommit={(raw) => {
        const v = raw === '' ? null : Number(raw.replace('%', ''));
        c.store.setTarget(u, field, v == null || !Number.isFinite(v) ? null : v);
      }}
      onEnterUnchanged={() => c.store.acceptSuggestions()}
    />
  );
}

const STATUS_ICON: Record<string, string> = { ok: '●', warn: '▲', bad: '✖', wait: '○' };

function Readiness({ c }: { c: Controller }) {
  const { s, d, cfg } = c.store;
  const [showAll, setShowAll] = useState(false);
  const checks = readiness(s, d, cfg, d.now, s.panelProbe);
  const sum = summarize(checks);
  const shown = showAll ? checks : checks.filter((x) => x.status !== 'ok');
  return (
    <div class={cls('box', 'ready', `ready-${sum.worst}`)}>
      <div class="sec">
        <span title="live-readiness checks: symbols, quotes, spot, clock, T, positions, order form, news parse">Ready {sum.ok}/{sum.total}</span>
        {sum.worst === 'ok' && <span class="tag good">all checks pass</span>}
        {sum.worst === 'bad' && <span class="tag bad">fix the red lines before trading</span>}
        <span class="sp" />
        <button onClick={() => setShowAll(!showAll)}>{showAll ? 'hide ok' : 'show all'}</button>
      </div>
      {shown.map((x) => (
        <div class={cls('row', 'small', `chk-${x.status}`)} title={x.fix ?? ''}>
          <span class={cls('chk', `chk-${x.status}`)}>{STATUS_ICON[x.status]}</span>
          <b>{x.label}</b>
          <span>{x.detail}</span>
          {x.fix && x.status !== 'ok' && <span class="muted">→ {x.fix}</span>}
        </div>
      ))}
    </div>
  );
}

function Targets({ c }: { c: Controller }) {
  const { s, d, cfg } = c.store;
  const unds = cfg.underlyings.filter((u) => !cfg.focus || cfg.focus === u);
  return (
    <div class="box">
      <div class="sec">
        Targets
        <span class="sp" />
        <button class={cls(!d.targetsConfirmed && 'primary')} onClick={() => c.store.acceptSuggestions()} title="Alt+A">Accept (Alt+A)</button>
      </div>
      {unds.map((u) => {
        const t = s.targets[u];
        const live = d.spot[u];
        const ev = d.phase?.event?.n;
        const base = ev != null ? s.baselines[ev]?.[u] : undefined;
        const auto = s.auto.targets[u];
        const showAuto = cfg.auto.confirm && auto && auto.event === ev && (auto.status !== 'idle' || (d.phase?.phase === 'NEWS' || d.phase?.phase === 'UNDERLYING_MOVED'));
        return (
          <div class="box">
            <div class="row">
              <b>{u}</b>
              <span class="muted small">live {f(live?.value)} <span class="tag">spot: {live?.src}</span></span>
              <span class="muted small">mkt IV {pct(d.marketIV[u])}</span>
            </div>
            <div class="row">
              <span class="muted">spot</span>
              <TargetInput c={c} u={u} field="spot" />
              <span class="tag">{t?.spot.src}</span>
              {t?.spot.suggestion && <span class="amber small">new {f(t.spot.suggestion.value)} ({t.spot.suggestion.src})</span>}
            </div>
            <div class="row">
              <span class="muted">vol%</span>
              <TargetInput c={c} u={u} field="vol" />
              <span class="tag">{t?.vol.src}</span>
              {t?.vol.suggestion && <span class="amber small">new {pct(t.vol.suggestion.value)} ({t.vol.suggestion.src})</span>}
            </div>
            <div class="small muted">
              band {pct(d.effTargets[u]?.volLow)}–{pct(d.effTargets[u]?.volHigh)} {t?.bandNote ? `· ${t.bandNote}` : ''}
              {base && ` · old ${f(base.oldSpot)} / ${pct(base.oldVol)}`}
            </div>
            {showAuto && (
              <div class={cls('autoreason', auto.status === 'confirmed' ? 'ok' : 'manual')} title="auto-confirm">
                {auto.status === 'confirmed' ? `auto-confirmed: ${auto.reason}` : auto.status === 'manual' ? `needs you: ${auto.reason}` : `auto: ${auto.reason}`}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Queue({ c }: { c: Controller }) {
  const { s, d } = c.store;
  const list = s.manualQueue.length ? s.manualQueue : d.plan;
  return (
    <div class="box">
      <div class="sec">
        Ticket queue {s.manualQueue.length ? '(arb)' : ''}
        <span class="muted small">{d.plan.filter((t) => t.withinRateBudget).length} within rate budget</span>
        <span class="sp" />
        <button class={cls(c.store.cfg.priceMode === 'passive' && 'on')} title="touch = take the bid/ask; passive = rest inside the spread, never closer to fair than min edge"
          onClick={() => c.patchConfig({ priceMode: c.store.cfg.priceMode === 'passive' ? 'touch' : 'passive' })}>{c.store.cfg.priceMode}</button>
        <button class="primary" onClick={() => c.loadNext('edge')} title="Alt+N">Load next (Alt+N)</button>
      </div>
      {!d.targetsConfirmed && !s.manualQueue.length && <div class="amber small">Targets are suggestions until you accept them (Alt+A){c.store.cfg.auto.confirm ? '; auto-confirm is waiting (reasons above)' : ''}.</div>}
      {d.autoArmed && <div class="small pos">AUTO ON: tickets are {c.store.cfg.auto.submitVia === 'api' ? 'posted straight to the exchange API' : 'loaded into the form and clicked'} by the overlay. Alt+P pauses.</div>}
      <table>
        <tbody>
          {list.slice(0, 5).map((t) => {
            const ct = d.contracts[t.symbol];
            const fair = d.edges[t.underlying]?.find((r) => r.contract.symbol === t.symbol)?.fair ?? null;
            const valid = ticketStillValid(t, ct, t.source === 'edge' ? fair : null, 0);
            return (
              <tr class={cls(!valid && 'invalid', t.breach.length > 0 && 'red')} title={t.reason + (t.breach.length ? ` · breaches ${t.breach.join(', ')}` : '')}>
                <td class={t.side === 'BUY' ? 'bid' : 'ask'}>{t.side}</td>
                <td>{t.qty}</td>
                <td>{t.symbol}</td>
                <td>@{t.price}</td>
                <td>{money(t.expectedPnL)}</td>
                <td>{t.groupId ? '⛓' : ''}{!t.withinRateBudget ? '⏳' : ''}</td>
                <td>
                  <button class="primary" onClick={() => c.sendTicket(t)} title="send this order now through the exchange API (one click, no form)">send</button>
                  <button onClick={() => c.loadTicket(t)} title="prefill the page's order form instead">load</button>
                </td>
              </tr>
            );
          })}
          {!list.length && <tr><td class="muted">no ticket clears min edge {c.store.cfg.thresholds.minEdge}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function heat(e: number, minEdge: number): string {
  if (e < minEdge) return '';
  const a = Math.min(0.55, 0.12 + e / 2);
  return `rgba(43,182,115,${a.toFixed(2)})`;
}

function Bars({ r, max }: { r: EdgeRow; max: number }) {
  if (r.spotComponent == null || r.volComponent == null || !(max > 0)) return <span class="muted">—</span>;
  const w = (x: number) => `${Math.max(1, Math.round((Math.abs(x) / max) * 20))}px`;
  return (
    <span class="bars" title={`spot ${f(r.spotComponent)} · vol ${f(r.volComponent)}`}>
      <span class="bar" style={{ width: w(r.spotComponent), background: r.spotComponent >= 0 ? '#4a90d9' : '#2c5a8a' }} />
      <span class="bar" style={{ width: w(r.volComponent), background: r.volComponent >= 0 ? '#b07de0' : '#6c4a8f' }} />
    </span>
  );
}

function EdgeTable({ c, u }: { c: Controller; u: string }) {
  const { d, cfg } = c.store;
  const rows = d.edges[u] ?? [];
  if (!rows.length) return <div class="muted">{u}: no chain/targets yet</div>;
  const max = Math.max(...rows.map((r) => Math.max(Math.abs(r.spotComponent ?? 0), Math.abs(r.volComponent ?? 0))));
  const sorted = [...rows].sort((a, b) => b.robustPnL - a.robustPnL || b.robustEdge - a.robustEdge);
  return (
    <>
      <div class="sec">{u} <span class="muted small">T {f(d.T.days, 2)}d · tick {d.tick}</span></div>
      <table>
        <thead>
          <tr><th>ctr</th><th>bid</th><th>ask</th><th>fair</th><th>side</th><th>robust</th><th>qty</th><th>$PnL</th><th title="spot / vol decomposition">S|V</th></tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const k = r.contract;
            return (
              <tr style={{ background: heat(r.robustEdge, cfg.thresholds.minEdge) }} title={`${k.symbol} · edge@target ${f(r.edge, 3)} (${f(r.edgeTicks, 1)} ticks) · fair band ${f(r.fairLow)}–${f(r.fairHigh)} · Δ ${f(r.greeks.delta, 2)} vega ${f(r.greeks.vegaPerPoint, 3)}`}>
                <td>{k.kind}{k.strike}</td>
                <td class="bid">{f(k.bid)}</td>
                <td class="ask">{f(k.ask)}</td>
                <td>{f(r.fair)}</td>
                <td class={r.robustSide === 'BUY' ? 'bid' : r.robustSide === 'SELL' ? 'ask' : ''}>{r.passes ? r.robustSide : ''}</td>
                <td class={r.robustEdge >= cfg.thresholds.minEdge ? 'pos' : 'muted'}>{f(r.robustEdge)}</td>
                <td>{r.passes ? r.qty : ''}</td>
                <td>{r.passes ? money(r.robustPnL) : ''}</td>
                <td><Bars r={r} max={max} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <Structures c={c} u={u} />
    </>
  );
}

function Structures({ c, u }: { c: Controller; u: string }) {
  const { d, cfg } = c.store;
  const syn = (d.synths[u] ?? []).filter((x) => x.edge > 0).slice(0, 2);
  const str = (d.straddles[u] ?? []).filter((x) => x.edge > 0).slice(0, 2);
  if (!syn.length && !str.length) return null;
  return (
    <div class="small">
      {syn.map((x) => (
        <div class={x.edge >= cfg.thresholds.minEdge ? 'pos' : 'muted'}>
          {x.kind === 'synthLong' ? 'Buy' : 'Sell'} synthetic K{x.strike}: edge {f(x.edge)} × {x.size} (vega {f(x.vega, 3)}, Δ {f(x.delta, 2)})
        </div>
      ))}
      {str.map((x) => (
        <div class={x.edge >= cfg.thresholds.minEdge ? 'pos' : 'muted'}>
          {x.kind === 'straddleBuy' ? 'Buy' : 'Sell'} straddle K{x.strike}: edge {f(x.edge)} × {x.size} (vega {f(x.vega, 2)})
        </div>
      ))}
    </div>
  );
}

export function EdgeTab({ c }: { c: Controller }) {
  const { cfg } = c.store;
  const unds = cfg.underlyings.filter((u) => !cfg.focus || cfg.focus === u);
  return (
    <div>
      <Readiness c={c} />
      <Targets c={c} />
      <Queue c={c} />
      {unds.map((u) => <EdgeTable c={c} u={u} />)}
    </div>
  );
}
