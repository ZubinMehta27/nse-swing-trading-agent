# Milestone 2K historical readiness audit

**Decision: BLOCKED.** No strategy backtest or profitability evaluation was run.

## Scope

RELIANCE only. Provider bars span 2018-01-01 to 2026-10-22 (2166 rows), raw/unadjusted. Day-by-day calendar comparison covers 2018–2024 (2557 dates); selected 2025/2026 exchange circulars do not constitute full daily-calendar coverage.

## Calendar comparison


| Classification | Count |
|---|---:|
| confirmed_exchange_holiday | 100 |
| observed_bar_on_calendar_non_session_review | 1 |
| observed_expected_session_bar | 1723 |
| provider_bar_missing_official_candidate_available_unmerged | 4 |
| weekend_no_bar_expected | 729 |

## Recovery candidates

8 NSE RELIANCE EQ candidate bars are schema/source reconciled in a separate dataset. They remain unmerged. Four are special Muhurat sessions (2018-11-07, 2021-11-04, 2022-10-24, 2024-11-01); four are June 2026 sessions (2026-06-05, 2026-06-15, 2026-06-16, 2026-06-22). Older source timestamps are local file-mtime proxies, not verified retrieval times.

## Corporate actions

The raw provider response fingerprint matches the evidence registry (25 event rows). Provider discovery is not evidence of complete coverage. The machine-readable event-by-event findings are in `audit.json`.

Selected archived issuer/exchange documents are fingerprinted in `audit.json`. The 2025 dividend record-date sources conflict; the 2026 dividend payment date is not established. Rights and JFSL demerger terms are partially corroborated, but required accounting is unsupported. No absence from the provider feed is treated as proof no event occurred.

## Priority blockers and remediation

| Priority | Affected scope | Gap and risk | Best evidence / next action | Acceptance test |
|---:|---|---|---|---|
| 1 | RELIANCE, 2018–2026 | Eight bars are outside canonical series; silent merge could alter raw history. | Review candidate manifest and authorize separately versioned migration after event-continuity review. | Independent source hashes and canonical equality; new immutable dataset fingerprint; original bytes unchanged. |
| 2 | RELIANCE, full provider period | Action-feed completeness and terms are unresolved; unsupported rights/demerger accounting can misstate holdings/cash. | Obtain issuer filings, exchange notices, depository/event records; reconcile event universe and terms. | Every in-scope event has verified identity, dates, terms and tested accounting or blocks period. |
| 3 | NSE/BSE historical cost schedule | Missing historical tax, BSE group/turnover, brokerage, DP and rounding inputs. | Obtain dated government, exchange, SEBI, depository and broker evidence for chosen account category. | Complete verified date-effective profiles pass boundary and arithmetic tests. |
| 4 | All instruments | RELIANCE-only sample and incomplete point-in-time universe/ISIN evidence do not establish broad coverage. | Define universe and acquire sourced identity/calendar/bar data. | Coverage manifest proves each instrument/session and no unresolved expected gaps. |

## Evidence limitations

Unresolved calendar-audit dates within 2018–2024: none classified unresolved by the supplied calendar.
The calendar labels ordinary weekdays by the sourced holiday calendar and exchange-week rule; it does not independently verify every day with a bhavcopy. The eight candidate source files and selected official PDFs are listed with SHA-256 in `audit.json`. No candidate rows were merged. Cost profile and prior evidence were not edited.
