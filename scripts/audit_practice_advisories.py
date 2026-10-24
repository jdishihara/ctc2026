"""Compare captured advisories against their published counterparts, using past inputs only.

This diagnostic never reads prices, settlements, an API key, or the active season.
It measures valuation sensitivity, not counterfactual trading P&L.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ctc.strategies import FairValueTrader


def audit():
    evidence = json.loads((ROOT / 'docs/evidence/practice-advisories.json').read_text())
    case = json.loads((ROOT / 'data/case.json').read_text())
    first, last = evidence['observed_first_seq'], evidence['observed_last_seq']
    overrides = {m['seq']: m for m in evidence['advisories']}
    published = {}
    path = ROOT / f"data/history/season-{evidence['season']:03d}/feed.jsonl"
    for line in path.open():
        message = json.loads(line)
        seq = message.get('seq')
        if seq is not None and seq <= last:
            published[seq] = message
    if set(published) != set(range(last + 1)) or not set(overrides) <= set(range(first, last + 1)):
        raise ValueError('audit needs a complete prefix and captured advisories within its observed interval')
    for seq, message in overrides.items():
        if message['type'] != 'advisory' or published[seq]['type'] != 'advisory':
            raise ValueError('only recorded advisory replacements are permitted')

    models = []
    for _ in range(2):
        ex = SimpleNamespace(case=case, competition_id='offline-audit', round=0, t=0.)
        strategy = FairValueTrader(analog=True, sigma=15, k=100, cone_w=1, cone_s0=20,
                                   cone_nu=0, isl_w=0, final_exact=True)
        strategy.on_start(ex)
        models.append(strategy)
    maxima, advisory_checks = {}, []
    for seq, message in sorted(published.items()):
        for model, current in zip(models, (message, overrides.get(seq, message))):
            model.model.on_message(current)
        if seq < first:
            continue
        reference, observed = [model.compute_fair() for model in models]
        changes = {symbol: observed[symbol] - value for symbol, value in reference.items()}
        for symbol, change in changes.items():
            if symbol not in maxima or abs(change) > maxima[symbol]['absolute_change']:
                maxima[symbol] = {'seq': seq, 'absolute_change': abs(change), 'signed_change': change}
        if seq in overrides:
            advisory_checks.append({'seq': seq, 'age': message.get('age'),
                                    'fair_changes': changes})
    return {'season': evidence['season'], 'prefix_last_seq': last,
            'checkpoints': last - first + 1, 'changed_advisories': len(overrides),
            'maxima': maxima, 'advisory_checks': advisory_checks}


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
