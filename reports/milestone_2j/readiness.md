# Milestone 2J Readiness

**Decision: BLOCKED.** No real-data backtest or profitability evaluation was run.

## Bounded recovery candidate

- Candidate validation: **complete**, 8 NSE bhavcopy bars.
- Dates: 2018-11-07, 2021-11-04, 2022-10-24, 2024-11-01, 2026-06-05, 2026-06-15, 2026-06-16, 2026-06-22.
- Candidate SHA-256: `15736362fb99df90dbb7e77004dbf8fe74d58dbe25358319174be166ba076aa8`.
- Candidate data: `candidate_missing_bars.csv`. It is standalone and was not merged into TejHQ or any prior dataset.
- Source rows matched the source hash and Milestone 2H OHLCV, session date, RELIANCE symbol, ISIN INE002A01018 and NSE EQ series. The four June 2026 reports retain recorded retrieval times; the older four have local-file-mtime proxies, not verified retrieval times.
- The source rows and TejHQ history are both treated as raw/unadjusted. This does not clear action-continuity gaps. The candidate builder makes no adjustment and explicitly prohibits merge pending review.

## Existing-history identity, actions and costs

- Full-history symbol/ISIN identity remains incomplete; only candidate rows have ISIN evidence.
- Corporate-action registry has 25 provider rows but is not completeness-verified; 20 dividend records lack payment-date or currency terms. Unsupported event types: rights, demerger, merger, buyback, delisting.
- Hypothetical cost profile `zerodha-resident-individual-nse-delivery-observed-2026-10-23-v1` is `partial`. It leaves **2166 of 2166** provider sessions and **8 of 8** candidate sessions uncovered. No tariff was inferred to complete the profile.

## Blockers

- Full-history TejHQ instrument identity has no ISIN; eight source-verified candidate rows do not establish the identity of all provider rows.
- The provider action feed is discovery-only, not completeness-verified; dividend payment dates/currency remain absent in 20 records.
- Rights, demerger, merger, buyback and delisting accounting remain unsupported or unverified.
- Eight NSE bars are available only in a separate candidate dataset and are not merged.
- No complete date-effective, verified cost profile covers all historical sessions; the hypothetical profile fails closed.
- The existing Milestone 2H historical action-coverage and point-in-time-universe blockers remain.

## Decision

The eight-row candidate set validates only those source records; it does not establish history completeness, corporate-action coverage, date-effective transaction costs, or real-data evaluation readiness. Keep raw inputs and previous evidence immutable. The next necessary human input is confirmation of the account/holder category and selection of the intended broker tariff evidence, followed by source-backed review of historical statutory fee intervals and unresolved corporate-action coverage. No backtest should be started until the readiness gate is independently rebuilt and passes.
