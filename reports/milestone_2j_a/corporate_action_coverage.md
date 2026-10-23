# Corporate-action coverage audit

Decision: **BLOCKED**. Provider action rows are discovery evidence; this report does not establish complete historical coverage.

- Events: 25
- Verification statuses: `{"partially_verified": 4, "unverified": 21}`
- Event types: `{"bonus": 3, "demerger": 1, "dividend": 20, "rights": 1}`
- Duplicate representation groups: 4
- Missing terms: `{"bonus.effective_date": 3, "demerger.consideration": 1, "demerger.effective_date": 1, "dividend.currency": 20, "dividend.payment_date": 20, "dividend.record_date": 6, "rights.subscription_price": 1}`

## Blockers

- TejHQ action endpoint states historical feed completeness is not guaranteed.
- Provider discoveries are not independent evidence of complete event terms.
- Some known action types are unsupported by portfolio accounting.
- Absence of an event type from this response does not establish no such event occurred.

Raw source and registry fingerprints are recorded in the JSON report.
