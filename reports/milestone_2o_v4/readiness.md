# Milestone 2O — Session calendar and data-readiness audit

**Decision: BLOCKED. No real-data backtest or profitability evaluation was run.**

The original NSE calendar and historical dataset are unchanged. A separate verified exception registry promotes 2024-01-20 from the source calendar's WEEKEND label to SPECIAL_SESSION in a derived effective calendar. NSE Circular MSD59999, dated 2023-12-28, explicitly designates this a special live equity session. SHA-256: `614b965d1152ed636052e983a01206117ff6af224365348fa00b7165a6baa243`.

The RELIANCE TejHQ file has 2166 observed rows. Its canonical schema has symbol but no ISIN or series. The date-by-date CSV separates observed bars from calendar expectations. Ordinary sessions derive from the weekly rule and holiday master; missing bars are not classified as holidays.

All 8 candidate bars were re-hashed against their source records and Milestone 2K reconciliation. They remain in a separate candidate file and were not merged.

The NSE daily calendar evidence ends 2024-12-31; provider history after that date lacks a full session calendar. Provider and candidate evidence cover RELIANCE only. Corporate-action completeness, transaction costs, instrument identity/universe coverage and session/bar coverage remain separate BLOCKED gates.

The 2024-01-20 RELIANCE bar needs review: the session is verified, but the circular does not verify its OHLCV and this audit did not retrieve the day's bhavcopy. The normalized row also lacks ISIN/series identity.

See `audit.json` for hashes and counts, `data/reference/milestone_2o/session_calendar_exceptions_v1.json` for the registry, and `data/reference/milestone_2o/calendar_effective_v4.csv` for the derived calendar.
