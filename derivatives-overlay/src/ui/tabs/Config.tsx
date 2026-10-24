import { useState } from 'preact/hooks';
import { Controller } from '../controller';

export function ConfigTab({ c }: { c: Controller }) {
  const cfg = c.store.cfg;
  const [text, setText] = useState(() => JSON.stringify(cfg, null, 2));
  const [msg, setMsg] = useState<{ ok: boolean; lines: string[] } | null>(null);
  const [armed, setArmed] = useState(false);
  return (
    <div>
      <div class="box">
        <div class="sec">Safety</div>
        <label class="row"><input type="checkbox" checked={cfg.prefillEnabled} onChange={(e) => c.patchConfig({ prefillEnabled: (e.currentTarget as HTMLInputElement).checked })} /> Prefill the order form (off = copyable ticket cards only)</label>
        <div class="row">
          <span>mode</span>
          <select value={cfg.mode} onChange={(e) => c.patchConfig({ mode: (e.currentTarget as HTMLSelectElement).value })}>
            <option value="auto">auto</option><option value="derivatives">derivatives</option><option value="capture-only">capture-only</option>
          </select>
          <span>T</span>
          <select value={cfg.T_mode} onChange={(e) => c.patchConfig({ T_mode: (e.currentTarget as HTMLSelectElement).value })}>
            <option value="dom">dom (Fair tab)</option><option value="computed">computed</option><option value="fixed20">fixed 20d</option><option value="manual">manual</option>
          </select>
          <span>price</span>
          <select value={cfg.priceMode} onChange={(e) => c.patchConfig({ priceMode: (e.currentTarget as HTMLSelectElement).value })}>
            <option value="touch">touch</option><option value="passive">passive</option>
          </select>
        </div>
        <label class="row"><input type="checkbox" checked={cfg.auto.confirm} onChange={(e) => c.patchConfig({ auto: { confirm: (e.currentTarget as HTMLInputElement).checked } })} /> Auto-confirm parsed targets (complete parse within the sanity bounds; otherwise amber as before)</label>
        <label class="row"><input type="checkbox" checked={cfg.auto.converter} onChange={(e) => c.patchConfig({ auto: { converter: (e.currentTarget as HTMLInputElement).checked } })} /> Round 3: identify the IV-linked quantity automatically</label>
        <label class="row"><input type="checkbox" checked={cfg.auto.submit} onChange={(e) => c.setAutoSubmit((e.currentTarget as HTMLInputElement).checked)} /> <b>Auto-submit</b>: load, verify and click the submit button for each ticket (Alt+P pauses). Off by default; turn on only if the organisers allow a bot to submit.</label>
        <div class="small muted">With auto-submit off the overlay never submits orders, never clicks Buy/Sell/confirm buttons and never sends network requests of its own. With it on, the only extra clicks are the order form's own submit button, after the form was verified to hold the loaded ticket, and the OIL/PLANE product tab.</div>
      </div>
      <div class="row">
        <button onClick={() => { setText(JSON.stringify(c.store.cfg, null, 2)); setMsg(null); }}>Reload current</button>
        <button onClick={() => {
          try {
            JSON.parse(text);
          } catch (e) {
            return setMsg({ ok: false, lines: [String(e)] });
          }
          const r = c.saveConfig(text);
          setMsg({ ok: r.ok, lines: r.ok ? ['Saved and applied.'] : r.errors });
          if (r.ok) setText(JSON.stringify(r.config, null, 2));
        }} class="primary">Validate &amp; save</button>
        <button class="danger" onClick={() => {
          if (!armed) return setArmed(true);
          setArmed(false);
          c.resetConfig();
          setText(JSON.stringify(c.store.cfg, null, 2));
          setMsg({ ok: true, lines: ['Defaults restored.'] });
        }}>{armed ? 'Click again to reset' : 'Reset to defaults'}</button>
      </div>
      {msg && <div class={msg.ok ? 'pos small' : 'err small'}>{msg.lines.map((l) => <div>{l}</div>)}</div>}
      <textarea class="cfg" spellcheck={false} value={text} onInput={(e) => setText((e.currentTarget as HTMLTextAreaElement).value)} />
    </div>
  );
}
