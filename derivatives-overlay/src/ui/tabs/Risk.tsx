import { useState } from 'preact/hooks';
import { Controller } from '../controller';
import { cls, f, money } from '../fmt';

export function RiskTab({ c }: { c: Controller }) {
  const { s, d, cfg } = c.store;
  const pf = d.portfolio;
  const th = cfg.thresholds;
  const [manual, setManual] = useState('');
  const fills = s.fills.slice(-50);
  const atMid = fills.filter((x) => x.atMid === true).length;
  const known = fills.filter((x) => x.atMid != null).length;
  return (
    <div>
      <div class="box">
        <div class="sec">Greeks at targets</div>
        <table>
          <thead><tr><th></th><th>Δ</th><th>Γ</th><th>vega/pt</th><th>θ/day</th><th>±1 spot</th><th>±5 vol</th></tr></thead>
          <tbody>
            {[...Object.entries(pf.perUnderlying), ['TOTAL', pf.total] as const].map(([u, b]) => (
              <tr>
                <td>{u}</td>
                <td class={cls(u !== 'TOTAL' && Math.abs(b.delta) > th.maxAbsDeltaPerUnderlying && 'red')}>{f(b.delta, 1)}</td>
                <td>{f(b.gamma, 2)}</td>
                <td class={cls(u !== 'TOTAL' && Math.abs(b.vega) > th.maxAbsVegaPts && 'red')}>{f(b.vega, 1)}</td>
                <td>{f(b.theta, 1)}</td>
                <td>{money(b.dollarDeltaUp)} / {money(b.dollarDeltaDown)}</td>
                <td>±{money(Math.abs(b.vega5))}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div class="small muted">caps: |Δ| ≤ {th.maxAbsDeltaPerUnderlying} and |vega| ≤ {th.maxAbsVegaPts} per underlying</div>
      </div>
      <div class="box">
        <div class="sec">Flatten queue <span class="muted small">spread cost {money(d.flattenCost)}</span><span class="sp" />
          <button class="primary" onClick={() => c.loadNext('flatten')}>Load next (Alt+F)</button>
        </div>
        <table>
          <tbody>
            {d.flatten.slice(0, 8).map((t) => (
              <tr title={t.reason}>
                <td class={t.side === 'BUY' ? 'bid' : 'ask'}>{t.side}</td><td>{t.qty}</td><td>{t.symbol}</td><td>@{t.price}</td>
                <td>{t.groupId ? '⛓' : ''}</td><td><button onClick={() => c.loadTicket(t)}>load</button></td>
              </tr>
            ))}
            {!d.flatten.length && <tr><td class="muted">flat</td></tr>}
          </tbody>
        </table>
      </div>
      <div class="box">
        <div class="sec">Positions <span class="tag">{s.positionsSrc ?? 'none'}</span>
          <span class="muted small">{s.positionsAt ? `${f((d.now - s.positionsAt) / 1000, 0)}s ago` : ''}</span>
        </div>
        <table>
          <thead><tr><th>contract</th><th>qty</th><th>resting b/s</th><th>fair</th><th>mark</th><th>Δ</th><th>vega</th></tr></thead>
          <tbody>
            {pf.rows.map((r) => (
              <tr>
                <td>{r.symbol}</td><td class={r.qty > 0 ? 'pos' : 'neg'}>{r.qty}</td>
                <td>{s.resting[r.symbol] ? `${s.resting[r.symbol].buy}/${s.resting[r.symbol].sell}` : ''}</td>
                <td>{f(r.fair)}</td><td>{f(r.mark)}</td><td>{f(r.delta, 1)}</td><td>{f(r.vega, 1)}</td>
              </tr>
            ))}
            {!pf.rows.length && <tr><td class="muted">no open positions</td></tr>}
          </tbody>
        </table>
        <details>
          <summary>Manual positions (fallback)</summary>
          <div class="small muted">JSON like {'{"OIL_0626_C100": 50}'}; empty clears.</div>
          <textarea style={{ width: '100%', height: '50px' }} value={manual} onInput={(e) => setManual((e.currentTarget as HTMLTextAreaElement).value)} />
          <button onClick={() => {
            if (!manual.trim()) return c.store.setManualPositions(null);
            try { c.store.setManualPositions(JSON.parse(manual)); } catch { c.store.toast('manual positions: invalid JSON', 'error'); }
          }}>Apply</button>
        </details>
      </div>
      <div class="box small">
        <div class="sec">Fills vs quote</div>
        {known ? <div>{atMid}/{known} recent fills were at the quoted mid ({fills.length - atMid} elsewhere): {atMid / known > 0.5 ? 'midpoint execution looks real' : 'fills look like touch prices'}</div> : <div class="muted">no fills observed yet</div>}
      </div>
    </div>
  );
}
