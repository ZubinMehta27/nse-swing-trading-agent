# Milestone 2J-C Historical Tariff Evidence Reconciliation

**Readiness: BLOCKED.** No real-data backtest or profitability evaluation was run.

Profile: `zerodha-resident-individual-delivery-2026-10-partial-v2` (partial; fail-closed).

## Component coverage

- **brokerage:** no historical effective interval; partially_verified.
- **stt:** rate content-supported from 2005-06-01; profile window 2018-01-01 through 2026-10-23; partially_verified.
- **stamp_duty:** delivery buyer rate content-supported from 2020-07-01; earlier state-specific schedule not modeled; partially_verified.
- **nse_transaction:** 2024-10-01 through 2026-10-23; two archived circular intervals; verified_rates_unverified_rounding.
- **bse_transaction:** no date-complete instrument-specific schedule; partially_verified; group and monthly turnover unresolved.
- **sebi_turnover:** 2018-01-01 through 2026-10-23 in documented intervals; verified_rates_unverified_client_rounding.
- **gst:** current 18% taxable bases observed; historical applicability/rounding incomplete; partially_verified.
- **zerodha_dp:** current charge observed; historical effective interval unavailable; partially_verified.
- **cdsl_dp:** 2024-10-01 through 2026-03-31 source-edition interval; verified_within_source_edition.

## Source retrieval failures

- `income_tax_stt_delivery_2005` at https://www.incometaxindia.gov.in/documents/20117/14628360/ExplanatoryCircularFinanceAct2005-Compiled-Recast_2_.pdf/96027428-3563-b168-0386-408400394790?t=1767814850389: Official PDF request returned HTTP 403; document text was available through official-site search/open results. No local hash is claimed.
- `india_stamp_act_schedule_56a` at https://www.indiacode.nic.in/bitstream/123456789/15510/5/A1899-2%20.pdf: Official PDF request timed out after 20 seconds; a separate official India Code search result exposed Schedule I text. No local hash is claimed.
- `dea_stamp_duty_implementation_2020` at https://dea.gov.in/files/annual_reports_documents/Annual_Report_2020_2021_English.pdf: Official PDF TLS connection could not be established. No local hash is claimed.

## Remaining blockers

- Brokerage effective-date history, contract-note minimums and rounding remain unsupported.
- STT delivery rate is content-corroborated at 0.1% for the covered historical window, but local primary bytes, customer billing precision and rounding are unresolved.
- Stamp duty 0.015% buyer-side is content-corroborated from 2020-07-01 only; the pre-central-regime state-specific treatment and billing rounding are unresolved.
- NSE exchange charges are evidenced only from 2024-10-01; earlier coverage and charge rounding remain unavailable.
- BSE tariff depends on date-specific scrip group/exclusivity and monthly turnover; no validated historical RELIANCE group series or full schedule is configured.
- SEBI turnover fee rates are sourced, but billing aggregation/rounding is unresolved.
- GST 18% current taxable bases are observed; full historical effective-date, billing precision and component rounding evidence is incomplete.
- Zerodha DP effective history and GST billing treatment are incomplete; CDSL evidence is bounded by the 2026-03-31 manual edition.
- Corporate-action completeness and independent historical-bar recovery remain separate readiness blockers.

Archived NSE, BSE, SEBI, Zerodha and CDSL sources retain their earlier fingerprints in the versioned provenance manifest. The 2J-B artifacts were not modified.
