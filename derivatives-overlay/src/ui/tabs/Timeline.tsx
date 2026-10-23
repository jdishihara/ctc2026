import { Controller } from '../controller';
import { cls, f, money, pct, signed } from '../fmt';

export function TimelineTab({ c }: { c: Controller }) {
  const { s, d, cfg } = c.store;
  const cur = d.phase?.event?.n;
  return (
    <div>
      <table>
        <thead><tr><th>#</th><th>R</th><th>news</th><th>move</th><th>snap</th><th>status</th></tr></thead>
        <tbody>
          {cfg.schedule.map((e) => (
            <tr class={cls(e.n === cur && 'pos')}>
              <td>{e.n}</td><td>{e.round}</td><td>{e.date.slice(5)} {e.news}</td><td>{e.move}</td><td>{e.snap}</td>
              <td>{e.n === cur ? d.phase?.phase : s.timeline[e.n]?.trueVol ? 'done' : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {Object.values(s.timeline).sort((a, b) => b.n - a.n).map((t) => (
        <div class="box small">
          <div class="sec">Event {t.n} · round {t.round}{t.captured != null && <span class={t.captured >= 0 ? 'pos' : 'neg'}>captured ≈ {money(t.captured)}</span>}</div>
          {t.headline && <div>{t.headline}</div>}
          {cfg.underlyings.map((u) => (
            <div class="muted">
              {u}: old {f(t.baseline?.[u]?.oldSpot)} / {pct(t.baseline?.[u]?.oldVol)}
              {t.targets?.[u] && ` → target ${f(t.targets[u].spot)} / ${pct(t.targets[u].vol)}`}
              {t.trueVol && ` → true vol ${pct(t.trueVol[u])}`}
              {t.analystErrors?.[u] && ` · errors ${Object.entries(t.analystErrors[u]).map(([a, e]) => `A${a} ${signed((e as number) * 100, 1)}`).join(' ')}`}
            </div>
          ))}
        </div>
      ))}
      <div class="sec">News log</div>
      {s.news.slice(0, 30).map((n) => (
        <div class="small"><span class="tag">{n.src}{n.seq != null ? ` #${n.seq}` : ''}</span> <span class="muted">E{n.event ?? '?'} {n.kind}</span> {n.text}</div>
      ))}
    </div>
  );
}
