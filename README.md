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

The 2F historical audit is recorded in [the 2F readiness report](reports/milestone_2f/readiness.md). It uses seven preserved official year-filtered NSE CM holiday API responses and four official special-session daily reports. Rebuild the 2018–2024 calendar from the preserved responses, then reproduce the gap report using the commands in that report. The audit distinguishes regular weekdays, weekends, exchange holidays and Muhurat special sessions; it never merges recovered prices. Ordinary weekday rows use NSE's published weekly trading rule minus listed holiday dates and are not individually checked against daily bhavcopies. Corporate-action accounting and verified date-effective costs remain blockers to real-data evaluation.

## NSE source gap audit

Milestone 2E verified four TejHQ omissions against official NSE CM-UDiFF bhavcopy ZIPs. The unchanged originals and their hashes are retained under `data/raw/nse/`; detailed row values, ISIN, source filenames, retrieval times and hashes are in [the source evidence report](reports/milestone_2e_official_gap_evidence.json). The audit found an official RELIANCE EQ row (`INE002A01018`) on all four dates. These source bars have not been merged into the TejHQ dataset.

Use the reusable audit command with a sourced calendar CSV (`session_date,status,source`, where status is `SESSION` or `HOLIDAY`) and one or more original NSE CSV/ZIP files:

```powershell
python -m nse_swing_agent audit-gaps data/processed/history.csv --calendar data/reference/nse_calendar.csv --source-file data/raw/nse/BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip --output reports/gap-audit
```

The audit emits `gap_audit.csv`, `gap_audit.json` and `gap_audit.md`, fingerprints its inputs, validates source schemas and rows, and never fills bars. Calendar statuses include `SESSION`, `SPECIAL_SESSION`, `HOLIDAY`, `WEEKEND`, and `WEEKEND_HOLIDAY`. UDiFF mapping is explicit (`TradDt`, `TckrSymb`, `ISIN`, `OpnPric`, `HghPric`, `LwPric`, `ClsPric`, `TtlTradgVol`) and limited to `STK`/`EQ`; supported legacy mapping requires its named OHLCV fields. ZIP archives can contain one or more CSV members. Unsupported or ambiguous headers fail with an error. Source file fingerprints and schema validation are recorded separately; HTTP retrieval provenance is recorded in the cited source manifest. The 2E report records initial findings; the newer [2F readiness report](reports/milestone_2f/readiness.md) classifies the 2018–2024 gaps and records the remaining evaluation blockers.

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

Raw OHLCV is preserved. Adjustment factor/policy columns are metadata only and never treated as action terms. Corporate-action events use a separately reviewed canonical manifest; see [the action schema and accounting policy](docs/corporate_actions.md). Real-symbol backtests require action coverage explicitly marked complete and verified over all input history. The current TejHQ response is not complete/verified coverage: it includes NSE/BSE duplicates, lacks payment dates/currency for dividends, and its documented feed has no completeness guarantee. No raw files or Milestone 2F candidate bars are modified or merged.

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

For non-synthetic inputs, provide a reviewed action manifest with `--actions-manifest path/to/actions.json`. Unsupported rights, demerger, merger, buyback, and delisting events block overlapping runs. A manifest's coverage flags are review assertions and must be supported by source evidence; they are not proof that the provider feed is complete.

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

The TejHQ adjusted series exposes `adj_close = close * adj_factor_cumulative`; it does not define adjusted open/high/low. This project does not synthesize adjusted OHLC or mix adjusted indicators with raw execution prices. Split and bonus events scale held/pending whole-share quantities and inversely scale unit cost basis and protective levels; fractional entitlements block. Dividends accrue to eligible prior-close positions on ex-date, are recognized as receivables, and enter cash only on payment date. Dividend cash is kept separate from realized trading P&L. Raw indicators reset and warm up after split, bonus, and dividend ex-dates. Rights, demergers, mergers, buybacks, and delistings block overlapping runs pending event-specific terms and accounting. See the action audit report at `reports/milestone_2g_corporate_action_audit.json`. Real-data evaluation remains blocked by historical coverage, event completeness, and cost verification limitations.

