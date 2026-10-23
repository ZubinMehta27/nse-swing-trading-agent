# Milestone 2E — Historical verification readiness

**Decision: BLOCKED. No backtest or profitability evaluation was run.**

## Four 2026 dates

The original official NSE CM-UDiFF ZIP files are preserved in `data/raw/nse/`; TejHQ files were not changed. Each embedded CSV passed structural parsing, has exactly one date-specific RELIANCE EQ security row, and reports ISIN `INE002A01018`. All four dates are absent from the imported TejHQ CSV. NSE OHLCV is unadjusted bhavcopy data; no rows were merged automatically. Detailed values, UTC retrieval times, URLs, filenames and SHA-256 hashes are in [`milestone_2e_official_gap_evidence.json`](milestone_2e_official_gap_evidence.json).

| Date | Classification | NSE O/H/L/C/volume |
|---|---|---|
| 2026-06-05 | Confirmed provider/source discrepancy | 1304.50 / 1306.00 / 1288.00 / 1291.00 / 17785223 |
| 2026-06-15 | Confirmed provider/source discrepancy | 1315.30 / 1325.00 / 1303.30 / 1307.00 / 18633321 |
| 2026-06-16 | Confirmed provider/source discrepancy | 1313.40 / 1333.40 / 1306.40 / 1328.80 / 18513223 |
| 2026-06-22 | Confirmed provider/source discrepancy | 1316.70 / 1344.90 / 1314.10 / 1326.50 / 12931213 |

## 2018–2024 weekday gaps

All 104 dates are individually retained below and currently classified **unresolved**. No holiday conclusions are inferred from weekdays. The historical-report page documents NSE report archives and UDiFF common bhavcopy availability, but we have not attached an authoritative calendar or official daily file for these dates yet. Thus the audit distinguishes missing evidence from a confirmed exchange holiday or absent RELIANCE row.

### 2018

2018-01-26, 2018-02-13, 2018-03-02, 2018-03-29, 2018-03-30, 2018-05-01, 2018-08-15, 2018-08-22, 2018-09-13, 2018-09-20, 2018-10-02, 2018-10-18, 2018-11-07, 2018-11-08, 2018-11-23, 2018-12-25

### 2019

2019-03-04, 2019-03-21, 2019-04-17, 2019-04-19, 2019-04-29, 2019-05-01, 2019-06-05, 2019-08-12, 2019-08-15, 2019-09-02, 2019-09-10, 2019-10-02, 2019-10-08, 2019-10-21, 2019-10-28, 2019-11-12, 2019-12-25

### 2020

2020-02-21, 2020-03-10, 2020-04-02, 2020-04-06, 2020-04-10, 2020-04-14, 2020-05-01, 2020-05-25, 2020-10-02, 2020-11-16, 2020-11-30, 2020-12-25

### 2021

2021-01-26, 2021-03-11, 2021-03-29, 2021-04-02, 2021-04-14, 2021-04-21, 2021-05-13, 2021-07-21, 2021-08-19, 2021-09-10, 2021-10-15, 2021-11-04, 2021-11-05, 2021-11-19

### 2022

2022-01-26, 2022-03-01, 2022-03-18, 2022-04-14, 2022-04-15, 2022-05-03, 2022-08-09, 2022-08-15, 2022-08-31, 2022-10-05, 2022-10-24, 2022-10-26, 2022-11-08

### 2023

2023-01-26, 2023-03-07, 2023-03-30, 2023-04-04, 2023-04-07, 2023-04-14, 2023-05-01, 2023-06-29, 2023-08-15, 2023-09-19, 2023-10-02, 2023-10-24, 2023-11-14, 2023-11-27, 2023-12-25

### 2024

2024-01-22, 2024-01-26, 2024-03-08, 2024-03-25, 2024-03-29, 2024-04-11, 2024-04-17, 2024-05-01, 2024-05-20, 2024-06-17, 2024-07-17, 2024-08-15, 2024-10-02, 2024-11-01, 2024-11-15, 2024-11-20, 2024-12-25

## Reusable tooling

`nse-swing-agent audit-gaps OBSERVED.csv --calendar CALENDAR.csv --source-file NSE_BHAVCOPY.zip --output OUTPUT_DIR` accepts an explicit `session_date,status,source` calendar (status `SESSION`/`HOLIDAY`) and strict verified NSE UDiFF or legacy bhavcopy schemas. It emits CSV/JSON/Markdown, fingerprints original source files and never fills missing bars. Successful retrieval is recorded separately from validation. The current tool supports ZIP containing exactly one CSV and direct CSV.

## Readiness blockers

- Historical calendar and bhavcopy evidence for the 104 dates remains unresolved.
- The four June 2026 sessions are classified as provider omissions with official replacement evidence available, but the source series remains unmodified pending an explicit reviewed import decision.
- Corporate actions are not applied to held quantity/cash; adjusted price conversion remains unsupported.
- No verified, date-effective nonzero cost profile exists.

Next step: produce a sourced NSE session calendar covering 2018–2024 and attach official daily reports for each session gap; resolve missing dates from reviewed source data, then implement and test corporate-action accounting and verify fees before any real-data evaluation.

NSE archive reference: [Historical Reports — Capital Market Daily/Monthly Archives](https://www.nseindia.com/static/resources/historical-reports-capital-market-daily-monthly-archives).
