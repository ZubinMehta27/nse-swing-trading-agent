# Milestone 2H Source-Verified Readiness

**Decision: BLOCKED. No real-data backtest or profitability evaluation was run.**

Generated: 2026-10-23T12:00:00+00:00

## Evidence status

- TejHQ action response: 25 rows; provider rows are discovery-only. Cross-exchange representations retained as separate source rows.
- Eight NSE official rows: 8 validated; 8 TejHQ bars absent; no provider OHLCV values were available for comparison; none merged.
- Action coverage: 21 event groups; 16 source rows fall within available bar history; none fully verified.
- Dividend gaps: 20 rows lack payment date and/or currency.
- Cost profile: incomplete; no broker/DP selected, no complete historical tariff or rounding policy.

## Blocking reasons

- TejHQ action feed is not completeness-verified; its 25 provider records are discovery evidence only.
- Dividend payment dates and currency are absent; supported cash accounting cannot be sourced from provider response.
- Rights and demerger events remain unsupported by the current position/cash accounting model.
- Eight official NSE bars are confirmed absent from TejHQ and remain unmerged.
- Historical action coverage from dataset start through latest session is not complete or independently verified.
- A broker/DP tariff and complete date-effective statutory charge schedule with bases and rounding are not verified.
- Current CostSchedule omits minimum brokerage, SEBI turnover fee, statutory rounding and broker-specific DP tariff details.
- Historical universe membership and survivorship limitations remain; no point-in-time universe is supplied.

## Eight-bar disposition

Each date has one validated NSE RELIANCE EQ row (`INE002A01018`); no TejHQ row exists. Official values remain candidates only.

| Date | NSE OHLC | Volume | Source file | SHA-256 |
|---|---|---:|---|---|
| 2018-11-07 | 1115 / 1115 / 1106.7 / 1110.7 | 1283997 | `cm07NOV2018bhav.csv.zip` | `34cb7742d962b69efaf6da9606dbd0386a0361c884bddfc63c3248a4d9c2b939` |
| 2021-11-04 | 2492.95 / 2504.9 / 2490 / 2498.85 | 787160 | `cm04NOV2021bhav.csv.zip` | `3c6b0e631b0ff18946537ba98dd78a4307a9fbc60d70c85e8e529e8acd1de1d8` |
| 2022-10-24 | 2460 / 2502.5 / 2455.3 / 2479.85 | 1555270 | `cm24OCT2022bhav.csv.zip` | `c8aa044e671cdb4dd8d2f312d3894a30a3201d8bc17287963a88c937fcb8c208` |
| 2024-11-01 | 1333.05 / 1341.95 / 1333.00 / 1338.65 | 2127335 | `BhavCopy_NSE_CM_0_0_0_20241101_F_0000.csv.zip` | `f45f1ee610a8b1f823682e0c19bb2a51286d11175eb4b0f1194318394cde9b7c` |
| 2026-06-05 | 1304.50 / 1306.00 / 1288.00 / 1291.00 | 17785223 | `BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip` | `120156b35ac42eace0520882dd2efb376265f2e26139a7d6f32521074a6db903` |
| 2026-06-15 | 1315.30 / 1325.00 / 1303.30 / 1307.00 | 18633321 | `BhavCopy_NSE_CM_0_0_0_20260615_F_0000.csv.zip` | `19be8fb43a2c5d67e5ebb00e136141e1fadded8312394186e9d6096e370572ba` |
| 2026-06-16 | 1313.40 / 1333.40 / 1306.40 / 1328.80 | 18513223 | `BhavCopy_NSE_CM_0_0_0_20260616_F_0000.csv.zip` | `2200b17310b6ecdc43ddc7fc1bbb500248b86f214919a590d42e385ff6491f2c` |
| 2026-06-22 | 1316.70 / 1344.90 / 1314.10 / 1326.50 | 12931213 | `BhavCopy_NSE_CM_0_0_0_20260622_F_0000.csv.zip` | `ea7428e0e2600e9106a6c3545698e0905c2fe164632eb017188ca4a417b905c7` |

No candidate was merged; every raw report was re-fingerprinted and parsed without editing the source file.

## Corporate-action registry

See `corporate_action_evidence_registry.json`. It preserves every provider row, row ID, exchange, raw subject, retrieval metadata, raw response hash, duplicate group and evidence pointer. Dividend payment dates/currency are absent. Rights and demerger terms remain incomplete for accounting. Selected filings are partially verified only; their local PDF retrieval timed out, so no local PDF hash is claimed.

## Cost evidence

NSE's exchange circular sets cash transaction charges at Rs 2.97 per lakh each side from 2024-10-01. NSE levy guidance lists delivery STT, stamp duty, GST on broker services and SEBI turnover fees. This does not establish the complete 2018–2026 schedule. Brokerage/minimum and DP tariff are unselected; charge bases, per-order/day/settlement allocation and rounding remain incomplete. See `cost_schedule_evidence.json`.

## Next decisions

- Select whether to pursue a specific hypothetical broker/DP tariff for delivery trades.
- Review an evidence-backed action manifest and explicitly approve a versioned policy for the eight source-verified missing bars.
- Acquire and review a complete authoritative action history and resolve unsupported event accounting before evaluation.