## Milestone 2J cost profile and bar recovery

The hypothetical, incomplete resident-individual Zerodha/NSE delivery cost profile is at `config/cost_profiles/zerodha_resident_individual_nse_delivery_hypothetical.json`; its source archive and SHA-256 provenance are under `data/reference/cost_profiles/source_archive/`. Read [the cost-profile evidence and calculation specification](docs/milestone_2j_cost_profile.md). Source page snapshots are observations at retrieval time, not a full historical tariff. Two official Income Tax documents could not be archived (HTTP 403); the Department of Economic Affairs annual report retrieval failed TLS and is not relied upon. The NSE circulars verify transaction charge intervals from 2024-10-01 and 2026-03-01, but unverified contract-note rounding still blocks quotes. Brokerage/DP account applicability, historical statutory rates, effective dates, bases, minimums, aggregation and rounding remain unresolved. The existing zero/unverified `CostSchedule` defaults are unchanged. A cost-inclusive evaluation must not use this partial profile.

For isolated source validation of the eight Milestone 2H discrepancies, run:

```powershell
$env:PYTHONPATH = "src"
python scripts/build_m2j_recovery_candidate.py
python scripts/build_m2j_reports.py
```

The first command writes a separate eight-row canonical candidate CSV and detailed recovery manifest to `data/validation/recovery_candidates/milestone_2j_v2/`. It checks each retained NSE file SHA-256, source date, RELIANCE/INE002A01018 identity, NSE EQ row, OHLCV invariants and exact agreement with the prior source reconciliation, plus absence from the cached TejHQ file. It never edits or merges any source data. The candidate set validates only those rows; the full history remains blocked for identity, corporate-action coverage and costs. `reports/milestone_2j/evidence_integrity.json` compares all raw NSE and processed files, plus enumerated prior 2F–2I reports, against the pre-edit hash snapshot. The second command writes the updated report to `reports/milestone_2j_v2/`; the earlier `reports/milestone_2j/` output is preserved. An identical rerun is deterministic; different existing outputs are refused, so choose a new versioned output directory when evidence changes.

Cost arithmetic regression fixtures under `tests/fixtures/` are synthetic and explicitly opt-in; they are not tariffs or market facts. No backtest or profitability evaluation was run as part of Milestone 2J.

## Milestone 2H evidence gate

Regenerate the source-verified evidence package from the preserved reports and raw files with:

```powershell
python scripts/build_milestone_2h_evidence.py
```

The command creates `reports/milestone_2h/` with an event-by-event corporate-action evidence registry, an eight-date official NSE versus TejHQ OHLCV comparison (CSV and JSON), a date-effective cost evidence schedule, and a readiness decision. It re-hashes and re-validates the preserved NSE source reports. It never edits raw data or merges candidate bars. The report stays blocked when sources, event terms, historical effective intervals, broker assumptions, or charge rounding are incomplete. The current TejHQ action feed is only discovery evidence; cross-exchange representations remain separate source rows. Official filings inspected for selected rights, demerger, bonus and charge facts are recorded by URL. Direct archiving of those PDF files failed due to an HTTPS read timeout; no local fingerprint is claimed for them.

The NSE sources establish selected charge facts, not a complete historical transaction-cost profile: the 2024 exchange circular sets cash market charges at Rs 2.97 per lakh each side effective 2024-10-01; NSE's levy guidance lists delivery-equity STT, delivery stamp duty, GST on broker services, and SEBI turnover fees. Historical statutory schedules, the selected broker's minimum brokerage and DP tariff, precise charge bases and rounding still need review. The existing cost model does not include minimum brokerage, SEBI turnover fees, or statutory rounding. These entries must not be treated as a verified cost-inclusive simulation.

No real-data backtest or profitability evaluation is run by this evidence command. A successful report build is not a readiness approval.

