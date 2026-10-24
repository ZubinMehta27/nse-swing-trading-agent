# Milestone 2O — Session calendar and data-readiness audit

**Decision: BLOCKED. No real-data backtest or profitability evaluation was run.**

The original NSE calendar and historical dataset are unchanged. A separate verified exception registry promotes 2024-01-20 from the source calendar's generic WEEKEND label to SPECIAL_SESSION in a derived effective calendar. NSE Circular MSD59999, dated 2023-12-28, explicitly calls it a special live equity session. The circular hash is `614b965d1152ed636052e983a01206117ff6af224365348fa00b7165a6baa243`.

The RELIANCE TejHQ file has 2166 observed rows. Its canonical schema has symbol but no ISIN or series. Calendar expectation and observed data are separated row by row in `date_by_date_calendar_audit.csv`; ordinary sessions derive from the weekly rule and holiday master, and missing provider bars are not labeled holidays.

All 8 existing candidate bars were re-hashed against their source records and Milestone 2K reconciliation. They remain in the standalone candidate file and were not merged.

Calendar evidence is NSE-only and ends 2024-12-31. Provider and candidate evidence cover RELIANCE only. Corporate-action completeness, transaction-cost history, instrument identity/universe coverage and full session/bar coverage remain independent BLOCKED gates.

See `audit.json` for hashes and counts, `data/reference/milestone_2o/session_calendar_exceptions_v1.json` for the exception registry, and `data/reference/milestone_2o/calendar_effective_v1.csv` for the derived calendar.
