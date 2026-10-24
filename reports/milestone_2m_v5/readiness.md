# Milestone 2M — Dividend payment-timing readiness addendum

**Readiness: BLOCKED. No real-data backtest was run.**

- Exact payment dates verified: 0
- Bounded documented payment windows: 3
- Unknown actionable timing: 14
- Descriptive but unbounded window notes within UNKNOWN: 3

Exact-date dividends retain ex-date receivable recognition and payment-date cash credit. For a documented window or unknown timing, a held entitlement raises a structured blocking error containing the amount, timing bounds or unknown state, evidence reference and source fingerprint. No portfolio path is returned, so the engine cannot credit cash at either window boundary or invent an exact posting date.

Window and unknown timing are representable in the action model, but they are not supported for portfolio-path accounting. Existing action-coverage, unsupported-event, data/session and historical-cost gates remain in force.

No bounded window is eligible. This addendum does not alter the Milestone 2M base audit or global readiness defaults.

Input audit SHA-256: `73add29b9b7b32ed636a051206739d6377e5f34abb8eda92a6637990ee2a4524`.