Exports in the selected output directory: `trades.csv`, `equity_curve.csv`, `ledger.csv`, `corporate_actions.csv`, `metrics.json`, and `manifest.json` with run configuration, input fingerprint, date range, symbols, synthetic flag, adjustment policy, action coverage, and execution policy. Metrics include gross/net closed-trade P&L, return, CAGR when meaningful, max drawdown, annualized Sharpe/Sortino conventions, gross profit factor, win rate, average win/loss, session exposure (share of sessions with an open position), turnover, costs, and optional benchmark price return. Undefined statistics remain `null` when there are no trades, insufficient time, or zero return variance. Benchmark symbol data is report-only and is not traded; its price return excludes dividends unless the supplied prices are adjusted.

## Offline demo and quality checks

```powershell
python -m nse_swing_agent.demo
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Synthetic OHLCV used by the demo and accounting tests is explicitly artificial. Retained historical provider and exchange source files are separately identified with provenance and are not presented as complete or backtest-ready data. Backtests, paper fills, and historical simulation cannot prove profitability or establish a guaranteed stop loss.

## Milestone 2I bounded validation

`data/validation/milestone_2i/` contains six RELIANCE sessions selected from the already cached TejHQ raw, unadjusted OHLCV response, plus a sourced exchange-calendar excerpt. The OHLCV rows are provider-sourced and schema-validated, but were not independently compared with official bhavcopy and contain no verified ISIN. The NSE holiday-master source confirms 2024-10-02 as a holiday; 2024-10-10 is intentionally absent from the bounded sample and is classified unresolved by the gap audit. The fixture builder refuses to overwrite different evidence:

```powershell
$env:PYTHONPATH = "src"
python scripts/build_m2i_fixture.py
python scripts/validate_m2i_fixture.py
python -m pytest tests/test_milestone_2i.py tests/test_corporate_actions.py
```

`reports/milestone_2i/validation_report.md` separates provider facts, the one exchange-verified calendar fact, synthetic accounting test cases and unverified assumptions. It does not run the strategy or backtester. Split, bonus and dividend accounting tests use synthetic unit fixtures; they do not verify any real event terms. `docs/cost_model_specification.md` lists the missing effective-date, tariff, calculation-base, aggregation and rounding inputs. The existing Milestone 2H real-data readiness gate remains blocked; validating this fixture cannot override it.

## Milestone 2J-A controlled recovery and action coverage

The eight source-reconciled NSE RELIANCE bars from Milestone 2H can be revalidated into a **separate candidate-only** dataset. Use a new output directory for this milestone so the earlier Milestone 2J evidence stays unchanged:

```powershell
$env:PYTHONPATH = "src"
python scripts/build_m2j_recovery_candidate.py --output data/validation/recovery_candidates/milestone_2j_a_v2
python scripts/audit_corporate_action_coverage.py --output reports/milestone_2j_a_v4
python scripts/build_m2j_reports.py --milestone 2J-A --candidate data/validation/recovery_candidates/milestone_2j_a_v2/recovery_manifest.json --output-dir reports/milestone_2j_a_v4
```

The candidate builder verifies preserved report-file hashes, report date, NSE EQ series, RELIANCE/INE002A01018 identity, OHLCV and absence from the provider dataset, then validates candidate rows against the canonical loader. Its manifest carries raw-source and input fingerprints; unavailable or changed source bytes are marked incomplete. Candidate bars are not merged, and existing outputs are write-once. `reports/milestone_2j_a_v4/corporate_action_coverage.json` checks each registry row against the immutable TejHQ response and distinguishes provider discovery, partial corroboration and independently fingerprinted verified terms; missing accounting terms and applicable unresolved event dates are listed. The action feed explicitly does not guarantee complete historical coverage; an event absent from that feed is not evidence that the event did not occur. The report therefore retains a blocked decision. Neither command runs a strategy or backtest, verifies every event term, or changes cost assumptions.
# Versioned delivery-cost evidence

Milestone 2J-B adds a Decimal, effective-dated Zerodha delivery-cost profile scoped to NSE/BSE resident-individual cash delivery. The supplied profile is intentionally **partial** and fails closed; it does not establish complete historical fees or enable a real-data backtest. See [`docs/milestone_2j_b_cost_model.md`](docs/milestone_2j_b_cost_model.md), the [profile](config/cost_profiles/zerodha_resident_individual_delivery_v2_partial.json), [provenance manifest](data/reference/cost_profiles/milestone_2j_b/provenance_manifest.json), and [coverage report](reports/milestone_2j_b/readiness.md).

The CLI accepts an explicit versioned profile with `--cost-profile`, `--cost-exchange`, `--account-category resident_individual`, and `--dp-holder-category`. The profile currently refuses total-cost quotes because historical coverage, BSE tariff inputs, and multiple rounding/tax details remain unresolved. A non-synthetic backtest remains blocked by cost and independent data/corporate-action readiness checks. No profitability evaluation was run.

## Milestone 2J-C tariff evidence

The historical Zerodha delivery tariff reconciliation is documented in [docs/milestone_2j_c_tariff_reconciliation.md](docs/milestone_2j_c_tariff_reconciliation.md). Its versioned profile, [coverage report](reports/milestone_2j_c/readiness.md), and provenance manifest are partial and fail closed. No real-data backtest or profitability evaluation was run; source retrieval failures and missing rounding/BSE inputs keep readiness BLOCKED.

## Milestone 2K historical readiness audit

The reproducible audit command is `python scripts/build_milestone_2k_readiness_audit.py --output reports/milestone_2k_v4`. It compares RELIANCE provider rows with the retained, sourced NSE calendar for 2018–2024, fingerprints the provider dataset, calendar, separate eight-bar recovery candidate, corporate-action registry/raw response and the Milestone 2K official-document archive, then writes CSV, JSON and Markdown evidence. The output directory is write-once; select a new versioned `--output` path if it already exists. The audit does not merge candidates or run a strategy/backtest. NSE circular MSD59999 is retained and identifies 2024-01-20 as a special live equity session, correcting the baseline calendar's generic Saturday label in this report only.

The audit is RELIANCE-only. Provider data extends through 2026-10-22, but the day-by-day calendar comparison ends in 2024; retained 2025/2026 holiday circulars and issuer filings are selected evidence, not a full later calendar or proof of corporate-action completeness. Corporate-action feed rows are reconciled to their raw fingerprint, while missing terms, conflicting evidence, unsupported rights/demerger accounting and events absent from the discovery feed remain blockers. Cost profile coverage is unchanged and incomplete. See [the Milestone 2K readiness report](reports/milestone_2k_v4/readiness.md) and machine-readable [audit](reports/milestone_2k_v4/audit.json). Readiness remains BLOCKED; no real-data performance evaluation was run.

## Milestone 2L RELIANCE corporate-action audit

Run `python scripts/build_milestone_2l_audit.py --output reports/milestone_2l_v1` to rebuild the write-once audit from the preserved TejHQ registry/raw response and archived official sources. It groups the 25 provider rows into 21 economic events, verifies matching NSE/BSE representations, reconciles a separately archived symbol-bound NSE action response, and records per-event terms, unresolved fields, source hashes and accounting status. The source response is not treated as proof of complete history; it returns 20 rows and the missing 2010 event remains unresolved against that response.

The audit resolves the 2025 RIL dividend record date to August 14, 2025 using the issuer filing and symbol-bound NSE data. The August 13 observation in an older note came from an unfiltered NSE page and was not a RELIANCE-specific conflict. The exact payment date remains unknown. For the 2026 dividend, RIL confirms ₹6/share, the June 5 record date, and a seven-day payment window after the June 19 AGM, but the actual payment date is not established. Exact payment dates remain unresolved for all 17 dividend events. Four event-term records are fully verified (the 2017 and 2024 bonuses, 2020 rights, and 2023 JFSL demerger), 11 are partially corroborated, and six older dividend records remain unresolved on dates; rights and demerger accounting are still unsupported. Historical costs, full action coverage, and broader data-integrity gates continue to block readiness. See [the report](reports/milestone_2l_v1/readiness.md), [event audit](reports/milestone_2l_v1/corporate_action_audit.json), and [source manifest](reports/milestone_2l_v1/source_manifest.json). No backtest or profitability evaluation was run.

\n
## Milestone 2M — RELIANCE action accounting and coverage audit

The Milestone 2M audit preserves the prior Milestone 2L artifacts and adds archived
issuer/exchange annual reports. The 2010 provider dividend is tied to its existing
event group. Reviewed annual-report copies support the Board recommendation date,
₹7 per share and 2010-05-11 record date; primary-source ex-date confirmation,
shareholder approval evidence and the payment date/window remain unresolved. The
2020 and 2021 issuer annual reports document payment windows, not exact account
posting dates.

The current dividend accounting requires an exact payment date and does not substitute
a window boundary for cash availability. Rights and demerger accounting remains
unsupported and blocks affected evaluation periods. No bounded real-data period meets
all corporate-action, data, calendar and verified-cost gates. No real-data backtest was
run. See [Milestone 2M readiness](reports/milestone_2m_v4/readiness.md), its
[machine-readable audit](reports/milestone_2m_v4/corporate_action_audit.json), and
[source manifest](reports/milestone_2m_v4/source_manifest.json).

The write-once audit builder defaults to `reports/milestone_2m_v2` and refuses to
overwrite existing outputs. Choose a new output directory for another run:

```powershell
python scripts/build_milestone_2m_audit.py --output reports/milestone_2m_v6
```

## Milestone 2O — Session calendar and data-readiness audit

`data/reference/milestone_2o/session_calendar_exceptions_v1.json` records verified,
date-specific corrections separately from the immutable NSE 2018–2024 source calendar.
It promotes 2024-01-20 from the base calendar's generic weekend label to
`SPECIAL_SESSION`, based on archived NSE Circular MSD59999. The audit builder
re-hashes the base calendar and source bytes, writes a separate effective calendar,
and refuses to overwrite existing versioned outputs:

```powershell
python scripts/build_milestone_2o_audit.py --output reports/milestone_2o_v4
```

The current report is [Milestone 2O v4](reports/milestone_2o_v4/readiness.md), with
[date-by-date audit](reports/milestone_2o_v4/date_by_date_calendar_audit.csv) and
[machine-readable findings](reports/milestone_2o_v4/audit.json). The audit distinguishes
verified holidays and special sessions from ordinary session expectations inferred
from NSE's weekly rule and annual holiday master. It records observed TejHQ bars and
unmerged official recovery candidates separately. It does not infer exchange closures
from missing provider rows.

The calendar covers 2018-01-01 through 2024-12-31. The provider history after that
calendar ends at 2026-10-22 and lacks a full date-by-date official session calendar.
Provider canonical bars identify symbol but lack ISIN and series; RELIANCE-only
evidence does not establish full-market coverage. The eight recovery candidates remain
standalone and are rehashed against their source files and Milestone 2K reconciliation.
All global data, corporate-action and cost readiness gates remain blocked.

### Dividend payment timing

Dividend actions distinguish `exact_date`, `documented_window`, and `unknown`
payment timing. Legacy actions with an explicit `payment_date` preserve exact-date
cash credit and receive an evidence reference from their source and fingerprint.
Window actions require ordered earliest/latest dates and a source reference; those
dates never become an exact payment date. When a position is entitled to a dividend
with window or unknown timing, the backtester raises a structured blocking error and
returns no portfolio path. It does not credit cash at either bound. The error carries
the receivable amount, timing state, bounds, evidence reference and source fingerprint.

The preserved versioned payment-timing readiness addendum is under
`reports/milestone_2m_v5/`. Its builder refuses to overwrite it. To create another
snapshot, select a new output path:

```powershell
python scripts/build_m2m_payment_timing_readiness.py --output-dir reports/milestone_2m_v6/payment_timing
```

The readiness report classifies the 17 dividends as 0 exact dates, 3 bounded windows,
and 14 unknown actionable timings (including 3 prose-only windows that lack explicit
bounds). Window and unknown timing remain unsupported for portfolio simulation.
