# Milestone 2M — RELIANCE corporate-action accounting and coverage audit

**Decision: BLOCKED. No strategy backtest or profitability evaluation was run.**

## Evidence update

The 2010 provider dividend is reconciled to its existing event group, not counted as a new event. Official RIL/BSE-hosted annual-report copies support a Board recommendation dated 2010-04-23, INR 7.00 per share and a 2010-05-11 record date. The retrieved evidence does not verify the ex-date, shareholder approval date, or payment date/window. Its absence from the 20-row NSE API response remains a source-coverage limitation.

The archived RIL annual reports document payment windows for the 2020 and 2021 dividends: 2020-07-16–2020-07-22 and 2021-06-24–2021-06-30. These are windows, not exact shareholder cash-posting dates. Earlier Milestone 2L issuer filings also document windows for 2023–2026. No exact payment date was established for the 17 provider dividend events.

## Accounting and bounded period

Existing accounting tests cover ex-date dividend receivables and payment-date cash; split/bonus quantity, basis and protective-price adjustments; and blocking fractional entitlements without cash-in-lieu terms. Rights, demerger, merger, buyback and delisting remain fail-closed. The dividend model requires an exact payment date and cannot safely use a payment window as a cash-credit date.

No bounded historical window passes every data, action-coverage, accounting, calendar and verified transaction-cost gate. Synthetic tests do not establish real-event coverage. The eight recovery candidates remain separate and were not merged.

## Remaining blockers

- Obtain symbol-bound issuer/exchange evidence for missing ex/record dates and the 2010 ex-date.
- Obtain exact payment dates or implement and test a receivable/window policy that never advances cash before the documented bound.
- Establish action-history completeness from primary issuer/exchange records independently of the provider feed.
- Implement verified rights and demerger consideration/basis accounting or continue blocking affected windows.
- Resolve historical bars, instrument identity, calendar, and date-effective transaction-cost gates before proposing a bounded window.

Source byte hashes, publication-date precision and retrieval timestamp limitations are recorded in `source_manifest.json`. Milestone 2L and earlier evidence are unchanged.
