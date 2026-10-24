# Milestone 2Q — RELIANCE 2025-10-21 reconciliation

**Decision: BLOCKED. Evidence-only validation; no backtest or profitability evaluation was run.**

NSE’s official CM Muhurat circular verifies the session. The official CM-UDiFF final bhavcopy was retrieved and validated. The archive contains exactly one RELIANCE EQ / INE002A01018 row. OHLCV: 1468.00 / 1474.00 / 1460.00 / 1465.20 / 2,066,169.

The existing TejHQ canonical dataset has 0 rows for this symbol/date. The source outcome is `official_bar_present_provider_row_missing`. The official row is not merged or appended.

Archive: `data/raw/nse/BhavCopy_NSE_CM_0_0_0_20251021_F_0000.csv.zip`; SHA-256 `729f028f4dfde2d7dca1abca7b0277a87c4ca950dd0fd5d180ba8fc48c0b6456`; downloaded at 2026-10-24T13:36:27.216539+00:00 UTC.

The canonical dataset, raw provider response and eight prior recovery candidates remain unchanged. Overall readiness remains blocked by broader session/bar coverage, corporate-action completeness, historical transaction-cost evidence, and instrument/universe identity coverage.

See `reconciliation.json` for all identity fields, source schema, exact field mapping, validation status and provenance. `provenance.json` records retrieval metadata.
