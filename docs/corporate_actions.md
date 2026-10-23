# Corporate action manifest and accounting policy

The backtester consumes raw, unadjusted OHLCV only. Provider adjustment factors are not event
terms and are never used to derive share ratios, dividend amounts, or consideration. The raw
TejHQ action response is preserved under `data/raw/nse/`; it is not itself a reviewed action
manifest and its advertised feed has no completeness guarantee.

## Canonical reviewed JSON

```json
{
  "schema_version": "1.0",
  "source": "reviewed source citation",
  "source_fingerprint": "64 lowercase/uppercase hex SHA-256 characters",
  "retrieved_at": "2026-10-23T10:34:51+00:00",
  "coverage": {"from": "2024-01-01", "to": "2026-10-22", "complete": true, "verified": true},
  "events": [{
    "symbol": "EXAMPLE", "isin": "INE...", "type": "dividend",
    "ex_date": "2025-01-02", "record_date": "2025-01-03",
    "payment_date": "2025-02-01", "cash_per_share": "2.50",
    "currency": "INR", "verification_status": "verified"
  }]
}
```

Each event inherits source, fingerprint, and retrieval timestamp from this manifest. Dividend
events require explicit INR/share amount and payment date. Split and bonus events require
`ratio_new_per_old`, the post-event share count divided by pre-event share count (a 1:1 bonus is
`2`). Do not translate a provider ratio or adjustment factor unless its exact semantics have
been verified independently. Duplicate/conflicting symbol, ex-date, type events are rejected.

## Implemented accounting

At the ex-date, before processing that session's OHLC, verified split/bonus events multiply held
and pending whole-share quantities and divide unit cost basis, entry reference, stop and target by
the same factor. Total cost basis is invariant. Fractional share entitlements block the run; no
fractional value is discarded or fabricated. Raw indicator history resets on split/bonus dates
and warms up again on subsequent observed raw bars; no future action is applied before its
effective date.

Dividend eligibility uses holdings carried into the ex-date from the prior close. A gross
receivable is recorded on ex-date, stop and target levels are reduced by the per-share dividend
to avoid treating the modeled ex-dividend drop as a trading stop/target move, and cash is credited
only on the payment date. Receivables count as an asset in marked equity; gross dividend income
is separate from realized trade P&L. This simplified policy does not model tax withholding or
issuer/exchange price-reference deviations.

Rights, demergers, mergers, buybacks, and delistings block any overlapping evaluation. They need
verified security/cash consideration, elections, entitlement handling, and/or terminal valuation
not present in this model. `agm` and `other` provider categories also cannot be mapped without
event terms. Do not use adjusted-close features with raw execution prices. Raw-price indicators
reset only for split/bonus; dividend discontinuities remain a limitation requiring evaluation
review and may affect features even though held-position stop levels and cash are accounted for.

Non-synthetic backtests must supply `--actions-manifest` whose explicitly reviewed coverage spans
the input history. This is a user assertion and does not upgrade an incomplete provider feed to
verified evidence. Raw source responses are immutable and candidate replacement bars from the
Milestone 2F recovery manifest are not merged by this feature.
