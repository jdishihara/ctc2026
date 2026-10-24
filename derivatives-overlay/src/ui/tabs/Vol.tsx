import { useState } from 'preact/hooks';
import { AnalystId, ANALYSTS } from '../../engine/analysts';
import { contractIV } from '../../engine/chain';
import { CONVERTERS, ConverterId } from '../../engine/converters';
import { Controller } from '../controller';
import { DraftInput } from '../DraftInput';
import { cls, f, pct, signed } from '../fmt';

const CHEAT = [
  ['oil supply disruption', 'OIL ↑, OIL IV ↑, PLANE ↓'],
  ['tariff escalation', 'PLANE ↓, both IV ↑'],
  ["crash confirmed NewAir's fault", 'PLANE ↓↓, PLANE IV ↑'],
  ['NewAir cleared', 'PLANE ↑, PLANE IV ↓'],
  ['de-escalation / trade deal', 'both IV ↓'],
  ['uncertainty resolved', 'IV usually crushed, even when price jumps'],
];

function AnalystGrid({ c, ev, round }: { c: Controller; ev: number; round: number }) {
  const { s, cfg, d } = c.store;
  const unds = cfg.underlyings;
  return (
    <div class="box">
      <div class="sec">Analysts · event {ev} {round === 3 ? `(raw → σ via ${CONVERTERS.find((x) => x.id === s.converter.id)?.label})` : '(IV)'}</div>
      <table>
        <thead><tr><th></th>{unds.map((u) => <th>{u}</th>)}</tr></thead>
        <tbody>
          {ANALYSTS.map((a) => (
            <tr>
              <td>A{a}</td>
              {unds.map((u) => {
                const cell = s.analystInputs[ev]?.[u]?.[a];
                const shown = cell?.raw == null ? '' : String(cell.raw);
                return (
                  <td title={cell?.note ?? ''}>
                    <DraftInput class={cls('small', cell?.src === 'parsed' && 'amber')} value={shown} placeholder={round === 3 ? 'raw' : 'IV'}
                      onCommit={(t) => c.store.setAnalyst(ev, u, a as AnalystId, t === '' ? null : Number(t.replace('%', '')), 'typed')} />
                    <span class="small muted"> {pct(cell?.sigma)}</span>
                  </td>
                );
              })}
            </tr>
          ))}
          <tr>
            <td>blend</td>
            {unds.map((u) => {
              const b = d.blends[u];
              return <td class="small">{pct(b?.vol)} <span class="muted">[{pct(b?.low, 0)}–{pct(b?.high, 0)}]</span></td>;
            })}
          </tr>
        </tbody>
      </table>
      <div class="row small">
        <span class="muted">blend</span>
        <select value={cfg.blend.mode} onChange={(e) => c.patchConfig({ blend: { mode: (e.target as HTMLSelectElement).value } })}>
          <option value="median">median</option>
          <option value="weighted">weighted (learned)</option>
          <option value="single:1">analyst 1 only</option>
          <option value="single:2">analyst 2 only</option>
          <option value="single:3">analyst 3 only</option>
        </select>
        <span class="muted">k</span>
        <DraftInput class="small" value={String(cfg.blend.k)} onCommit={(t) => c.patchConfig({ blend: { k: Number(t) || 1 } })} />
        <span class="muted">{Object.entries(d.blends[unds[0]]?.weights ?? {}).map(([a, w]) => `A${a} ${(w as number * 100).toFixed(0)}%`).join(' ')}</span>
      </div>
    </div>
  );
}

