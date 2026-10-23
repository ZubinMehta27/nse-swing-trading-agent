# NSE Swing Agent

Offline research tools for Indian NSE/BSE cash-equity swing trading. **PAPER TRADING ONLY.** The package contains local simulation code and an optional, explicit TejHQ historical-data fetcher. It has no broker API, credential handling, or live order submission. Historical backtest results do not guarantee future profitability. The starter strategy is an unvalidated research hypothesis, not financial advice.

## Install

Python 3.11 or newer is required. CSV ingestion and simulation use the standard library. Parquet is optional:

```powershell
python -m pip install -e '.[dev]'
# Optional Parquet support:
python -m pip install -e '.[dev,data]'
```

The project uses `Decimal` for prices and money and daily session dates normalized to 15:30 Asia/Kolkata for completed bars. Core installation and tests work offline. TejHQ retrieval uses Python's standard-library HTTPS client and runs only when explicitly requested.

## TejHQ daily NSE history

The `fetch-history` command requests one explicitly named NSE symbol over one explicit date range. It never requests a market-wide dataset. No credentials are needed for the documented keyless `/v1/ohlcv` endpoint. Requests use a 15-second timeout and at most two retries by default (retry count and timeout are configurable).

```powershell
python -m nse_swing_agent fetch-history --symbol RELIANCE --from 2025-01-01 --to 2025-01-10
```

The endpoint contract documents a JSON object with `data` and `meta`; each daily row provides `date`, `open`, `high`, `low`, `close`, and `volume`. Optional provider fields such as `last`, `prev_close`, `turnover`, and `trades` are preserved in the unchanged raw response, but are not mapped into canonical columns. The canonical schema maps `date` to `session_date`, the four OHLC fields by their same names, and `volume` by its same name. The symbol comes from the requested single-symbol endpoint path and the response metadata is checked against it. Rows are sorted by session date and then validated with the same strict local CSV validator; malformed dates, missing/invalid values, duplicate sessions, invalid OHLC, and out-of-range observations fail with an error.

Original response bytes are written exclusively (never silently overwritten) to `data/raw/nse/`. Normalized canonical CSV and a JSON provenance manifest are written to `data/processed/`. The manifest records endpoint, provider, symbol, requested and returned ranges, UTC retrieval time, raw SHA-256, schema version, adjustment status, and transformations. Inspect a run using the paths printed by the command, for example:

```powershell
Get-Content data/processed/tejhq_RELIANCE_*.json
```

