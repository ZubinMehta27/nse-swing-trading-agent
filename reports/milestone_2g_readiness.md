# Milestone 2G — Corporate-action-aware accounting readiness

**Decision: BLOCKED. No real-data backtest or profitability evaluation was run.** No raw inputs or candidate recovery bars were changed.

## Evidence inspected

The unchanged TejHQ action response is `data/raw/nse/tejhq_actions_RELIANCE_20261023T103451Z_4b305e0765.json`, SHA-256 `4b305e0765bd8a1b0e32ee4074d7343c81cefd99e8231e1275a9e793952bf777`, retrieved `2026-10-23T10:34:51.675000+00:00`. It contains 25 rows from 2010-05-10 through 2026-06-05: 20 dividends, 3 bonuses, 1 demerger, and 1 rights issue. NSE and BSE duplicates are present. Fields actually observed include symbol, ISIN, ex-date, record date, event type, cash amount, ratio numerator/denominator, and raw subject. Dividend payment dates and currency are absent. The provider does not guarantee action-feed completeness. The detailed machine-readable findings are in [milestone_2g_corporate_action_audit.json](milestone_2g_corporate_action_audit.json).

Historical coverage remains imperfect: the Milestone 2F audit classified the exact 104 dates as 100 NSE holidays and four source discrepancies, with zero unresolved classifications. Four additional June 2026 dates are verified NSE/TejHQ source discrepancies in Milestone 2E. Those eight source-verified bars (four 2018–2024 special sessions and four 2026 sessions) are still absent from the TejHQ derived series and remain unmerged. They are not treated as ordinary sessions or silently filled.

## Implemented policy

- Verified dividends, splits, and bonuses can be applied to raw OHLCV runs through a separately reviewed canonical manifest.
- Splits/bonuses transform open positions and pending orders at ex-date, preserve total cost basis, adjust stop/target levels, and reset raw indicator history. Fractional entitlements block.
- Dividend entitlement uses holdings carried into ex-date from the previous close. Gross income is recorded separately; receivable increases marked equity on ex-date and cash is credited on payment date. Stops and targets shift down by the verified per-share cash amount. Indicator history resets after split, bonus, and dividend ex-dates, then warms up from subsequent raw bars.
- Rights, demergers, mergers, buybacks, and delistings block overlapping runs. Ambiguous, unverified, duplicate, incomplete, or conflicting input is rejected.
- Non-synthetic backtests require explicit action coverage over all input history. This coverage declaration is an operator assertion, not evidence that a provider feed is complete.

## Remaining blockers

1. Obtain a complete, authoritative action history with verified terms, including dividend payment dates/currency and applicable symbol/ISIN identity. Current TejHQ rows cannot be promoted to the canonical manifest as-is.
2. Resolve unsupported rights and the 2023 demerger with verified entitlement/consideration and position valuation models, or keep overlapping evaluation blocked.
3. Review a separately versioned recovery policy for the eight source-verified but unmerged bars: 2018-11-07, 2021-11-04, 2022-10-24, 2024-11-01, 2026-06-05, 2026-06-15, 2026-06-16, and 2026-06-22.
4. Supply a sourced, verified, nonzero, date-effective cost profile.

The exact next step is to prepare a source-reviewed canonical action manifest with complete coverage and event terms (starting with the actual missing dividend payment dates and unresolved rights/demerger terms), then add regression tests for any newly supported event accounting. Do not run real-data performance evaluation before all readiness blockers are reviewed and closed.
