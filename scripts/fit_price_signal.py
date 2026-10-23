"""Fit the public-price signal using training seasons only."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import numpy as np

LAGS = [2, 10, 30, 60, 120]
HORIZON = 120
BOUNDARY = 540
ACTIVE = [120, 650]


def samples(prices, times):
    prices, times = np.asarray(prices, dtype=float), np.asarray(times, dtype=float)
    if (prices.ndim != 2 or len(prices) != len(times)
            or not np.array_equal(times, np.arange(len(times)) * 2)):
        raise ValueError('prices must use a complete 2-second round grid')
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError('prices must be finite and positive')
    indexes = np.arange(ACTIVE[0] // 2, min(ACTIVE[1] // 2 + 1, len(times) - HORIZON // 2), 5)
    current = prices[indexes]
    x = np.stack([np.ones_like(current)] + [
        (current - prices[indexes - lag // 2]) / current for lag in LAGS], axis=-1)
    y = (prices[indexes + HORIZON // 2] - current) / current
    return x, y, times[indexes]


def fit(root, train_end=450, eval_end=450):
    if not 1 <= train_end <= eval_end <= 450:
        raise ValueError('training/evaluation must be ordered within seasons 1 through 450')
    root = Path(root)
    case = json.loads((root / 'case.json').read_text())
    manifest = json.loads((root / 'history/manifest.json').read_text())
    symbols = list(case['limits'])
    xs, ys, phases, season_ids = [], [], [], []
    digest = hashlib.sha256()
    for n, season in enumerate(manifest['seasons'][:eval_end], 1):
        raw = (root / 'history' / season['dir'] / 'market.csv').read_bytes()
        digest.update(raw)
        rows = list(csv.DictReader(io.StringIO(raw.decode())))
        for rnd in (1, 2, 3):
            subset = [row for row in rows if int(row['round']) == rnd]
            prices = np.array([[float(row[symbol]) for symbol in symbols] for row in subset])
            clock = [list(map(float, row['time'].split('T')[1].split(':'))) for row in subset]
            times = np.array([((h - 9) * 3600 + (m - 30) * 60 + s) / 30 for h, m, s in clock])
            x, y, elapsed = samples(prices, times)
            xs.append(x); ys.append(y); phases.append(elapsed >= BOUNDARY)
            season_ids.extend([n] * len(elapsed))
    x, y, phase, season_ids = np.concatenate(xs), np.concatenate(ys), np.concatenate(phases), np.array(season_ids)
    train = season_ids <= train_end
    coefficients, prediction = {}, np.empty_like(y)
    for i, symbol in enumerate(symbols):
        coefficients[symbol] = {}
        for flag, name in ((False, 'storm'), (True, 'aftermath')):
            selected = train & (phase == flag)
            a, b = x[selected, i], y[selected, i]
            penalty = np.eye(x.shape[-1]) * .01
            penalty[0, 0] = 1e-6
            weights = np.linalg.solve(a.T @ a + penalty, a.T @ b)
            coefficients[symbol][name] = weights.tolist()
            selected = phase == flag
            prediction[selected, i] = x[selected, i] @ weights
    def metrics(selected):
        actual, pred = y[selected], prediction[selected]
        signals = abs(pred) > .005
        return dict(samples=int(actual.size), rmse=float(np.sqrt(np.mean((pred - actual) ** 2))),
                    zero_rmse=float(np.sqrt(np.mean(actual ** 2))),
                    correlation=float(np.corrcoef(pred.ravel(), actual.ravel())[0, 1]),
                    directional_return=float(np.mean(np.sign(pred[signals]) * actual[signals])),
                    direction_hit_rate=float(np.mean(np.sign(pred[signals]) * actual[signals] > 0)))
    return dict(version=1, horizon=HORIZON, lags=LAGS, phase_boundary=BOUNDARY, active_interval=ACTIVE,
                feature_definition='[1, (current - latest_price_at_or_before_lag) / current for lag in lags]',
                training_seasons=[1, train_end], evaluation_seasons=[train_end + 1, eval_end] if eval_end > train_end else [],
                ridge=.01, intercept_ridge=1e-6, sample_step_seconds=10,
                input_sha256=digest.hexdigest(), fit_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                coefficients=coefficients, training_metrics=metrics(train),
                validation_metrics=metrics(~train) if (~train).any() else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1] / 'data')
    ap.add_argument('--train-end', type=int, default=450)
    ap.add_argument('--eval-end', type=int, default=450)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.out.exists():
        ap.error('output path already exists; use a fresh file')
    result = fit(args.root, args.train_end, args.eval_end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('training_seasons', 'evaluation_seasons', 'training_metrics', 'validation_metrics')}))


if __name__ == '__main__':
    main()
