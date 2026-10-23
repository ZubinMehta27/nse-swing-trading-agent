# Milestone 2J cost model and evidence

## Scope

This is a hypothetical, incomplete tariff outline for a resident individual using Zerodha for NSE cash delivery. No account holder category has been chosen. It is not a broker integration and does not submit orders. `config/cost_profiles/zerodha_resident_individual_nse_delivery_hypothetical.json` is deliberately `partial`; `coverage_errors()` must block every cost-inclusive run until each required component has a verified effective rule and charge rounding. The pre-existing backtest `CostSchedule` defaults remain zero and unverified.

The new Decimal-based cost arithmetic groups transaction-level items by fill, order, trading day/security, or settlement/security, supports explicit minimum and cap fields, and itemizes GST separately from its taxable components. It does not claim to replicate a broker contract note. The executable model is a local quote function only.

## Evidence actually inspected

The archive manifest at `data/reference/cost_profiles/source_archive/manifest.json` records response time, HTTP response metadata and SHA-256 for each downloaded response. Those fingerprints identify the exact archived bytes; they do not alone prove historical application or semantic completeness. The official NSE circular PDFs are byte-archived. Zerodha published pages are snapshots from retrieval date and do not give a complete historical rate series. Official Income Tax pages for Section 98 and Stamp Act Schedule I returned HTTP 403 to the local archiver; their pages were inspected through browser rendering, so no local source-file hash is asserted for them. DEA annual-report retrieval failed TLS validation and the browser retrieval failed; it is not used as verified evidence.

| Component | Observed rule/evidence | Effective interval in profile | Status / limitation |
|---|---|---|---|
| Brokerage | Zerodha currently publishes zero delivery brokerage for resident individual accounts | none | Partial; no historical effective dates, account eligibility to be confirmed |
| STT | Official Income Tax Act §98 presentation and Zerodha page show 0.1% each side for delivery equity | none | Partial; direct Act archive failed; historical changes, assessment base and rounding not established |
| NSE transaction charge | NSE FA64232: ₹2.97/lakh each side | 2024-10-01 to 2026-02-28 | Rate interval supported by circular; contract-note rounding remains unverified |
| NSE transaction charge | NSE FA73061: ₹306.99/crore each side from 2026-03-01 | 2026-03-01 onward | Circular-supported base charge; separate IPFT below; rounding unverified |
| NSE IPFT | ₹0.01/crore each side from FA73061 | 2026-03-01 onward only | Circular-supported interval; profile rule is not applicable because statutory rounding is unverified; no earlier interval inferred |
| SEBI turnover | Published charge information states ₹10/crore | none | Partial; date-effective history, exact base, rounding incomplete |
| GST on services | 18% on brokerage, SEBI and exchange service charges per broker guidance | none | Partial; historical effective intervals/base and statutory rounding incomplete |
| Delivery stamp duty | Current published rate 0.015% on buy side | none | Partial; local official consolidated schedule retrieval failed; effective history/base/rounding incomplete |
| DP charge | Zerodha help page: ₹13 pre-GST for male or ₹12.75 for female primary holder, per scrip/day | none | Partial; no holder category selected, effective interval and exceptional settlement treatment incomplete |
| GST on DP | 18% separately displayed against pre-GST DP amount | none | Partial; no verified historical interval or rounding policy |

Sources: [Zerodha charges](https://zerodha.com/charges), [Zerodha DP charge explanation](https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/what-do-dp-charges-mean), [Zerodha GST on SEBI guidance](https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/gst-on-sebi-charges), [NSE FA64232](https://nsearchives.nseindia.com/content/circulars/FA64232.pdf), [NSE FA73061](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf), [Income Tax Act §98](https://www.incometaxindia.gov.in/w/section-98-55), and [SEBI true-to-label circular](https://www.sebi.gov.in/legal/circulars/jul-2024/charges-levied-by-market-infrastructure-institutions-true-to-label_84506.html).

## Calculation specification and unresolved inputs

Each rate needs its legal/broker source, exchange/segment, effective-from and effective-to dates, buy/sell applicability, calculation base, aggregation unit, minimum/cap, per-line rounding mode and whether GST applies. Required components are represented separately to avoid embedding one levy inside another. GST is separately itemized and uses only declared taxable component names. DP aggregation is by security and day in the explanatory model; broker policy must verify exceptional settlements and the once-per-scrip behavior. No contract-note minimum fee is assumed.

Before a complete historical profile can exist, the reviewer must choose/confirm the resident account category and holder category; supply a dated broker tariff (including minimum brokerage, if any, and DP/exception rules); verify every historical STT, stamp, SEBI, exchange and IPFT interval; confirm charge bases and aggregation; and verify rounding/minimum rules from applicable primary documents or contract notes. The task deliberately leaves these decisions open. There is no single complete interval covering the 2018–2026 data.

For arithmetic tests only, `tests/fixtures/synthetic_cost_profile.json` uses toy rates and is opt-in. The tests verify Decimal totals and aggregation; these synthetic values are not market tariffs.
