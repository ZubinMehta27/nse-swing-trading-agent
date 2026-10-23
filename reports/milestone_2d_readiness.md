# Milestone 2D — Historical coverage and corporate-action readiness

Audit date: 2026-10-23. This is a data and implementation audit only. No backtest or profitability evaluation was run. PAPER TRADING ONLY.

## A. Historical coverage

Command run:

```powershell
python -m nse_swing_agent fetch-history --symbol RELIANCE --from 2018-01-01 --to 2026-10-23
```

TejHQ returned **2,166 rows**, requested `2018-01-01..2026-10-23`, actual `2018-01-01..2026-10-22`. Its keyless `/v1/status` returned `trading_date=2026-10-22`, matching the latest bar. The existing canonical validator accepted the normalized CSV: 1 symbol, 2,166 rows, schema `1.0`, no duplicate sessions, and no missing required cells. OHLC validity also passed through `load_historical_file`/`OHLCVBar`.

Raw response SHA-256: `fd48f50f69338ee1f9b705bd889af7e7f0c8767751dfa0ab5126be6c7e502633`.

- Raw OHLCV: [provider JSON](../data/raw/nse/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.json)
- Normalized bars: [canonical CSV](../data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv)
- Fetch provenance: [manifest](../data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.json)
- Provider freshness response: [raw status JSON](../data/raw/nse/tejhq_status_20261023T103747Z_566af175d4.json), SHA-256 `566af175d4e2e1366311db508f3b8cba8c083be6a65d3797c8005f6714dfd991`.

