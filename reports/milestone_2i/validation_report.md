# Milestone 2I — Bounded Validation Report

**Decision: validation fixture passes canonical data validation; real-data backtest remains
blocked.** No strategy backtest or profitability evaluation was run.

## Evidence status

- Six OHLCV rows are selected without transformation from the cached TejHQ response. They have not
  been independently compared with official daily bhavcopy files; the provider response has no
  ISIN field.
- 2024-10-02 is explicitly marked as the NSE cash-market holiday in the retained annual
  holiday-master response. The selected bars bracket that date and resume on 2024-10-03.
- 2024-10-10 is an expected session in the excerpt but is absent from this intentionally bounded
  sample. Audit classifies it as unresolved; it does not impute a bar. No automatic fills are
  performed.
- Synthetic accounting unit tests are not historical corporate-action evidence. The six-row
  fixture contains no asserted action.

## Validation and accounting

The canonical loader validates the fixture’s required columns, ISO session dates, Decimal OHLC
values, OHLC invariants, integer nonnegative volume, duplicates and deterministic date ordering.
The reusable gap audit records holiday versus absent expected session separately.

Split and bonus quantity rebasing, per-share and aggregate cost basis, protective level
adjustment, dividend receivables/payment, fractional-share blocking, unsupported event blocking,
duplicate rejection and event-date timing use explicitly synthetic tests.

## Cost specification

See `cost_model_specification.md`. The historical profile is incomplete and unverified; the
cost-inclusive readiness gate stays closed.

## Readiness

The existing Milestone 2H readiness report remains authoritative and blocked. This fixture report
does not modify or override it. Provider OHLCV lacks independently verified instrument identity,
the sample is not sufficient for the configured strategy warm-up, corporate-action coverage is
not complete, and historical statutory, exchange, broker and DP charges lack a fully verified
date-effective schedule.

See `validation_report.json` and `data/validation/milestone_2i/provenance.json` for hashes, input
references and exact classifications.
