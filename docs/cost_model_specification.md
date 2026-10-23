# Cost model specification for historical validation

No complete historical cost profile is selected or verified. The backtest readiness
gate must remain closed until the following inputs are sourced for every applicable
date range. Zero values in unit tests are not evidence that actual costs were zero.

| Component | Category | Calculation basis to verify | Date and source evidence required | Outstanding inputs |
|---|---|---|---|---|
| STT | Statutory | Delivery-equity buy/sell turnover, including side-specific applicability | Effective-dated central tax provisions or authoritative exchange levy guidance | Full historical rates, effective transitions, charge rounding |
| Stamp duty | Statutory | Applicable delivery buy turnover and collection side | Effective-dated central/state rules and exchange collection guidance | Full historic rates and effective dates; rounding |
| Exchange transaction charge | Exchange | Turnover per side, exchange/segment and tariff interval | NSE tariff circulars covering every evaluated date | Historic tariff intervals, turnover basis and rounding |
| GST | Statutory | Taxable broker/exchange service components, excluding non-taxable levies | Effective-dated tax rules and fee component treatment | Tax base, rate periods, rounding and whether each fee is taxable |
| SEBI turnover fee | Statutory/regulatory | Turnover and prescribed collection unit | Effective-dated SEBI/exchange schedule | Historical rate intervals, unit conversion and rounding |
| Brokerage | Broker-specific | Broker's chosen percentage/fixed per order or executed order value | Selected broker's archived tariff, effective dates and account plan | Broker choice, rate, per-order minimum/cap and order aggregation rules |
| DP/depository sale charge | Broker/depository-specific | Delivery sell settlement, often per scrip/day/ISIN rather than per share | Selected broker/depository archived tariff with effective dates | Tariff, GST treatment, per-day/per-scrip aggregation, minimum and rounding |

Every profile must state its version, source URL/document hash, retrieval/review date,
effective-from and effective-to dates, calculation base, per-order or per-settlement
aggregation, minimums/caps, rounding mode and precision. The cost engine must then test
that each component is charged once on the correct side and that GST is applied only to
the verified taxable base. Do not add GST to statutory levies unless the source says it
applies. Do not convert a missing tariff into zero.

The existing Milestone 2H evidence records partial source inspection, but do not
establish one complete historical profile: broker and DP are unselected; historical
effective intervals, SEBI fees, minimums, charge allocation and rounding are missing.
The existing simplified `CostSchedule` does not model every item in this table and is
not sufficient to label a real historical evaluation cost-inclusive.

Synthetic accounting tests may use explicitly named toy rates to check arithmetic.
Those rates are test data only and must never be copied into a historical profile.
