# Historical loss attribution

## Result

The entry-corrected strategy was replayed on every development season, 451–525,
with the observed-touch cost profile, 10% position limits, and latencies of
0.25 and 3 seconds. All 150 traced runs reproduced the baseline P&L, fill count,
rejections, and round P&L. No strategy parameters changed.

| Assumed latency | Seasons | Mean simulated P&L | Losing seasons | Worst season |
| --- | ---: | ---: | ---: | ---: |
| 0.25 seconds | 75 | +$1,434.47 | 6 | −$765.65 |
| 3 seconds | 75 | +$1,027.27 | 9 | −$1,097.41 |

HAVEN is the largest loss contributor in the worst scenario (season 520,
3 seconds): −$516.15 of −$1,097.41. But it also has the highest average trade
contribution across all 75 seasons. Every symbol contributes positively on
average at both latencies. Removing HAVEN based on the selected losing seasons
would ignore its contribution in the other seasons.

| Symbol | Mean contribution, 0.25 seconds | Mean contribution, 3 seconds |
| --- | ---: | ---: |
| AQUA | $82.24 | $59.39 |
| ARCH | $236.46 | $150.62 |
| FERRY | $162.14 | $117.08 |
| GEN | $44.42 | $37.20 |
| GRID | $126.85 | $108.80 |
| HAVEN | $319.76 | $224.98 |
| ISLE | $81.36 | $56.19 |
| MAT | $14.47 | $8.20 |
| PORT | $211.75 | $143.58 |
| REBLD | $58.47 | $55.76 |
| RECON | $77.33 | $53.77 |
| REIN | $19.22 | $11.70 |

Orders submitted during a storm account for mean contributions of $1,329.34 and
$1,005.85, but −$2,667.93 in the worst scenario. Both gains and losses are
concentrated in trades submitted during storms. This accounting does not isolate
forecast error from price paths or execution effects. It does not
establish that skipping a phase or symbol would retain the other contributions:
entry orders, reductions, later trades, basket legs, and risk limits interact.

## Method and limits

`TraceSim` records order state when submitted and fill state when executed. It
does not consult settlement during these callbacks. After replay, each filled
trade is marked to settlement as:

`signed quantity × (settlement price − fill price)`

Contributions are grouped by symbol, submission phase, and submission round.
Round attribution is not the simulator's marked P&L at each round boundary.
Conversions can redistribute exposures, so any residual is reported separately.
The largest absolute residual across the 150 runs was $6.14 × 10⁻¹².

The first pass examined the 15 losing scenarios (nine distinct seasons). The
second pass included all 150 scenarios to avoid drawing a conclusion from losses
alone. These are repeatedly examined development data, with static historical
execution assumptions. They do not prove live consistency or future profitability.
The diagnostic does not change the running frozen evaluation or enable trading.

## Evidence and reproduction

- [All 150 summaries](evidence/loss-contributions/all-summary.json) and
  [run metadata](evidence/loss-contributions/all-metadata.json).
- [Initial 15 losing summaries](evidence/loss-contributions/loss-summary.json)
  and [run metadata](evidence/loss-contributions/loss-metadata.json).
- [Entry-corrected baseline](evidence/executable-entry/dev-results.jsonl) and
  [baseline metadata](evidence/executable-entry/dev-metadata.json).

Metadata records strategy parameters, every selected history file's SHA-256,
Python/model/NPZ hashes, and baseline hashes. The first pass used script commit
`ce46c72`. The all-season pass added only the `--include-positive` selection flag;
its recorded script SHA-256 is
`ff0ba8b1a491fc2cd306ec7820a5ce23f9aa561cd79b7383bd706a1a6d18f82a`.

The full per-fill traces remain in the local output directories. They can be
recreated from the fixed baseline and history; the smaller summaries are checked
into the repository. Original trace receipts:

| Local path | Bytes | SHA-256 |
| --- | ---: | --- |
| `out/downside-attribution-20261024/traces.jsonl` | 754867 | `ccf70e9793c48e512ff45ed81d7e24a61d8b0adfe4f82d207f8fafa28ef967a9` |
| `out/all-contributions-20261024/traces.jsonl` | 7495495 | `5a35b2f4af990e2c5e6793ca4dea8020a8b99c60a0a6cafb67920d7fcd5abeb8` |

From the project root, with the history present and the original baseline output
directory (its metadata is named `metadata.json`):

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/diagnose_loss_contributions.py \
  --baseline out/entry-guard-20261024-dev/results.jsonl \
  --include-positive --out out/contributions-reproduction
```

For a fresh checkout, reconstruct that baseline directory from the two linked
baseline artifacts, naming them `results.jsonl` and `metadata.json`. The script
rejects mismatched sources, incomplete baseline grids, and any replay that
changes P&L, fill count, rejections, or round P&L.