TejHQ documents `/v1/ohlcv` as end-of-day OHLCV and `/v1/adjusted` as a separate endpoint. This adapter uses only `/v1/ohlcv` and therefore labels values `raw_unadjusted`; it does not infer or apply corporate-action factors. Do not combine its output with adjusted prices. Raw corporate actions, provider corrections, exchange holidays, and historical symbol/universe membership are outside this adapter. The provider describes data derived from exchange bhavcopy; consult the [TejHQ API documentation](https://tejhq.dev/docs) and [dataset documentation](https://huggingface.co/datasets/tejhq/indian-markets) for source/schema limits. Follow the provider and exchange terms; access does not imply permission to redistribute. A successful fetch only validates and records a data response; it is not evidence of backtest validity or profitability.

For a smoke test, choose a short date range explicitly. Larger ranges require an explicit `--from` and `--to` by design. Use `--raw-dir` and `--processed-dir` to choose other local output locations. Transport/schema errors are printed to stderr and return status 2. The fetch command does not connect to brokers or submit orders.

The Milestone 2D coverage and corporate-action review is recorded in [the readiness report](reports/milestone_2d_readiness.md) and its machine-readable [JSON audit](reports/milestone_2d_readiness.json). It includes the long RELIANCE coverage run, provider freshness response, raw corporate-action response fingerprint, execution/cost audit, and unresolved data gaps. No performance evaluation was run.

## NSE source gap audit

Milestone 2E verified four TejHQ omissions against official NSE CM-UDiFF bhavcopy ZIPs. The unchanged originals and their hashes are retained under `data/raw/nse/`; detailed row values, ISIN, source filenames, retrieval times and hashes are in [the source evidence report](reports/milestone_2e_official_gap_evidence.json). The audit found an official RELIANCE EQ row (`INE002A01018`) on all four dates. These source bars have not been merged into the TejHQ dataset.

Use the reusable audit command with a sourced calendar CSV (`session_date,status,source`, where status is `SESSION` or `HOLIDAY`) and one or more original NSE CSV/ZIP files:

```powershell
python -m nse_swing_agent audit-gaps data/processed/history.csv --calendar data/reference/nse_calendar.csv --source-file data/raw/nse/BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip --output reports/gap-audit
```

The audit emits `gap_audit.csv`, `gap_audit.json` and `gap_audit.md`, fingerprints its inputs, validates source schemas and rows, and never fills bars. UDiFF mapping is explicit (`TradDt`, `TckrSymb`, `ISIN`, `OpnPric`, `HghPric`, `LwPric`, `ClsPric`, `TtlTradgVol`) and limited to `STK`/`EQ`; supported legacy mapping requires its named OHLCV fields. Unsupported or ambiguous headers fail with an error. A retrieved file and a valid row are recorded separately. See [the readiness report](reports/milestone_2e_readiness.md): the 104 weekday gaps from 2018–2024 remain unresolved pending authoritative calendar and daily-report evidence, so real-data evaluation remains blocked.

## Local historical data

Keep source files under `data/raw/` and local imports/caches under `data/cache/` (ignored by git). Never edit source files in place. Input CSV and Parquet use this canonical schema:

| Column | Required | Meaning |
| --- | --- | --- |
| `symbol` | yes | Exchange symbol; normalized to uppercase |
| `session_date` | yes | ISO `YYYY-MM-DD` exchange session date |
| `open`, `high`, `low`, `close` | yes | Positive decimal prices |
| `volume` | yes | Nonnegative integer shares |
| `adjustment_factor` | no | Positive factor metadata; not applied by importer/backtester |
| `adjustment_policy` | no | Provenance label; defaults to `raw_unadjusted` |

Every symbol/session pair must be unique. All columns and rows are validated; invalid records stop the import with a row-specific error. Values are not silently dropped, coerced, sorted in-place, or repaired. Valid rows are returned in deterministic `(session_date, symbol)` order. Parquet requires `pyarrow` and uses the same column names and validation.

CSV example (prices below are illustrative only):

```csv
symbol,session_date,open,high,low,close,volume,adjustment_factor,adjustment_policy
EXAMPLE,2025-01-02,100.00,103.00,99.50,102.00,250000,,raw_unadjusted
```

Validate and cache an import:

```powershell
python -m nse_swing_agent validate data/raw/my_history.csv --source "manually prepared NSE report, downloaded YYYY-MM-DD"
```

The cache contains normalized canonical CSV plus JSON metadata: source description, SHA-256 input fingerprint, import UTC time, symbol/date range, row count, schema version, and adjustment policy. Cache files are derived artifacts; source files are not overwritten.

### Official source and corporate actions

For NSE cash market end-of-day reports, use NSE's official [All Reports portal](https://www.nseindia.com/all-reports) and the [Capital Market historical reports page](https://www.nseindia.com/resources/historical-reports-capital-market-daily-monthly-archives). NSE states that the older CM Bhavcopy/Common Bhavcopy formats were discontinued effective 8 July 2024; look for the current CM-UDiFF Common Bhavcopy Final report. NSE also offers [paid EOD/historical data](https://www.nseindia.com/static/market-data/eod-historical-data-subscription). This project does not download or parse exchange-specific report layouts automatically: manually obtain reports through official access and map them to the canonical schema. Follow applicable exchange terms; do not bypass access controls or redistribute files without permission.

Raw OHLCV is preserved. Adjustment factor/policy columns are metadata only; the pipeline does not apply split/dividend adjustments or reconstruct total returns. `raw_unadjusted` series may contain discontinuities that distort indicators and stops. Supply consistently pre-adjusted prices only when the adjustment method and source are known, and label them accordingly. A point-in-time historical universe is not provided, so results are not survivorship-free. No official exchange calendar is bundled; different symbol calendars and warm-up shortages are flagged, but a date missing for every symbol cannot be distinguished from an exchange holiday without an external calendar.

## Strategy and backtest

The existing long-only starter strategy is unchanged: completed close above SMA50, SMA50 above SMA200, and RSI14 within a configurable 40–60 pullback band. It is an **unvalidated hypothesis**, not a demonstrated trading edge. The backtester uses the same strategy and risk sizing implementation.

Run an offline backtest on the bundled synthetic fixture:

```powershell
python -m nse_swing_agent backtest src/nse_swing_agent/data/synthetic_ohlcv.csv --output backtest-output/synthetic
```

The CLI labels this fixture synthetic. Its results are test/demo output, not market evidence. Run on a local canonical data file with a reserved chronological period and pre-period warm-up rows:

```powershell
python -m nse_swing_agent backtest data/raw/history.csv --start 2024-01-01 --end 2025-12-31 --output backtest-output/test-period
```

Backtest options expose `--initial-cash`, `--max-positions`, `--max-volume-fraction`, `--slippage-bps`, `--atr-period`, `--stop-atr-multiple`, `--target-r-multiple`, `--risk-fraction`, `--position-fraction`, `--sma-fast`, `--sma-slow`, `--rsi-period`, `--rsi-pullback-min`, and `--rsi-pullback-max`. `python -m nse_swing_agent backtest --help` lists the accepted arguments.

Rows are never shuffled. All history before `--start` is available only for indicator warm-up; entries are not queued before the evaluation window. `--end` stops processing at the specified date. For research, decide and record train/validation/test periods chronologically before inspecting results; tune on train, select on validation, and report the final test period once. The tool does not optimize parameters or prevent repeated manual inspection.

Execution assumptions:

- A completed close signal on session *t* becomes a pending order and can only enter at the next available session for that symbol.
- Buy/sell slippage is configurable adverse basis points. Orders fill in full at the modeled price only if under a configured participation cap of bar volume, within cash including fees, and within the open-position limit; otherwise they are rejected.
- ATR determines the initial stop distance; a configurable R multiple sets a target. Opening gaps through a stop exit at the open less adverse sell slippage. An intraday stop touch exits at the stop less slippage. If stop and target are both touched in one daily bar, the conservative stop outcome is used. Stops do not guarantee exit prices in real markets.
- A daily OHLC bar cannot reveal intraday event order. Targets, gaps, liquidity, market impact, and costs are simplified. Open positions are marked to close at the end of the run and are not forcibly liquidated.
- `CostSchedule` supports version/effective date, brokerage, buy/sell STT, exchange charges, GST on brokerage plus exchange charges, buy stamp duty, and delivery-sale DP cost per share. Defaults are deliberately zero because rates vary by date, broker, instrument, and jurisdiction. Supply applicable documented values via a JSON file; do not treat defaults as a realistic cost estimate.
- A profile can include `effective_from`, `effective_to`, `source`, and `verification_status` (`unverified` or `verified`). `config/cost_profile.example.json` is deliberately zero and unverified. The `--cost-inclusive` label is rejected unless the supplied profile is explicitly `verified`, cites its source, explicitly supplies every rate, has nonzero rates, and covers the evaluated dates. This metadata is an assertion by the profile author; users must check each applicable component and effective date themselves. Ordinary runs can still use illustrative/zero schedules and their manifest identifies their status.
- The cost model applies configured rate times modeled turnover plus configured per-share DP charges; it does not model minimum brokerage, statutory rounding/levies, or broker-specific fee tiers.

Example `costs.json` (placeholder rates only; replace with a verified, date-effective schedule):

```json
{
  "version": "example-only-2025-01",
  "effective_from": "2025-01-01",
  "brokerage_rate": "0.0000",
  "stt_buy_rate": "0.0000",
  "stt_sell_rate": "0.0000",
  "exchange_rate": "0.0000",
  "gst_rate": "0.0000",
  "stamp_buy_rate": "0.0000",
  "dp_charge_per_share": "0.00"
}
```

Pass it with `--costs-json costs.json`. For a real study, verify effective dates, turnover bases, minimums, rounding, taxes, and DP applicability from primary sources and your chosen broker. Components are accounted once per modeled fill; no current rate is asserted here.

The TejHQ adjusted series exposes `adj_close = close * adj_factor_cumulative`; it is a back-adjusted close, while the published adjusted-price table retains raw `open/high/low/close`. This project does not synthesize adjusted OHLC or convert adjusted signals into raw execution prices. The backtester now rejects non-`raw_unadjusted` policy labels until a tested conversion and corporate-action position/cash model exists. Raw data can still have unmodeled corporate-action discontinuities and warrants audit before real-data research.

Exports in the selected output directory: `trades.csv`, `equity_curve.csv`, `ledger.csv`, `metrics.json`, and `manifest.json` with run configuration, input fingerprint, date range, symbols, synthetic flag, adjustment policy, and execution policy. Metrics include gross/net closed-trade P&L, return, CAGR when meaningful, max drawdown, annualized Sharpe/Sortino conventions, gross profit factor, win rate, average win/loss, session exposure (share of sessions with an open position), turnover, costs, and optional benchmark price return. Undefined statistics remain `null` when there are no trades, insufficient time, or zero return variance. Benchmark symbol data is report-only and is not traded; its price return excludes dividends unless the supplied prices are adjusted.

## Offline demo and quality checks

```powershell
python -m nse_swing_agent.demo
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Synthetic OHLCV is explicitly artificial. Backtests, paper fills, and historical simulation cannot prove profitability or establish a guaranteed stop loss. No market data is bundled except the small synthetic fixture.
