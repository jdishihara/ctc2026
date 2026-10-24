"""Summarize all sixteen supplemental closed-247 comparisons and declared gates."""
import collections
import hashlib
import json
import math
import itertools
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row):
    return row['capture'], row['rtt_seconds'], row['displayed_depth_fraction'], row['basket_enabled']


def load_phase(name):
    path = ROOT / name
    summary = json.loads((path / 'summary.json').read_text())
    assert summary['runs'] == 16 and summary['errors'] == 0
    assert summary['changed_sources'] == summary['forbidden_attempts'] == []
    assert summary['results_sha256'] == digest(path / 'results.jsonl')
    rows = [json.loads(l) for l in (path / 'results.jsonl').read_text().splitlines()]
    indexed = {key(r): r for r in rows}
    assert len(indexed) == len(rows) == 16
    assert all(r['status'] == 'ok' and not r['errors'] and math.isfinite(r['terminal_settlement_pnl']) for r in rows)
    return indexed, summary


def aggregate(rows):
    values = [r['terminal_settlement_pnl'] for r in rows]
    return dict(settings=len(rows), mean=statistics.mean(values), worst=min(values), best=max(values),
        positive=sum(x > 0 for x in values), negative=sum(x < 0 for x in values), zero=sum(x == 0 for x in values),
        trial_states=dict(collections.Counter(r['trial_state'] for r in rows)),
        cleanup_states=dict(collections.Counter(r['cleanup']['state'] for r in rows)),
        recognized_calls=sum(r['repeat_profile']['recognized'] for r in rows),
        weight_calls=sum(r['repeat_profile']['calls'] for r in rows))


baseline, bs = load_phase('baseline')
candidate, cs = load_phase('candidate')
assert set(baseline) == set(candidate) == set(itertools.product([247], [0., .05, .25, 1.], [1., .5], [False, True]))
stats = {'baseline': aggregate(list(baseline.values())), 'candidate': aggregate(list(candidate.values()))}
pairs, new_attention, residual_increases = [], [], []
for setting in sorted(baseline):
    a, b = baseline[setting], candidate[setting]
    before, after = a['cleanup']['state'], b['cleanup']['state']
    if after not in ('settled', 'flat') and before in ('settled', 'flat'):
        new_attention.append(setting)
    if after not in ('settled', 'flat'):
        previous = a['cleanup'].get('positions', {}) if before not in ('settled', 'flat') else {}
        now = b['cleanup'].get('positions', {})
        if any(abs(v) > abs(previous.get(s, 0)) for s, v in now.items()):
            residual_increases.append(setting)
    pairs.append(dict(setting=setting, baseline_pnl=a['terminal_settlement_pnl'], candidate_pnl=b['terminal_settlement_pnl'],
        delta=b['terminal_settlement_pnl']-a['terminal_settlement_pnl'],
        baseline_trial=a['trial_state'], candidate_trial=b['trial_state'],
        baseline_cleanup=before, candidate_cleanup=after,
        baseline_stop=a['stop_reason'], candidate_stop=b['stop_reason'],
        baseline_low=a['lowest_marked_pnl'], candidate_low=b['lowest_marked_pnl'],
        baseline_drawdown=a['maximum_marked_drawdown'], candidate_drawdown=b['maximum_marked_drawdown'],
        baseline_orders=a['orders'], candidate_orders=b['orders'], baseline_fills=a['fills'], candidate_fills=b['fills'],
        baseline_conversions=a['conversions'], candidate_conversions=b['conversions'],
        recognized_calls=b['repeat_profile']['recognized'], matched_rows=b['repeat_profile']['rows']))

b, c = stats['baseline'], stats['candidate']
failures = []
for condition, reason in [
    (bool(new_attention), 'new_attention_outcome'),
    (bool(residual_increases), 'increased_residual_exposure'),
    (c['negative'] > b['negative'], 'more_negative_capture_settings'),
    (c['worst'] < b['worst'] - 1e-9, 'worse_worst_capture_result'),
    (c['mean'] < b['mean'] - 1e-9, 'lower_mean_capture_result'),
    (c['positive'] != 16, 'not_all_settings_positive'),
    (c['trial_states'].get('completed', 0) != 16, 'not_all_trials_completed'),
    (c['cleanup_states'].get('settled', 0) != 16, 'not_all_receipts_settled')]:
    if condition:
        failures.append(reason)

report = dict(
    source_result_hashes={'baseline':bs['results_sha256'], 'candidate':cs['results_sha256']},
    aggregate=stats,
    pnl_comparison=dict(improved=sum(p['delta'] > 1e-9 for p in pairs),
                        worsened=sum(p['delta'] < -1e-9 for p in pairs), unchanged=sum(abs(p['delta']) <= 1e-9 for p in pairs)),
    per_capture={str(n):{phase:aggregate([r for r in data.values() if r['capture']==n])
                         for phase,data in [('baseline',baseline),('candidate',candidate)]} for n in [247]},
    primary=[p for p in pairs if p['setting'][1:]==(.25,1.,True)],
    new_attention_settings=new_attention, increased_residual_settings=residual_increases,
    decision='reject' if failures else 'passes_declared_offline_gates_pending_independent_review',
    failed_rules=failures, pairs=pairs,
    limitations=['Captures exactly overlap fitted weather; gains are not unseen-weather evidence.',
                 'Execution settings are correlated, not independent seasons.',
                 'The model was frozen before closure, but this check was declared after original-247 results were known.',
                 'Matching prefixes do not guarantee identical future continuation.'])
(ROOT / 'analysis.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
print(json.dumps({k:report[k] for k in ['aggregate','pnl_comparison','primary','decision','failed_rules']}, allow_nan=False))