There are **135 weekdays without a RELIANCE bar between adjacent returned sessions**. Those are not automatically data errors: NSE is closed on many such dates. The 14 gaps in 2025 match the [NSE Capital Market 2025 holiday circular](https://nsearchives.nseindia.com/content/circulars/CMTR65587.pdf); the 13 gaps in 2026 through October match the [NSE equities holiday calendar](https://www.nseindia.com/resources/exchange-communication-holidays?apiversion=v2). Four 2026 weekdays are outside that calendar and remain unexplained: **2026-06-05, 2026-06-15, 2026-06-16, 2026-06-22**. June 5 is also the ex-date of a RELIANCE dividend in the action response. The **104 weekday gaps from 2018–2024** have not been checked against archived annual calendars and remain unclassified. No rows were imputed, and continuity cannot be considered fully established.

The exact imported dataset was also run through:

```powershell
python -m nse_swing_agent validate data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv --cache-dir data/cache --source "TejHQ /v1/ohlcv; raw_unadjusted"
```

Result: `status=valid`, 2,166 rows, 1 symbol, date range `2018-01-01..2026-10-22`.

## B. Corporate actions and adjustments

The keyless [TejHQ `/v1/actions/{symbol}` contract](https://tejhq.dev/docs) describes action rows with exchange, symbol/ISIN, ex-date, record date, type, ratio/cash/face-value metadata, and raw source subject. The published action schema supports `dividend`, `split`, `bonus`, `rights`, `buyback`, `demerger`, `merger`, `agm`, and `other`; provider documentation describes the feed as all recorded actions, without a completeness guarantee. An actual `/v1/actions/RELIANCE` response was saved unchanged: 25 rows over `2010-05-10..2026-06-05`, covering both NSE and BSE. Observed types: 20 dividends, 3 bonuses, 1 demerger, 1 rights issue. The API result contains both-exchange duplicates for some events. It did not contain split, buyback, merger, rename, or delisting rows; absence in this symbol response does not prove those event classes are fully represented or absent historically.

- Raw action response: [JSON](../data/raw/nse/tejhq_actions_RELIANCE_20261023T103451Z_4b305e0765.json)
- SHA-256: `4b305e0765bd8a1b0e32ee4074d7343c81cefd99e8231e1275a9e793952bf777`
- Audit metadata: [`milestone_2d_readiness.json`](milestone_2d_readiness.json)

The provider’s [adjusted-price schema](https://huggingface.co/datasets/tejhq/indian-markets) documents `adj_factor_cumulative` and `adj_close = close * adj_factor_cumulative`; it does **not** define adjusted open, high, or low. The raw OHLC columns remain unadjusted. The cumulative factor is based on actions after each price date, across the provider’s instrument chain. Published conventions are split `face_value_to / face_value_from`, bonus `M / (N+M)`, dividend `(previous-session close - cash) / previous-session close`; rights, buybacks, demergers, and mergers carry factor 1.0 under its stated NSE convention. Factors therefore model continuity for split/bonus/dividend close series, not every economic entitlement or cash flow.

The actual adjusted REST endpoint was probed for one short range without a provider key and returned HTTP 401 `key_required`. No key was present or requested, so no adjusted API row payload was inspected. The published Parquet schema supports the close-only finding, but exact REST response rows remain unverified. TejHQ documents a separate symbol-history tree and `/v1/symbols` endpoint with ISIN-to-symbol validity intervals; the dataset reports NSE coverage since 2010-01-04. This represents ticker intervals for identified instrument chains, but no explicit delisting event/status is described, and the symbol API payload was not inspected here because it requires a free key. A last observation or `valid_to` date should not be interpreted as a confirmed delisting notice. The provider itself notes that action-source classification can retain `other` and that raw-source, missing-day, duplicate, and per-type coverage audits are outstanding ([pipeline notes](https://github.com/tejhq/tej-bazaar/blob/master/README.md), [adjustment postmortem](https://tejhq.dev/blog/the-split-that-broke-adjusted-prices)).

## C. Execution and costs

- **Signal timing:** signals use completed session closes; pending buys are eligible only on a later observed session for that symbol.
- **Stops:** opening gaps use the open then adverse sell slippage; an intraday touch uses the stop then slippage. If stop and target are both touched, stop wins. Daily OHLC cannot establish intraday order; a stop is not a guaranteed real fill.
- **Limits and orders:** buy orders are rejected over the volume cap, position limit, or available cash including modeled fees. The simulator uses a per-symbol pending dictionary (one pending buy per symbol); it does not submit to `PaperBroker`. The local paper broker separately has deterministic idempotent client order IDs.
- **Fees:** brokerage, side-specific STT, exchange turnover charge, GST on brokerage plus exchange charge, buy stamp duty, and sell-side DP per share are calculated once per filled ledger entry. Existing tests compare trade costs with filled ledger costs. Minimum brokerage, rounding, broker tiers, and some regulatory levies are not modeled.
- **Corporate actions:** positions are not quantity-adjusted for splits/bonuses, dividend cash is not credited, and rights/demerger/merger handling is absent. Backtester price and position state stays in the input convention. Adjusted-price conversion is not implemented.

Added a validated versioned cost profile with effective start/end, source, verification status, and all rate fields in `config/cost_profile.example.json`. It is explicitly zero and unverified. A run labeled `--cost-inclusive` now requires a sourced `verified` profile with at least one nonzero rate covering the evaluation dates. No real-world rates are supplied or asserted.

The backtester now rejects any input adjustment policy other than `raw_unadjusted` until a tested conversion and action-aware holdings/cash model is implemented. The current raw series still warns about corporate-action discontinuities.

## D. Readiness decision

**Real-data performance evaluation is not ready.** The data validates structurally, and the latest returned session matches the provider status, but four 2026 weekday bars are unexplained and 104 earlier weekday gaps are unclassified. Provider adjusted data is close-only and the adjusted REST response was unavailable without a key. The simulator does not apply corporate actions to holdings or cash, and no sourced verified nonzero cost profile exists. No backtest was run.

Next step: resolve the four 2026 session omissions against official source data, classify 2018–2024 calendar gaps, then design and test a corporate-action-aware raw execution/adjusted feature policy and verify a complete date-effective cost profile. Only after those reviews should a real-data backtest be considered.
