"""Training-only screen of recency weighting; no live strategy changes."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ctc.analog import AnalogEnsemble, build_library, GRID_AGES
from ctc.valuation import SeasonModel
from ctc.wind import PHYS, PARAMS


class RecentAnalog(AnalogEnsemble):
    """Research override: recompute weighted mismatch without optimizing it."""
    def __init__(self, *args, half_life=0, cone_center=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.half_life = half_life
        self.cone_center = cone_center
        self.current_advisory = None

    def weights(self, obs, official, wire, adv=None):
        self.current_advisory = adv
        if self.half_life:
            cur = np.array([[o['age'], o['x'], o['y']] for o in obs])
            delta = self._positions_at(cur[:, 0]) - cur[None, :, 1:]
            age_weight = np.exp2((cur[:, 0] - cur[-1, 0]) / self.half_life)
            self._track_error = (np.square(delta).sum(2) @ age_weight) / age_weight.sum() * len(cur)
            self._observed = cur.copy()
        return super().weights(obs, official, wire, adv)

    def projected_paths(self, obs, w):
        age = obs[-1]['age']
        selected = np.flatnonzero(w > 0)
        grid = GRID_AGES[GRID_AGES > age]
        paths = self.tracks[selected, int(age // 2) + 1:].copy()
        offset = np.array([obs[-1]['x'], obs[-1]['y']]) - self._positions_at(np.array([age]))[selected, 0]
        paths[:, :, :2] += offset[:, None]
        cones = [cp for cp in (self.current_advisory or {}).get('cone', []) if age < cp['age'] <= 480]
        if self.cone_center and cones:
            mean = np.einsum('i,ijk->jk', w[selected], paths[:, :, :2])
            knots, corrections = [age], [np.zeros(2)]
            for cp in sorted(cones, key=lambda cp: cp['age']):
                projected = np.array([np.interp(cp['age'], grid, mean[:, axis]) for axis in range(2)])
                knots.append(cp['age'])
                corrections.append(np.array([cp['x'], cp['y']]) - projected)
            knots.append(knots[-1] + 60)
            corrections.append(np.zeros(2))
            correction = np.stack([np.interp(grid, knots, np.array(corrections)[:, axis]) for axis in range(2)], axis=1)
            paths[:, :, :2] += self.cone_center * correction[None]
        return paths, selected

    def future_exposure(self, obs, w):
        paths, selected = self.projected_paths(obs, w)
        e, o = {}, {}
        for symbol, sites in self.sites.items():
            dist = np.hypot(paths[:, :, 0, None] - sites[:, 0], paths[:, :, 1, None] - sites[:, 1])
            wind = paths[:, :, 3, None] * np.exp(-PARAMS['k'] * dist / paths[:, :, 2, None])
            e[symbol] = np.clip(wind - PARAMS['thr_dmg'], 0, None).__pow__(PARAMS['p']).sum(1) * 2
            o[symbol] = (wind > PARAMS['thr_close']).sum(1) * 2
        return e, o, selected


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--method', choices=['recency', 'cone-center'], default='recency')
    ap.add_argument('--production', action='store_true', help='verify production cone projection against the research prototype')
    a = ap.parse_args()
    if a.production and a.method != 'cone-center':
        ap.error('--production requires --method cone-center')
    a.out.mkdir(parents=True, exist_ok=False)
    root = ROOT / 'data'
    case = json.loads((root / 'case.json').read_text())
    seasons = json.loads((root / 'history/manifest.json').read_text())['seasons']
    lib = a.out / 'library-1-300.npz'
    build_library(root, seasons[:300], lib)
    configs = {half: {'half_life': half} for half in (0, 60, 120, 240)} if a.method == 'recency' else {
        alpha: {'cone_center': alpha} for alpha in (0, .5, 1)}
    cls = AnalogEnsemble if a.production else RecentAnalog
    models = {name: cls(case, lib=lib, sigma=15, k=100, cone_w=1, cone_s0=20,
                                **config) for name, config in configs.items()}
    errors = {half: [] for half in models}
    ages = (30, 90, 150, 240, 360)
    for n in range(301, 451):
        season = seasons[n - 1]
        feed = [json.loads(line) for line in (root / 'history' / season['dir'] / 'feed.jsonl').read_text().splitlines()]
        md = SeasonModel(case)
        truth = {storm['round']: storm for storm in season['storms']}
        positions = {(m['round'], m['age']): np.array([m['x'], m['y']])
                     for m in feed if m['type'] == 'storm'}
        for m in feed:
            md.on_message(m)
            if m['type'] != 'storm' or m['age'] not in ages:
                continue
            rnd, age = m['round'], m['age']
            for half, model in models.items():
                w = model.weights(md.obs, md.official, md.wire, md.adv)
                paths, selected = (model.future_tracks(md.obs, w, md.adv) if a.production
                                   else model.projected_paths(md.obs, w))
                row = dict(season=n, round=rnd, age=age)
                for horizon in (60, 120):
                    point = w[selected] @ paths[:, horizon // 2 - 1, :2]
                    row[f'position{horizon}_sq'] = float(np.square(point - positions[rnd, age + horizon]).sum())
                exposure, _, selected = (model.future_exposure(md.obs, w, md.adv) if a.production
                                        else model.future_exposure(md.obs, w))
                preds = []
                for symbol in PHYS:
                    state = md.states[symbol]
                    damages = (100 - np.array(state.cum)) * (1 - np.exp(-state.c * (np.array(state.exposure) + exposure[symbol])))
                    expected = w[selected] @ (damages @ np.array([site['weight'] for site in state.sites]))
                    preds.append(float(expected - truth[rnd]['damage_pct'][symbol]))
                row['damage_sq'] = float(np.mean(np.square(preds)))
                errors[half].append(row)
        if n % 50 == 0:
            print(f'completed through season {n}', flush=True)
    summaries = {}
    for half, rows in errors.items():
        summaries[half] = {key.replace('_sq', '_rmse'): float(np.sqrt(np.mean([r[key] for r in rows])))
                           for key in ('position60_sq', 'position120_sq', 'damage_sq')}
        summaries[half]['by_age'] = {age: {key.replace('_sq', '_rmse'): float(np.sqrt(np.mean([r[key] for r in rows if r['age'] == age])))
                                        for key in ('position60_sq', 'position120_sq', 'damage_sq')} for age in ages}
        print(json.dumps({'method': a.method, 'candidate': half, **summaries[half]}), flush=True)
    (a.out / 'results.json').write_text(json.dumps(dict(training_seasons=[1, 300],
        validation_seasons=[301, 450], method=a.method, production=a.production, configurations=configs,
        summaries=summaries, rows=errors), indent=2) + '\n')


if __name__ == '__main__':
    main()
