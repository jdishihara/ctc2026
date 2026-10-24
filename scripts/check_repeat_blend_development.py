"""Predeclared development-only half-weight blend scan and paired simulation.

Reads seasons 451–525 only. This is reused development data, not a holdout.
It never places account orders. See docs/repeat-blend-plan.md.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
import copy
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def value_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


class TerminalPrices(Mapping):
    def __init__(self, values, sim, violations):
        self._prices, self.sim, self.violations = dict(values), sim, violations

    def _check(self):
        if self.sim.market_open or not math.isfinite(self.sim.t) or self.sim.t < 2340:
            self.violations.append('early settlement read')
            raise RuntimeError('development settlement accessed before season end')

    def __getitem__(self, key):
        self._check()
        return self._prices[key]

    def __iter__(self):
        return iter(self._prices)

    def __len__(self):
        return len(self._prices)

    def copy(self):
        self._check()
        return dict(self._prices)

    def __copy__(self):
        return TerminalPrices(self.copy(), self.sim, self.violations)

    def __deepcopy__(self, memo):
        return self.__copy__()


def make_input_audit(history, forbidden):
    history = Path(history).resolve()
    names = {'feed.jsonl', 'market.csv', 'settlement.json'}
    allowed = {history / f'season-{i:03d}' / name
               for i in range(451, 526) for name in names}

    def audit(event, fields):
        if event in ('socket.connect', 'socket.getaddrinfo', 'socket.bind'):
            forbidden.append(event)
            raise RuntimeError('development experiment forbids network')
        if event == 'open' and isinstance(fields[0], (str, bytes, os.PathLike)):
            lexical = Path(os.fsdecode(fields[0])).absolute()
            path = lexical.resolve()
            lower = str(path).lower()
            if '.botkey' in lower or '/.env' in lower or 'credentials' in lower:
                forbidden.append(lower)
                raise RuntimeError('development experiment forbids credentials')
            history_read = any(p.is_relative_to(history) or p.name in names or '/data/history/' in str(p).lower()
                               for p in (lexical, path))
            if history_read and path not in allowed:
                forbidden.append(str(path))
                raise RuntimeError('history access outside declared development inputs')
    return audit


def unmatched_differences(rows, scans):
    recognized = {s['season'] for s in scans if s['first_match'] is not None}
    return [a['season'] for a, b in zip(rows[::2], rows[1::2]) if a['season'] not in recognized and
            {k: v for k, v in a.items() if k != 'repeat_prefix'} !=
            {k: v for k, v in b.items() if k != 'repeat_prefix'}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history-root', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    history = args.history_root.resolve()
    forbidden = []

    sys.addaudithook(make_input_audit(history, forbidden))
    sys.path.insert(0, str(ROOT))
    from ctc.analog import AnalogEnsemble
    from ctc.ladder import Ladder
    from ctc.sim import Sim
    from ctc.strategies import FairValueTrader
    from scripts.experiment_execution_costs import PARAMETERS

    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT):
        raise RuntimeError('commit source before development evaluation')
    sources = [*ROOT.glob('ctc/*.py'), *ROOT.glob('ctc/*.json'), *ROOT.glob('ctc/*.npz'),
               ROOT / 'data/case.json', Path(__file__), ROOT / 'docs/repeat-blend-plan.md',
               ROOT / 'scripts/experiment_execution_costs.py']
    for path in sources:
        committed = subprocess.check_output(['git', 'show', f'{revision}:{path.relative_to(ROOT)}'], cwd=ROOT)
        if committed != path.read_bytes():
            raise RuntimeError(f'source differs from committed revision: {path.name}')
    inputs = [history / f'season-{i:03d}' / name for i in range(451, 526)
              for name in ('feed.jsonl', 'market.csv', 'settlement.json')]
    source_hashes = {str(p): digest(p) for p in sources}
    input_hashes = {str(p): digest(p) for p in inputs}
    case = json.loads((ROOT / 'data/case.json').read_text())
    case['limits'] = {s: max(1, math.floor(n * .1)) for s, n in case['limits'].items()}
    metadata = dict(started_at=time.time(), revision=revision, source_sha256=source_hashes,
                    input_sha256=input_hashes, seasons=list(range(451, 526)), fraction=.1,
                    latency=.25, rate_limit=90, ladder_scale=.5, refill_seconds=30,
                    parameters=PARAMETERS, repeat_weight=.5, limitations=['Reused development data.',
                    'Historical simulator is not full live supervision or queue competition.'])
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    scans, rows, guard_violations = [], [], []
    recognizer = AnalogEnsemble(case, repeat_prefix=True, repeat_weight=.5)
    with (args.out / 'results.jsonl').open('x') as output:
        for season in range(451, 526):
            folder = history / f'season-{season:03d}'
            rounds = {}
            for line in (folder / 'feed.jsonl').read_text().splitlines():
                message = json.loads(line)
                if message.get('type') == 'storm':
                    rounds.setdefault(message['round'], []).append(message)
            if set(rounds) != {1, 2, 3}:
                raise RuntimeError('development season lacks exactly three storm rounds')
            for rnd, observations in sorted(rounds.items()):
                matches = [recognizer._repeat_index(observations[:n]) for n in range(1, len(observations) + 1)]
                recognized = [(n + 1, row) for n, row in enumerate(matches) if row is not None]
                first = recognized[0] if recognized else None
                divergence = bool(first and any(row != first[1] for row in matches[first[0]:]))
                scans.append(dict(season=season, round=rnd, observations=len(observations),
                    recognized_prefixes=len(recognized), first_match=first,
                    final_match=matches[-1], diverged_after_match=divergence))
            pair = []
            for enabled in (False, True):
                sim = Sim(folder, copy.deepcopy(case), half_spread=.0015, latency=.25, rate_limit=90,
                          ladder=Ladder(refill_secs=30, scale=.5))
                sim.settlement = TerminalPrices(sim.settlement, sim, guard_violations)
                pnl = sim.run(FairValueTrader(**PARAMETERS, repeat_prefix=enabled, repeat_weight=.5))
                if not math.isfinite(pnl):
                    raise RuntimeError('nonfinite development P&L')
                row = dict(season=season, repeat_prefix=enabled, pnl=pnl, fills=len(sim.fills),
                    rejected=sim.rejected, round_pnl=sim.round_pnl,
                    fill_trace_sha256=value_hash([asdict(f) for f in sim.fills]),
                    pnl_path_sha256=value_hash(sim.pnl_path), final_positions=sim.position, cash=sim.cash)
                pair.append(row)
                rows.append(row)
                output.write(json.dumps(row, allow_nan=False) + '\n')
                output.flush()
            print(json.dumps(dict(season=season, difference=pair[1]['pnl'] - pair[0]['pnl'],
                                  matching_storms=sum(s['first_match'] is not None for s in scans[-3:]))), flush=True)
    (args.out / 'prefix-scan.json').write_text(json.dumps(scans, indent=2) + '\n')
    groups = {}
    for enabled in (False, True):
        values = [r['pnl'] for r in rows if r['repeat_prefix'] == enabled]
        groups[str(enabled)] = dict(mean=statistics.mean(values), worst=min(values), best=max(values),
                                    negative=sum(v < 0 for v in values))
    mismatches = [a['season'] for a, b in zip(rows[::2], rows[1::2]) if
                  {k: v for k, v in a.items() if k != 'repeat_prefix'} !=
                  {k: v for k, v in b.items() if k != 'repeat_prefix'}]
    changed = [p for p, h in {**source_hashes, **input_hashes}.items() if digest(p) != h]
    unmatched = unmatched_differences(rows, scans)
    summary = dict(finished_at=time.time(), runs=len(rows), storm_scans=len(scans), groups=groups,
        activated_storms=sum(s['first_match'] is not None for s in scans),
        diverged_storms=sum(s['diverged_after_match'] for s in scans), paired_mismatches=mismatches,
        unmatched_paired_mismatches=unmatched,
        changed_sources_or_inputs=changed, forbidden_attempts=forbidden, guard_violations=guard_violations,
        results_sha256=digest(args.out / 'results.jsonl'), scan_sha256=digest(args.out / 'prefix-scan.json'))
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
    if changed or forbidden or guard_violations or unmatched:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
