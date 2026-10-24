# Milestone 2P — Independent bar verification and NSE calendar extension

**Decision: BLOCKED. No strategy backtest or profitability evaluation was run.**

## 2024-01-20 RELIANCE bar

The archived NSE CM bhavcopy contains exactly one RELIANCE EQ / INE002A01018 row. Its open, high, low, close and total traded quantity match the TejHQ row numerically at source precision. The source identifies symbol, series, ISIN and trading date. Session verification and OHLCV verification are recorded separately.

Official source SHA-256: `2c41ce167656f708e32e1106b98e0dbb68588cf26209b4a7486d747902a52c27`. Raw provider and canonical files were not changed.

## Calendar scope and evidence standard

A derived daily calendar now covers 2018-01-01 through 2026-10-22. 2025 and 2026 holiday evidence comes from NSE Capital Market circulars; special sessions override generic weekend or holiday classifications. Ordinary weekdays and weekends are classified using the official equities weekly rule plus the dated CM holiday schedule. This is a rule-based expectation, not individual bhavcopy proof for every day.

Unresolved calendar dates: 2018-03-25, 2018-04-14, 2018-06-16, 2019-01-26, 2019-04-13, 2019-04-14, 2019-10-27, 2020-01-26, 2020-08-01, 2020-08-15, 2020-08-22, 2020-08-30, 2020-10-25, 2020-11-14, 2021-04-25, 2021-05-01, 2021-08-15, 2021-10-02, 2021-12-25, 2022-04-10, 2022-05-01, 2022-07-10, 2022-10-02, 2022-12-25, 2023-02-18, 2023-04-22, 2023-07-29, 2023-11-12, 2024-03-02, 2024-04-14, 2024-04-21, 2024-09-07, 2024-10-12, 2024-11-02

Provider omissions on expected sessions: 1; exact dates are listed in `audit.json` and `date_by_date_audit.csv`. A provider omission is not treated as an exchange closure.

The 2025-02-01 Saturday live session and 2025-10-21 Muhurat session are separately evidenced. The 2026-01-15 Maharashtra municipal-election holiday is a CM-specific correction. F&O and settlement schedules were not used to define cash-equity sessions.

## Instrument and remaining readiness limits

The provider dataset remains RELIANCE-only and its canonical rows lack ISIN, exchange and series. The eight recovery candidates remain separate and unmerged. Full-market or point-in-time-universe coverage is not established.

Corporate-action completeness and verified historical transaction costs remain independent BLOCKED gates. Calendar and RELIANCE bar validation do not establish performance validity or profitability.

See `reports/milestone_2p_v1/audit.json`, `date_by_date_audit.csv`, the versioned calendar registry and source archive manifest for evidence and fingerprints. The derived calendar is `data/reference/milestone_2p/calendar_2018_2026-10-22_v1.csv`.
