import { useState } from 'preact/hooks';
import { guardLog, submitLog } from '../../ticket/guard';
import { Controller } from '../controller';
import { f } from '../fmt';

function pretty(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 1);
  } catch {
    return raw;
  }
}

export function CaptureTab({ c }: { c: Controller }) {
  const cap = c.store.capture;
  const [open, setOpen] = useState<string | null>(null);
  const now = Date.now();
  const kinds = [...cap.kinds.values()].sort((a, b) => b.last - a.last);
  const flagged = kinds.filter((k) => k.highlights.size);
  return (
    <div>
      <div class="row">
        <span>{cap.length} messages buffered</span>
        <span class="sp" />
        <button class="primary" onClick={() => c.downloadCapture()}>Download capture</button>
        <button onClick={() => { cap.clear(); c.store.changed(true); }}>Clear</button>
      </div>
      {flagged.length > 0 && (
        <div class="box small">
          <div class="sec">Highlights</div>
          {flagged.map((k) => <div><b>{k.key}</b> <span class="tag warn">{[...k.highlights].join(', ')}</span></div>)}
        </div>
      )}
      <table>
        <thead><tr><th>kind</th><th>count</th><th>/s</th><th>last</th></tr></thead>
        <tbody>
          {kinds.map((k) => (
            <>
              <tr style={{ cursor: 'pointer' }} onClick={() => setOpen(open === k.key ? null : k.key)}>
                <td title={k.key}>{k.key.length > 42 ? k.key.slice(0, 42) + '…' : k.key}</td>
                <td>{k.count}</td>
                <td>{f(cap.ratePerSec(k.key, now), 1)}</td>
                <td>{f((now - k.last) / 1000, 0)}s</td>
              </tr>
              {open === k.key && <tr><td colSpan={4}><pre>{pretty(k.example)}</pre></td></tr>}
            </>
          ))}
        </tbody>
      </table>
      {c.store.s.auto.log.length > 0 && (
        <div class="box small">
          <div class="sec">Auto submissions <span class="muted">({c.store.s.auto.log.length})</span></div>
          <table>
            <thead><tr><th>time</th><th>side</th><th>qty</th><th>contract</th><th>price</th><th>src</th><th>result</th></tr></thead>
            <tbody>
              {c.store.s.auto.log.slice(-25).reverse().map((l) => (
                <tr class={/REJECT/.test(l.result) ? 'red' : ''}>
                  <td>{new Date(l.t).toLocaleTimeString()}</td><td class={l.side === 'BUY' ? 'bid' : 'ask'}>{l.side}</td><td>{l.qty}</td><td>{l.symbol}</td><td>{l.price}</td><td>{l.source}</td><td>{l.result}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {submitLog.some((x) => !x.ok) && (
        <div class="box small">
          <div class="sec">Auto-submit refusals</div>
          {submitLog.filter((x) => !x.ok).slice(-10).map((g) => <div>{new Date(g.t).toLocaleTimeString()} "{g.text}" ({g.reason})</div>)}
        </div>
      )}
      {guardLog.length > 0 && (
        <div class="box small">
          <div class="sec">Guard refusals</div>
          {guardLog.slice(-10).map((g) => <div>{new Date(g.t).toLocaleTimeString()} "{g.text}" ({g.reason})</div>)}
        </div>
      )}
    </div>
  );
}
