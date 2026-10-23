# Milestone 2J-C: historical tariff evidence

This is an offline evidence reconciliation for a Zerodha resident-individual cash-equity delivery account. It does not establish a complete fee schedule. The v3 profile is deliberately partial and the quote resolver rejects it. It is not suitable for a cost-inclusive evaluation.

## Sources and evidence status

Archived bytes from Milestone 2J-B remain referenced with their original SHA-256 values in `data/reference/cost_profiles/milestone_2j_c/provenance_manifest.json`. Additional official-page content was inspected for STT and stamp duty, but direct archival attempts failed. Those records have null hashes and are explicitly marked `content_observed_archive_failed`.

- Zerodha's [charges schedule](https://zerodha.com/charges) and [DP charge explanation](https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/what-do-dp-charges-mean) describe current charges and DP aggregation; they do not establish all historical effective dates.
- NSE circular [FA64232](https://nsearchives.nseindia.com/content/circulars/FA64232.pdf) supports the 2024-10-01 transaction-charge interval. NSE circular [FA73061](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf) supports the 2026-03-01 transaction charge and separately stated IPFT charge. The model keeps IPFT as a separate line to avoid double counting.
- BSE's archived equity-segment master circular is retained in the 2J-B source archive. Its group/exclusivity and monthly-turnover dimensions mean the displayed headline rate is not used as a historical daily rate. No date-specific historical RELIANCE scrip-group series was validated.
- SEBI turnover-fee intervals and CDSL DP terms remain linked to archived evidence from 2J-B. Source edition end dates are preserved; they are not extrapolated.
- Official Income Tax Department content for the Finance Act 2005 explanatory circular states 0.1% delivery STT from 2005-06-01; current Section 98 content corroborates the present rate. The source PDF request returned HTTP 403, so this is partial corroboration only and carries no local hash. [Circular PDF](https://www.incometaxindia.gov.in/documents/20117/14628360/ExplanatoryCircularFinanceAct2005-Compiled-Recast_2_.pdf/96027428-3563-b168-0386-408400394790?t=1767814850389), [Section 98](https://www.incometaxindia.gov.in/w/section-98-55).
- Official India Code Schedule I content supports 0.015% buyer stamp duty on delivery equity, with implementation from 2020-07-01 corroborated in the Department of Economic Affairs 2020-21 report. Direct PDF retrieval timed out/TLS failed; neither has an archived hash here. This does not resolve pre-2020 state-specific stamp treatment. [India Code Act](https://www.indiacode.nic.in/bitstream/123456789/15510/5/A1899-2%20.pdf), [DEA annual report](https://dea.gov.in/files/annual_reports_documents/Annual_Report_2020_2021_English.pdf).

## Remaining missing inputs

The profile does not assert a fee calculation precision or rounding method based on example displays. It needs verified client-billing rounding, fee bases/aggregation, historic Zerodha delivery brokerage/minimum rules, historical Zerodha DP dates, GST effective coverage and grouping, BSE scrip group/exclusivity by date and monthly turnover input, and complete applicable historical schedules. Stamp duty before 2020-07-01 also needs account- and state-applicable evidence. These are not filled by assumptions.

Independent historical bar, corporate-action and data-completeness blockers remain. No real-data backtest or profitability evaluation was run. See `reports/milestone_2j_c/readiness.md`.
