"""Audit saved trade/position JSON without sending exchange requests.

python scripts/audit_account.py --trades trades.json --positions positions.json
Use --opening opening.json if trades start after an existing account snapshot.
Input is a list or an object containing a trades/positions list. Export all fills
since opening; a latest-100 endpoint response is usually incomplete.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctc.accounting import audit


def load(path, key):
    data = json.loads(Path(path).read_text())
    data = data.get(key) if isinstance(data, dict) else data
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a {key} list")
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trades", required=True)
    ap.add_argument("--positions", required=True)
    ap.add_argument("--opening")
    ap.add_argument("--out")
    args = ap.parse_args()
    result = audit(load(args.trades, "trades"), load(args.positions, "positions"),
                   load(args.opening, "positions") if args.opening else [])
    encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.out:
        Path(args.out).write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
