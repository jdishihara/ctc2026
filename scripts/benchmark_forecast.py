"""Compare complete streaming forecasts and latency with an unchanged checkout.

python scripts/benchmark_forecast.py --baseline /path/to/baseline --seasons 451,470,500 --out out/forecast.json
Uses tune seasons by default; does not fit parameters or submit orders.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def package_at(root: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, root / "ctc/__init__.py",
                                                submodule_search_locations=[str(root / "ctc")])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return importlib.import_module(name + ".valuation"), importlib.import_module(name + ".analog")


def replay(modules, case, feeds):
    valuation, analog = modules
    samples, elapsed = [], []
    for feed in feeds:
        model = valuation.SeasonModel(case)
        model.ensemble = analog.AnalogEnsemble(case, sigma=15, k=100, cone_w=1, cone_s0=20)
        for message in feed:
            model.on_message(message)
            if message["type"] not in ("advisory", "damage_report", "storm_formed", "storm_dissipated"):
                if message["type"] != "storm" or message["age"] % 16:
                    continue
            start = time.perf_counter_ns()
            fair = model.fair_analog()
            elapsed.append((time.perf_counter_ns() - start) / 1e6)
            samples.append([fair[s] for s in valuation.SYMS] +
                           [model.fair_sd[s] for s in valuation.SYMS] +
                           [model.future_sd[s] for s in valuation.SYMS])
    return np.array(samples), np.array(elapsed)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--seasons", default="451,470,500")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.repeats < 1:
        ap.error("--repeats must be positive")
    seasons = [int(n) for n in args.seasons.split(",")]
    case = json.loads((ROOT / "data/case.json").read_text())
    feeds = [[json.loads(line) for line in (ROOT / f"data/history/season-{n:03d}/feed.jsonl").read_text().splitlines()]
             for n in seasons]
    modules = {"baseline": package_at(args.baseline, "ctc_reference"),
               "candidate": package_at(ROOT, "ctc_candidate")}
    measurements = {name: [] for name in modules}
    maximum_error = 0.0
    # Import and library I/O are outside the timed forecast calls. Alternate order
    # to reduce CPU temperature/order effects; retain cold and cached observations.
    for repeat in range(args.repeats):
        arrays = {}
        for name in (list(modules) if repeat % 2 == 0 else list(reversed(modules))):
            arrays[name], ms = replay(modules[name], case, feeds)
            measurements[name].append(ms)
        np.testing.assert_allclose(arrays["candidate"], arrays["baseline"], rtol=1e-10, atol=1e-9)
        maximum_error = max(maximum_error, float(np.max(np.abs(arrays["candidate"] - arrays["baseline"]))))
    result = {"seasons": seasons, "repeats": args.repeats, "python": platform.python_version(),
              "numpy": np.__version__, "machine": platform.machine(), "max_absolute_error": maximum_error}
    for name, runs in measurements.items():
        times = np.concatenate(runs)
        result[name] = {"calls": len(times), "median_ms": float(np.median(times)),
                        "p95_ms": float(np.percentile(times, 95)), "total_ms": float(times.sum())}
    result["speedup"] = result["baseline"]["total_ms"] / result["candidate"]["total_ms"]
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
