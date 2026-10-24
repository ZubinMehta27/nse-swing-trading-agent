# Milestone 2P — Independent bar verification and NSE calendar extension

**Decision: BLOCKED. No strategy backtest or profitability evaluation was run.**

## 2024-01-20 RELIANCE bar

The archived NSE CM bhavcopy contains exactly one RELIANCE EQ / INE002A01018 row. Its open, high, low, close and total traded quantity match the TejHQ row numerically at source precision. The source identifies symbol, series, ISIN and trading date. Session verification and OHLCV verification are recorded separately.

Official source SHA-256: `2c41ce167656f708e32e1106b98e0dbb68588cf26209b4a7486d747902a52c27`. Raw provider and canonical files were not changed.

Across 2166 TejHQ rows, 1 has independent official OHLCV verification in this audit; the remaining 2165 are not independently source-checked here. The CSV records verification status date by date.

## Calendar scope and evidence standard

A derived daily calendar now covers 2018-01-01 through 2026-10-22. 2025 and 2026 holiday evidence comes from NSE Capital Market circulars; special sessions override generic weekend or holiday classifications. Ordinary weekdays and weekends are classified using the official equities weekly rule plus the dated CM holiday schedule. This is a rule-based expectation, not individual bhavcopy proof for every day.

Unresolved calendar dates: None within the sourced date range; ordinary dates still follow the stated inference standard.

Provider omissions on expected sessions: 1; exact dates are listed in `audit.json` and `date_by_date_audit.csv`. A provider omission is not treated as an exchange closure.

The 2025-02-01 Saturday live session and 2025-10-21 Muhurat session are separately evidenced. The 2026-01-15 Maharashtra municipal-election holiday is a CM-specific correction. F&O and settlement schedules were not used to define cash-equity sessions.

## Instrument and remaining readiness limits

The provider dataset remains RELIANCE-only and its canonical rows lack ISIN, exchange and series. The eight recovery candidates remain separate and unmerged. Full-market or point-in-time-universe coverage is not established.

Four older candidate source timestamps remain local-file-mtime proxies. Candidate bytes and source fingerprints match existing manifests and the prior Milestone 2K audit, but those proxies are not verified retrieval times.

Corporate-action completeness and verified historical transaction costs remain independent BLOCKED gates. Calendar and RELIANCE bar validation do not establish performance validity or profitability.

See `reports/milestone_2p_v5/audit.json`, `date_by_date_audit.csv`, the versioned calendar registry and source archive manifest for evidence and fingerprints. The derived calendar is `data/reference/milestone_2p/calendar_2018_2026-10-22_v5.csv`.