function Accuracy({ c }: { c: Controller }) {
  const { cfg } = c.store;
  const [armed, setArmed] = useState(false);
  const pooled = c.store.analystTable();
  return (
    <div class="box">
      <div class="sec">Analyst accuracy <span class="muted small">(error = estimate − true, vol pts)</span><span class="sp" />
        <button class="danger" onClick={() => { if (armed) { c.store.resetHistory(); setArmed(false); } else setArmed(true); }} onBlur={() => setArmed(false)}>
          {armed ? 'Click again to reset' : 'Reset history'}
        </button>
      </div>
      <table>
        <thead><tr><th></th><th>n</th><th>RMSE</th><th>bias</th>{cfg.underlyings.map((u) => <th>last {u}</th>)}</tr></thead>
        <tbody>
          {ANALYSTS.map((a) => (
            <tr>
              <td>A{a}</td>
              <td>{pooled[a].n}</td>
              <td>{pooled[a].rmse == null ? '—' : f(pooled[a].rmse! * 100, 1)}</td>
              <td>{pooled[a].bias == null ? '—' : signed(pooled[a].bias! * 100, 1)}</td>
              {cfg.underlyings.map((u) => {
                const st = c.store.analystTable(u)[a];
                return <td>{st.lastErr == null ? '—' : signed(st.lastErr * 100, 1)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Converter({ c }: { c: Controller }) {
  const { s, d, cfg } = c.store;
  const conv = s.converter;
  const meta = CONVERTERS.find((x) => x.id === conv.id);
  const [probe, setProbe] = useState('');
  const u = cfg.focus ?? cfg.underlyings[0];
  const x = Number(probe);
  const out = probe && Number.isFinite(x) ? c.store.convert(3, u, x) : null;
  const ac = s.auto.converter;
  return (
    <div class="box">
      <div class="sec">Round 3 converter
        <span class="sp" />
        {cfg.auto.converter && (
          <span class={cls('tag', ac.status === 'chosen' && 'good', ac.status === 'manual' && 'warn')} title={ac.reason}>
            {ac.status === 'chosen' ? 'auto-identified' : ac.status === 'manual' ? 'manual pick' : 'auto: not identified yet'}
          </span>
        )}
        {cfg.auto.converter && <button title="forget the pick and identify again from this event's analyst messages" onClick={() => c.store.resetAutoConverter()}>re-run</button>}
      </div>
      {cfg.auto.converter && ac.reason && <div class={cls('small', ac.status === 'chosen' ? 'pos' : 'amber')}>{ac.reason}</div>}
      {cfg.auto.converter && ac.ranked.length > 0 && (
        <div class="small muted">
          {ac.ranked.slice(0, 4).map((r) => `${r.id} σ ${(r.sigma * 100).toFixed(1)}% (off ${r.errPts.toFixed(1)})${r.keyword ? ' ✓word' : ''}`).join(' · ')}
        </div>
      )}
      <div class="row">
        <select value={conv.id} onChange={(e) => c.store.setConverter({ id: (e.target as HTMLSelectElement).value as ConverterId })}>
          {CONVERTERS.map((k) => <option value={k.id}>{k.label}</option>)}
        </select>
        {meta?.needsK || conv.id === 'atmStraddle' ? (
          <>
            <span class="muted">K</span>
            <DraftInput class="small" value={conv.K == null ? '' : String(conv.K)} placeholder="ATM" onCommit={(t) => c.store.setConverter({ K: t === '' ? null : Number(t) })} />
          </>
        ) : null}
      </div>
      {conv.id === 'custom' && (
        <div class="row">
          <span class="muted">σ =</span>
          <DraftInput value={conv.formula} width="220px" onCommit={(t) => c.store.setConverter({ formula: t })} title="variables: x S T K · functions: sqrt ln log exp abs min max normcdf norminv" />
        </div>
      )}
      <div class="row small">
        <span class="muted">try x =</span>
        <DraftInput class="small" value={probe} onCommit={setProbe} />
        <span>→ σ {pct(out?.sigma ?? null)} {out?.note ? <span class="muted">({out.note})</span> : null}</span>
        <span class="muted">S {f(d.effTargets[u]?.spot)} T {f(d.T.years, 4)}</span>
      </div>
    </div>
  );
}

function Smile({ c }: { c: Controller }) {
  const { d, cfg } = c.store;
  return (
    <div class="box">
      <div class="sec">Market IV per contract</div>
      <table>
        <thead><tr><th>und</th><th>K</th><th>call bid/mid/ask</th><th>put bid/mid/ask</th></tr></thead>
        <tbody>
          {cfg.underlyings.flatMap((u) => {
            const ch = d.chains[u];
            const S = d.spot[u]?.value;
            if (!ch || S == null) return [];
            return ch.rows.map((r) => {
              const ci = r.call ? contractIV(r.call, S, d.T.years) : null;
              const pi = r.put ? contractIV(r.put, S, d.T.years) : null;
              const t = (x: typeof ci) => (x ? `${pct(x.bid, 0)} / ${pct(x.mid, 1)} / ${pct(x.ask, 0)}` : '—');
              return <tr><td>{u}</td><td>{r.strike}</td><td>{t(ci)}</td><td>{t(pi)}</td></tr>;
            });
          })}
        </tbody>
      </table>
      <div class="small muted">{cfg.underlyings.map((u) => `${u} median ${pct(d.marketIV[u])}`).join(' · ')}</div>
    </div>
  );
}

export function VolTab({ c }: { c: Controller }) {
  const { s, d } = c.store;
  const ev = d.phase?.event?.n ?? null;
  const round = d.round ?? 1;
  const evNews = s.news.filter((n) => n.event === ev);
  return (
    <div>
      {round === 1 && (
        <div class="box">
          <div class="sec">Round 1: announced</div>
          {evNews.length === 0 && <div class="muted">No news for this event yet.</div>}
          {evNews.map((n) => (
            <div class="small">
              <div>{n.text}</div>
              <div class="muted">
                {Object.entries(n.parse.underlyings).map(([u, p]) => `${u}: spot ${f(p.spot ?? null)}${p.iv != null ? `, IV ${pct(p.iv)} (read "${p.ivRaw}")` : ''}`).join(' · ') || 'nothing parsed'}
              </div>
            </div>
          ))}
        </div>
      )}
      {ev != null && round >= 2 && <AnalystGrid c={c} ev={ev} round={round} />}
      {round === 3 && <Converter c={c} />}
      <Accuracy c={c} />
      <Smile c={c} />
      <details open={s.ui.showCheat} onToggle={(e) => { s.ui.showCheat = (e.currentTarget as HTMLDetailsElement).open; }}>
        <summary>Qualitative prior cheat sheet</summary>
        <table><tbody>{CHEAT.map(([k, v]) => <tr><td>{k}</td><td>{v}</td></tr>)}</tbody></table>
      </details>
      {round < 3 && (
        <details>
          <summary>Converter (Round 3 tool, usable any time)</summary>
          <Converter c={c} />
        </details>
      )}
    </div>
  );
}
