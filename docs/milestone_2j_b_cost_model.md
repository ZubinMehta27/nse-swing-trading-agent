# Milestone 2J-B: delivery cost model

This is an offline Decimal tariff resolver for Zerodha resident individual standard delivery-equity research on NSE and BSE. It has no broker connection, authentication, or order submission. The profile is deliberately `partial`; it is useful for recording rules and refusing unsupported quotes, not for producing estimates or enabling a real-data evaluation.

## Profile and provenance

- Profile: [`zerodha_resident_individual_delivery_v2_partial.json`](../config/cost_profiles/zerodha_resident_individual_delivery_v2_partial.json)
- Evidence registry: [`provenance_manifest.json`](../data/reference/cost_profiles/milestone_2j_b/provenance_manifest.json)
- Machine-readable audit: [`coverage.json`](../reports/milestone_2j_b/coverage.json)
- Human-readable readiness: [`readiness.md`](../reports/milestone_2j_b/readiness.md)

Rebuild the immutable artifacts with:

```powershell
python scripts/build_milestone_2j_b_cost_profile.py
python scripts/build_milestone_2j_b_cost_audit.py
```

Both builders refuse to overwrite different existing output. Archived source bytes are fingerprinted when the provenance manifest is built. Sources observed without archived bytes have no hash and cannot back a verified rule. Original Milestone 2J evidence remains untouched.

## Modelled components and present coverage

The profile records brokerage, STT, exchange transaction charges, SEBI turnover fees, NSE IPFT, buy-side stamp duty, service GST, Zerodha DP, CDSL DP, and GST on DP charges. Required components are scoped by exchange and side; delivery account and DP holder category are explicit inputs. BSE’s historical scrip group, exclusivity, and monthly turnover dependencies are not represented by a flat rate.

NSE circular rates are present for 2024-10-01 through 2026-02-28 and 2026-03-01 through 2026-10-23. The later interval includes the stated IPFT component. Their fractional charge rounding is unverified, so a quote is refused. The profile does not extrapolate beyond these dates. SEBI turnover rates are recorded in dated intervals from 2018 through the consolidated source edition, but client billing rounding is unresolved. DP and tax components have partial or absent dates. Thus no period presently has complete usable total-cost coverage.

The CDSL male/female holder debit amounts are represented separately and require the holder category. The fixed CDSL amounts use exact arithmetic as stated fixed tariff amounts; that does not establish rounding policy for any rate-based fee. DP grouping is per symbol per date, with GST represented as its own component.

Account-level AMC and optional account charges are not allocated to trades. Doing so requires an explicit account-fee allocation policy and evidence of applicable charges.

## Fail-closed behavior

The resolver only returns a total when each required component and side resolves to one supported, date-effective rule and its rounding convention is known. Unsupported dates, gaps, unverified source/rule status, exchange/account/holder mismatch, and unverified rounding raise `CostCoverageError`. Partial totals are not exposed.

All non-synthetic backtests require both an explicit versioned `CostProfile` and complete verified corporate-action coverage. The versioned profile also requires explicit exchange and account category; DP-holder category is needed for a DP charge quote. The CLI flags are `--cost-profile`, `--cost-exchange`, `--account-category resident_individual`, and `--dp-holder-category male_primary|female_primary`, alongside `--cost-inclusive`. The supplied partial profile necessarily fails its coverage gate; no real-data backtest was run.

## Evidence limitations

- Zerodha current charges/support pages do not establish all historical effective dates or rate-rounding behavior. The displayed ₹0.01 delivery contract-note minimum also needs reconciliation with zero delivery brokerage.
- STT rate content was observed on the official Income Tax section page, but direct archival retrieval returned HTTP 403; no source bytes or hash are claimed here.
- The India Code Stamp Act Schedule I search extract displays the delivery rate and the 2019 amendment effective 2020-07-01. A direct official PDF retrieval attempt timed out after 30 seconds on 2026-10-23; no source bytes/hash or usable dated rule is claimed.
- NSE source circulars are archived, but do not establish the implementation’s billed rounding basis.
- BSE tariff depends on historical scrip group and monthly/month-end turnover rules, beyond the current broad rate shown in the Zerodha snapshot.
- SEBI consolidated schedule supports rate dates, but exact customer billing bases/rounding need broker tariff/contract-note evidence.
- CDSL manual evidence is edition-dated 2026-03-31; Zerodha DP component validity across historical periods is not established.
- GST historical applicability, component taxable bases, and rounding by charge aggregation need dated tax and contract-note evidence.
- This tariff audit does not resolve historical data gaps, corporate-action coverage, adjustment, or other readiness criteria.

No cost profile or successful download establishes profitability. A backtest does not guarantee future results.
