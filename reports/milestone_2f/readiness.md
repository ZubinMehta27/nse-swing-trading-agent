# Milestone 2F — Historical gap classification and recovery readiness

**Decision: BLOCKED. No backtest or profitability evaluation was run.**

## Results

The exact 104 dates were read from `reports/milestone_2e_readiness.json`; they were not re-created from weekdays. All 104 are now classified: **100 confirmed NSE CM exchange holidays** and **4 provider/source discrepancies**. Unresolved: 0.

The full 2018–2024 date calendar has 2,557 rows. NSE states equities trade all days except Saturdays, Sundays and holidays declared in advance; the seven year-filtered official CM trading holiday API responses supply closure dates. The 104 target dates are emitted as a separate subset calendar. Ordinary sessions are derived from the general weekly rule minus published holidays, not individually corroborated by bhavcopy. The exact source URL, applicable year, retrieval timestamp, HTTP status, raw file SHA-256 and limitations are in [`nse_cm_calendar_2018_2024.provenance.json`](../../data/reference/nse_cm_calendar_2018_2024.provenance.json). The original API responses, circulars and four special-session bhavcopies are preserved under `data/raw/nse/`.

## Classification counts by month

| Month | Exchange holiday | Provider/source discrepancy | Unresolved |
|---|---:|---:|---:|
| 2018-01 | 1 | 0 | 0 |
| 2018-02 | 1 | 0 | 0 |
| 2018-03 | 3 | 0 | 0 |
| 2018-05 | 1 | 0 | 0 |
| 2018-08 | 2 | 0 | 0 |
| 2018-09 | 2 | 0 | 0 |
| 2018-10 | 2 | 0 | 0 |
| 2018-11 | 2 | 1 | 0 |
| 2018-12 | 1 | 0 | 0 |
| 2019-03 | 2 | 0 | 0 |
| 2019-04 | 3 | 0 | 0 |
| 2019-05 | 1 | 0 | 0 |
| 2019-06 | 1 | 0 | 0 |
| 2019-08 | 2 | 0 | 0 |
| 2019-09 | 2 | 0 | 0 |
| 2019-10 | 4 | 0 | 0 |
| 2019-11 | 1 | 0 | 0 |
| 2019-12 | 1 | 0 | 0 |
| 2020-02 | 1 | 0 | 0 |
| 2020-03 | 1 | 0 | 0 |
| 2020-04 | 4 | 0 | 0 |
| 2020-05 | 2 | 0 | 0 |
| 2020-10 | 1 | 0 | 0 |
| 2020-11 | 2 | 0 | 0 |
| 2020-12 | 1 | 0 | 0 |
| 2021-01 | 1 | 0 | 0 |
| 2021-03 | 2 | 0 | 0 |
| 2021-04 | 3 | 0 | 0 |
| 2021-05 | 1 | 0 | 0 |
| 2021-07 | 1 | 0 | 0 |
| 2021-08 | 1 | 0 | 0 |
| 2021-09 | 1 | 0 | 0 |
| 2021-10 | 1 | 0 | 0 |
| 2021-11 | 2 | 1 | 0 |
| 2022-01 | 1 | 0 | 0 |
| 2022-03 | 2 | 0 | 0 |
| 2022-04 | 2 | 0 | 0 |
| 2022-05 | 1 | 0 | 0 |
| 2022-08 | 3 | 0 | 0 |
| 2022-10 | 2 | 1 | 0 |
| 2022-11 | 1 | 0 | 0 |
| 2023-01 | 1 | 0 | 0 |
| 2023-03 | 2 | 0 | 0 |
| 2023-04 | 3 | 0 | 0 |
| 2023-05 | 1 | 0 | 0 |
| 2023-06 | 1 | 0 | 0 |
| 2023-08 | 1 | 0 | 0 |
| 2023-09 | 1 | 0 | 0 |
| 2023-10 | 2 | 0 | 0 |
| 2023-11 | 2 | 0 | 0 |
| 2023-12 | 1 | 0 | 0 |
| 2024-01 | 2 | 0 | 0 |
| 2024-03 | 3 | 0 | 0 |
| 2024-04 | 2 | 0 | 0 |
| 2024-05 | 2 | 0 | 0 |
| 2024-06 | 1 | 0 | 0 |
| 2024-07 | 1 | 0 | 0 |
| 2024-08 | 1 | 0 | 0 |
| 2024-10 | 1 | 0 | 0 |
| 2024-11 | 2 | 1 | 0 |
| 2024-12 | 1 | 0 | 0 |

