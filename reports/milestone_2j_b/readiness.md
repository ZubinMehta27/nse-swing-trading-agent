# Milestone 2J-B Cost Coverage Audit

**Readiness: BLOCKED.** This is a tariff evidence audit only; no backtest or profitability evaluation was run.

Profile: `zerodha-resident-individual-delivery-2026-10-partial-v1` (`partial`), India cash delivery, NSE/BSE, Zerodha resident individual.

## Remaining cost blockers

- Brokerage current zero rate has no verified historical effective interval and contract-note minimum is unresolved.
- STT source result was observed but direct bytes were not archived; historical intervals and billing rounding are not resolved.
- NSE exchange-charge schedules are dated from 2024-10-01; fractional charge rounding is unverified, and earlier history is uncovered.
- BSE charges vary by historical scrip group/exclusivity and monthly turnover; no symbol/date lookup or complete tariff model is configured.
- SEBI turnover rate dates are sourced, but customer billing/rounding treatment is not verified.
- Stamp-duty official PDF retrieval timed out after 30 seconds; a search extract was observed, but source bytes and effective-date extraction were not validated.
- GST taxable-base coverage and historical dates/rounding remain incomplete.
- Zerodha DP base charge lacks historical effective dates; CDSL evidence is limited to the 2026-03-31 manual edition, and DP GST grouping/rounding is incomplete.
- Corporate-action, historical-bar recovery, source-completeness and other real-data readiness blockers remain independent.

## Archived and observed sources

Source hashes and archive statuses are recorded in `coverage.json` and the profile provenance manifest. Unarchived official-source observations have no fabricated hash.

## Gate behaviour

A versioned profile is required for every non-synthetic backtest. This profile is partial; dated gaps, unverified rules, missing holder parameters, or unverified rounding raise a coverage error. No partial total is returned.
