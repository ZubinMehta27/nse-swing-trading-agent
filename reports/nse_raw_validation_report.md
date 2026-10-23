# NSE raw data inspection and validation report

- Inspection date: 2026-10-23
- Requested location: `data/raw/nse/`
- Status: **No dataset was available to validate.**
- Backtest/profitability evaluation: **Not run.**

## Files observed

`data/raw/nse/` does not exist. The parent `data/raw/` contains only `README.md`, which documents the intended convention and is not a dataset. No source files were read, renamed, transformed, or overwritten.

| Requested item | Observation |
| --- | --- |
| Source/provider | Unknown; no data file or source metadata present |
| File names/formats | None in `data/raw/nse/` |
| Headers/columns | Unavailable; no headers could be inspected |
| Date range | Unavailable |
| Symbols | Unavailable |
| OHLCV fields | None verified; availability cannot be determined |
| Corporate-action/adjustment metadata | Unavailable; policy is unknown |
| Row-level quality | Not assessable without source rows |
| Indicator warm-up | Not assessable without dated observations |

The canonical schema requires `symbol, session_date, open, high, low, close, volume`, with optional `adjustment_factor` and `adjustment_policy`. No mapping was made because there were no source fields whose meanings could be verified.

## Validator attempt

Command:

```text
python -m nse_swing_agent validate data\raw\nse --cache-dir data\cache
```

The existing validator rejected the requested path before reading any rows:

```text
error: input file does not exist: data\raw\nse
```

The CLI function returned status 2; the PowerShell execution wrapper reported a nonzero process exit (1). This is a missing-input result, not a successful schema or data-quality validation. No imported dataset cache was produced from this path.

## Conclusion and required next step

There is no evidence to identify the source, columns, dates, symbols, or available OHLCV fields. Completeness, duplicate dates, malformed rows, indicator warm-up, corporate-action treatment, and backtest suitability therefore remain unknown. Do not run a backtest on this directory.

Place the original, authorized files under `data/raw/nse/` unchanged, along with source/provenance notes if available. Then rerun the validator against each file. Any exchange-specific field mapping must be supported by the file's documentation or official report specification; ambiguous fields must remain unmapped and be reported as errors. Before any future evaluation, review adjustment handling, execution assumptions, and a date-effective nonzero transaction-cost schedule.