## Four special sessions with verified RELIANCE EQ bars

These dates are not ordinary sessions. NSE annual/special-session circulars identify Muhurat trading, and date-specific bhavcopies carry the corresponding session date. Each has one RELIANCE `EQ` row with ISIN `INE002A01018`. The official OHLCV, raw filenames, retrieval metadata, hashes, and unmerged recovery candidates are in [`recovery_manifest.json`](recovery_manifest.json).

| Date | NSE O/H/L/C / volume | Source |
|---|---|---|
| 2018-11-07 | 1115 / 1115 / 1106.7 / 1110.7 / 1283997 | cm07NOV2018bhav.csv.zip |
| 2021-11-04 | 2492.95 / 2504.9 / 2490 / 2498.85 / 787160 | cm04NOV2021bhav.csv.zip |
| 2022-10-24 | 2460 / 2502.5 / 2455.3 / 2479.85 / 1555270 | cm24OCT2022bhav.csv.zip |
| 2024-11-01 | 1333.05 / 1341.95 / 1333.00 / 1338.65 / 2127335 | BhavCopy_NSE_CM_0_0_0_20241101_F_0000.csv.zip |

All four are `provider_source_discrepancy`: TejHQ has no row; NSE does. The source reports are unadjusted exchange OHLCV, consistent with TejHQ `/v1/ohlcv` raw-unadjusted price convention. No prices were merged. Adjusted close cannot substitute for these raw bars, and corporate-action-aware holdings/cash effects are not implemented.

## Reproducible audit

Build the date calendar from the preserved official JSON responses, then audit the exact 104-date subset against four necessary special-session daily reports:

```powershell
python scripts/build_nse_cm_calendar.py
python -m nse_swing_agent audit-gaps data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv --calendar data/reference/nse_gap_calendar_2018_2024.csv --source-file data/raw/nse/cm07NOV2018bhav.csv.zip --source-file data/raw/nse/cm04NOV2021bhav.csv.zip --source-file data/raw/nse/cm24OCT2022bhav.csv.zip --source-file data/raw/nse/BhavCopy_NSE_CM_0_0_0_20241101_F_0000.csv.zip --output reports/milestone_2f/audit-2018-2024
```

Audit outputs: [`gap_audit.csv`](audit-2018-2024/gap_audit.csv), [`gap_audit.json`](audit-2018-2024/gap_audit.json), [`gap_audit.md`](audit-2018-2024/gap_audit.md). The audit has no automatic fill path. Validation success is separate from HTTP retrieval status; official source files were retrieved successfully (HTTP 200) and parsed.

## Remaining blockers

- Four raw bars are verified but only candidates; recoveries are not merged into the existing TejHQ file or response.
- The 104 weekday omissions are explained as exchange holidays or verified special-session provider omissions. The special sessions have unusual timing and should remain tagged as such in any future derived dataset.
- Corporate-action-aware position quantity and dividend cash treatment remains unimplemented.
- No sourced, date-effective, verified nonzero cost profile is configured.

Next step: review the four raw replacement candidates and decide a separately versioned derived dataset policy; then implement and test corporate-action accounting and validate dated cost inputs before any real-data evaluation.

The four previously verified 2026 NSE reports and their classifications remain preserved in the [Milestone 2E evidence](../milestone_2e_official_gap_evidence.json).
