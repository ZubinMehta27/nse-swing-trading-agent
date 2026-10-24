# Milestone 2L — RELIANCE corporate-action evidence audit

**Readiness: BLOCKED.** No strategy backtest or profitability evaluation was run.

## Scope and reconciliation

This audit covers the 25 rows in the immutable TejHQ response for RELIANCE/INE002A01018. It groups four matching NSE/BSE representation pairs into one economic event each, leaving 21 economic events. A symbol-bound NSE EQ action API response was also retrieved and fingerprinted; it returned 20 rows and omitted one older provider event. That omission is not treated as proof the event did not occur.

Event-term evidence: 4 fully verified, 11 partially corroborated, 6 unresolved. These counts measure event-term evidence only; they do not mean accounting is supported.

## Findings

- **2025 dividend date resolved:** issuer filings and the symbol-bound NSE response support record/ex-date 2025-08-14. The earlier 2025-08-13 value came from an unfiltered NSE page and was not a RELIANCE-specific conflict. The ₹5.50 amount is confirmed by the AGM outcome. Payment is reported only as a window; the exact date remains unknown.
- **2026 dividend:** ₹6 and the 2026-06-05 record/ex-date are corroborated by issuer and NSE sources. The issuer specifies payment within seven days after the June 19 AGM, but the exact payment date remains unknown.
- **2024 bonus:** the issuer filing confirms 1:1 and record date 2024-10-28; the NSE allotment notice confirms allotment on 2024-10-29. Existing accounting tests cover quantity, aggregate basis, stop/target rebasing and value continuity.
- **2023 JFSL demerger:** the issuer annual report confirms appointed date 2023-03-31, effective date 2023-07-01, record date 2023-07-20 and one JFSL share per eligible RIL share. Portfolio accounting for the child security and basis allocation remains unsupported.
- **2020 rights:** NSE terms and issuer annual-report call details establish the 1:15 entitlement, ₹1,257 subscription price and staged payments. Rights election, cash-call and resulting-share accounting remain unsupported.
- **Dividends overall:** every one of the 17 economic dividend events still lacks a verified exact payment date. NSE action data omits record dates on older events; the 2010 provider event has no matching row in the retained NSE API response. Those facts remain unresolved rather than inferred.

## Action evidence by event

See `corporate_action_audit.json` for all 21 events, source row IDs, exchange representations, verified fields, unresolved fields, local source paths and hashes, accounting status and event-specific notes.

## Remaining blockers and acceptance criteria

- Reconcile the 2010 provider event and every missing NSE record date against a symbol-bound issuer/exchange filing or retain explicit unresolved status.
- For every dividend, archive a primary issuer/exchange source proving actual payment date or keep the corresponding period blocked.
- Implement and test rights cash-call/entitlement accounting and demerger security/cost-basis allocation using verified event terms, or retain the affected evaluation block.
- Establish completeness of issuer actions from issuer/exchange history over the full evaluation interval, including action types absent from the provider feed.
- Keep historical cost, session/data-integrity and point-in-time universe gates satisfied independently before any backtest readiness decision.

The source manifest records hashes for all retained bytes. Exact retrieval timestamps were not captured during the earlier fetch commands; file modification times are explicitly labeled as proxies, never as retrieval timestamps. The NSE quote-page retrieval returned a generic shell without event data and was excluded from term evidence. No prior raw provider files, candidate bars, canonical OHLCV, Milestone 2F–2K reports or readiness defaults were changed.
