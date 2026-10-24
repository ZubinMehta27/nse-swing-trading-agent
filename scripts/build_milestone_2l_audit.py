"""Build a write-once, source-fingerprinted RELIANCE action audit (no backtest)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from nse_swing_agent.action_coverage import audit_action_coverage
from nse_swing_agent.milestone_2l_audit import (
    classify_event_evidence,
    group_economic_events,
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _date_iso(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip() or value.strip() == "-":
        return None
    return datetime.strptime(value.strip(), "%d-%b-%Y").date().isoformat()


def _nse_action_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        symbol = row.get("symbol")
        isin = row.get("isin")
        ex_date = _date_iso(row.get("exDate"))
        if symbol != "RELIANCE" or isin != "INE002A01018" or row.get("series") != "EQ":
            raise ValueError("NSE action response contains an unexpected instrument identity")
        if ex_date is None:
            raise ValueError("NSE action row has an invalid or missing ex-date")
        key = (str(symbol), ex_date)
        if key in result:
            raise ValueError(f"duplicate NSE action row for symbol/date {key}")
        result[key] = row
    return result


def _validate_nse_event_terms(provider: dict[str, Any], nse: dict[str, Any]) -> None:
    subject = str(nse.get("subject", "")).strip().lower()
    kind = provider.get("type")
    token = {
        "dividend": "dividend",
        "bonus": "bonus",
        "demerger": "demerger",
        "rights": "rights",
    }.get(str(kind))
    if token is None or token not in subject:
        raise ValueError(f"NSE subject does not corroborate provider event type: {subject!r}")
    if kind == "dividend":
        match = re.search(r"rs\.?\s*([0-9]+(?:\.[0-9]+)?)", subject)
        if match is None or Decimal(match.group(1)) != Decimal(str(provider.get("cash_amount"))):
            raise ValueError(f"NSE dividend amount conflicts with provider event: {subject!r}")
    if kind == "bonus":
        ratio = re.search(r"bonus\s+([0-9]+):([0-9]+)", subject)
        if ratio is None or ratio.groups() != (
            str(provider.get("ratio_num")),
            str(provider.get("ratio_den")),
        ):
            raise ValueError(f"NSE bonus ratio conflicts with provider event: {subject!r}")
    if kind == "rights":
        ratio = re.search(r"rights\s+([0-9]+):([0-9]+)", subject)
        if ratio is None or ratio.groups() != (
            str(provider.get("ratio_num")),
            str(provider.get("ratio_den")),
        ):
            raise ValueError(f"NSE rights ratio conflicts with provider event: {subject!r}")
    nse_record = _date_iso(nse.get("recDate"))
    provider_record = provider.get("record_date")
    if nse_record and provider_record and nse_record != provider_record:
        raise ValueError(
            f"NSE record date {nse_record} conflicts with provider date {provider_record}"
        )


def _source_record(
    root: Path,
    source_id: str,
    relative_path: str,
    url: str,
    publication_date: str | None,
    relevance: str,
    *,
    exact_retrieval_time: str | None = None,
) -> dict[str, Any]:
    path = root / relative_path
    return {
        "source_id": source_id,
        "url": url,
        "publication_date": publication_date,
        "retrieved_at_utc": exact_retrieval_time,
        "retrieval_date": "2026-10-24" if exact_retrieval_time is None else None,
        "retrieval_time_note": (
            "Exact retrieval timestamp was not captured; file mtime is recorded separately "
            "and is not represented as retrieval time."
            if exact_retrieval_time is None
            else None
        ),
        "local_path": relative_path,
        "local_sha256": file_sha256(path),
        "bytes": path.stat().st_size,
        "local_file_mtime_utc_not_retrieval_time": datetime.fromtimestamp(
            path.stat().st_mtime, UTC
        ).isoformat(),
        "retrieval_outcome": "source_bytes_retrieved_and_fingerprinted",
        "relevance": relevance,
    }


def build(root: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)

    registry_path = root / "reports/milestone_2h/corporate_action_evidence_registry.json"
    raw_path = root / "data/raw/nse/tejhq_actions_RELIANCE_20261023T103451Z_4b305e0765.json"
    nse_path = (
        root / "data/reference/milestone_2l/source_archive/nse_reliance_actions_api_20261024.json"
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    nse_rows = json.loads(nse_path.read_text(encoding="utf-8"))
    provider_coverage = audit_action_coverage(registry_path, raw_path)
    grouped = group_economic_events(registry["events"])
    official = _nse_action_index(nse_rows)

    source_definitions = {
        "nse_actions_api": (
            "data/reference/milestone_2l/source_archive/nse_reliance_actions_api_20261024.json",
            "https://www.nseindia.com/api/corporates-corporateActions?index=equities&symbol=RELIANCE",
            None,
            "Symbol-bound NSE EQ action listing; provides symbol, ISIN, ex-date, record date, subject; response contains 20 rows.",  # noqa: E501
        ),
        "ril_2023_record": (
            "data/reference/milestone_2l/source_archive/ril_2023_agm_record_date_filing.pdf",
            "https://www.ril.com/sites/default/files/2023-08/RIL_1.pdf",
            "2023-08-04",
            "Issuer filing fixes 2023 dividend record date at 2023-08-21 and payment within one week after AGM.",  # noqa: E501
        ),
        "ril_2023_agm_notice": (
            "data/reference/milestone_2l/source_archive/ril_2023_agm_notice.pdf",
            "https://nsearchives.nseindia.com/corporate/RELIANCE_06082023144318_NoticeIAR_SE_AGM2023_signed.pdf",
            "2023-08-06",
            "Issuer AGM notice supports dividend and historical corporate benefits; also confirms payment timing convention.",  # noqa: E501
        ),
        "ril_dividend_history": (
            "data/reference/milestone_2l/source_archive/ril_dividend_history_since_1990.pdf",
            "https://www.ril.com/sites/default/files/2023-08/RIL-dividend-history-since-1990_0.pdf",
            "2023-08 (exact day unavailable)",
            "Issuer dividend history gives rupee amounts by financial year; does not establish individual ex/record/payment dates.",  # noqa: E501
        ),
        "ril_2025_record": (
            "data/reference/milestone_2l/source_archive/ril_2025_record_date_filing.pdf",
            "https://nsearchives.nseindia.com/corporate/kavinavora_31072025204029_SE_31072025.pdf",
            "2025-07-31",
            "Issuer filing sets 2025-08-14 dividend record date and payment within one week from AGM.",  # noqa: E501
        ),
        "ril_2025_agm": (
            "data/reference/milestone_2l/source_archive/ril_2025_agm_dividend_resolution.pdf",
            "https://nsearchives.nseindia.com/corporate/kavinavora_30082025123434_SE_Summary.pdf",
            "2025-08-30",
            "Issuer AGM summary confirms declaration of ₹5.50 per fully paid equity share.",
        ),
        "ril_2025_annual_report": (
            "data/reference/milestone_2k/source_archive/reliance_annual_report_2024_25.pdf",
            "https://nsearchives.nseindia.com/corporate/kavinavora_07082025114934_SE_NoticeIAR.pdf",
            "2025-08-07",
            "Issuer annual report supports 2025 dividend amount, record date and payment window Aug 29–Sep 04.",  # noqa: E501
        ),
        "ril_2026_record": (
            "data/reference/milestone_2l/source_archive/ril_2026_record_date_filing.pdf",
            "https://www.ril.com/sites/default/files/2026-05/SE_27052026.pdf",
            "2026-05-27",
            "Issuer filing sets 2026-06-05 dividend record date and payment within seven days after AGM.",  # noqa: E501
        ),
        "ril_2026_annual_report": (
            "data/reference/milestone_2k/source_archive/reliance_annual_report_2025_26.pdf",
            "https://nsearchives.nseindia.com/annual_reports/AR_29285_RELIANCE_2025_2026_A_11007429_28052026133947.pdf",
            "2026-05-28",
            "Issuer annual report supports ₹6 final dividend; it does not give an exact payment date.",  # noqa: E501
        ),
        "ril_2023_24_annual_report": (
            "data/reference/milestone_2k/source_archive/reliance_annual_report_2023_24.pdf",
            "https://nsearchives.nseindia.com/annual_reports/AR_24850_RELIANCE_2023_2024_07082024143222.pdf",
            "2024-08-07",
            "Issuer annual report supports 2024 dividend terms and JFSL demerger appointed/effective/record dates and 1:1 entitlement.",  # noqa: E501
        ),
        "ril_2024_bonus_filing": (
            "data/reference/milestone_2k/source_archive/reliance_2024_bonus_board_filing.pdf",
            "https://nsearchives.nseindia.com/corporate/RELIANCE_16102024200409_SE_16102024.pdf",
            "2024-10-16",
            "Issuer filing confirms 1:1 bonus and 2024-10-28 record date.",
        ),
        "nse_2024_bonus_allotment": (
            "data/reference/milestone_2k/source_archive/nse_reliance_bonus_allotment_CML64862.pdf",
            "https://nsearchives.nseindia.com/content/circulars/CML64862.pdf",
            None,
            "NSE listing notice identifies RELIANCE EQ and bonus allotment on 2024-10-29.",
        ),
        "nse_2020_rights": (
            "data/reference/milestone_2k/source_archive/nse_reliance_rights_adjustment_FAOP44356.pdf",
            "https://nsearchives.nseindia.com/content/circulars/FAOP44356.pdf",
            "2020-05-12",
            "NSE circular confirms 1:15 rights ratio, ex-date, record date and ₹1,257 issue price (₹1,247 premium plus ₹10 face value).",  # noqa: E501
        ),
        "ril_2020_rights_offer": (
            "data/reference/milestone_2k/source_archive/reliance_2020_rights_offer_letter.pdf",
            "https://nsearchives.nseindia.com/corporate/RELIANCE_07062020161501_Reg30IntimationAdvertisements07062020Ltr.pdf",
            "2020-06-07",
            "Original issuer offer-letter bytes retained; extracted terms were not relied on in this audit.",  # noqa: E501
        ),
    }
    sources = {}
    for source_id, (relative, url, published, relevance) in source_definitions.items():
        sources[source_id] = _source_record(root, source_id, relative, url, published, relevance)

    dividend_fields = {
        "symbol",
        "isin",
        "type",
        "amount",
        "currency",
        "ex_date",
        "record_date",
        "payment_date",
    }
    event_profiles: dict[str, dict[str, Any]] = {}
    for event in grouped:
        rows = [row for row in registry["events"] if row["event_group"] == event["event_group"]]
        first = rows[0]
        kind = first["type"]
        event_date = first["ex_date"]
        verified: set[str] = {"symbol", "isin", "type"}
        required = set(dividend_fields)
        critical = {"symbol", "isin", "ex_date", "record_date"}
        refs: list[str] = []
        terms: dict[str, Any] = {}
        accounting = "blocked_pending_action_specific_accounting_or_exact_terms"
        notes: list[str] = []
        nse = official.get(("RELIANCE", event_date))
        if nse is not None:
            _validate_nse_event_terms(first, nse)
            verified.update({"symbol", "isin", "series", "ex_date"})
            if _date_iso(nse.get("recDate")) is not None:
                verified.add("record_date")
            terms["nse_subject"] = nse.get("subject")
            refs.append("nse_actions_api")
        else:
            notes.append(
                "No matching row in the retained symbol-bound NSE API response; this is not evidence the action did not occur."  # noqa: E501
            )

        if kind == "dividend":
            if first.get("cash_amount") not in (None, ""):
                verified.add("amount")
                terms["amount_inr_per_share"] = str(first["cash_amount"])
            # The issuer reports all amounts in rupees; the official issuer history
            # corroborates the event amounts but not transaction dates or payment dates.
            verified.add("currency")
            refs.append("ril_dividend_history")
            if event_date == "2026-06-05":
                refs.extend(["ril_2026_record", "ril_2026_annual_report"])
                verified.update({"amount", "currency", "record_date"})
                terms["payment_window"] = (
                    "within seven days after AGM on 2026-06-19; exact date not established"
                )
            elif event_date == "2025-08-14":
                refs.extend(["ril_2025_record", "ril_2025_agm", "ril_2025_annual_report"])
                verified.update({"amount", "currency", "record_date"})
                terms["payment_window"] = (
                    "2025-08-29 through 2025-09-04; exact date not established"
                )
                notes.append(
                    "The earlier Aug 13 value came from a non-symbol-specific NSE page. Issuer filing and symbol-bound NSE API both give Aug 14; no RELIANCE correction notice was needed to resolve that misattributed value."  # noqa: E501
                )
            elif event_date == "2024-08-19":
                refs.append("ril_2023_24_annual_report")
                verified.update({"amount", "currency", "record_date"})
                terms["payment_window"] = (
                    "within one week after the 2024-08-29 AGM; exact date not established in archived evidence"  # noqa: E501
                )
            elif event_date == "2023-08-21":
                refs.extend(["ril_2023_record", "ril_2023_agm_notice"])
                verified.update({"amount", "currency", "record_date"})
                terms["payment_window"] = (
                    "within one week after the 2023-08-28 AGM; exact date not established"
                )
            elif nse is not None:
                verified.add("record_date") if _date_iso(nse.get("recDate")) else None
                notes.append(
                    "Exact dividend payment date is absent from the retained official evidence."
                )
            if nse is None and event_date <= "2015-05-08":
                notes.append(
                    "Older event lacks a matching row in the retained NSE API response; provider dates remain discovery-only."  # noqa: E501
                )
            terms["actual_payment_date"] = None
            terms["gross_dividend_accounting"] = (
                "payment-date cash credit cannot be applied without exact verified payment date"
            )
            accounting = "blocked_missing_exact_payment_date"
            required = set(dividend_fields)
        elif kind == "bonus":
            required = {"symbol", "isin", "type", "ratio", "ex_date", "record_date"}
            critical = {"symbol", "isin", "ratio", "ex_date", "record_date"}
            if event_date == "2024-10-28":
                refs.extend(["ril_2024_bonus_filing", "nse_2024_bonus_allotment"])
                verified.update(required)
                terms.update(
                    {
                        "ratio_new_per_old": "1",
                        "record_date": event_date,
                        "allotment_date": "2024-10-29",
                    }
                )
                accounting = "supported_bonus_policy; verified 1:1 event terms; overlapping period still subject to full action coverage gate"  # noqa: E501
            elif event_date == "2017-09-07":
                refs.extend(["ril_2023_agm_notice", "nse_actions_api"])
                verified.update(required)
                terms.update({"ratio_new_per_old": "1", "record_date": first.get("record_date")})
                accounting = "supported_bonus_policy; full historical completeness still unverified"
        elif kind == "demerger":
            required = {
                "symbol",
                "isin",
                "type",
                "ex_date",
                "record_date",
                "appointed_date",
                "effective_date",
                "entitlement_ratio",
                "child_security_identity",
            }
            critical = set(required)
            refs.append("ril_2023_24_annual_report")
            verified.update(required)
            terms.update(
                {
                    "appointed_date": "2023-03-31",
                    "effective_date": "2023-07-01",
                    "record_date": "2023-07-20",
                    "entitlement": "1 JFSL equity share for each eligible RIL equity share",
                    "child_security_identity": "Jio Financial Services Limited (JFSL); separate security",  # noqa: E501
                }
            )
            accounting = "unsupported_demerger_portfolio_allocation_and_security_delivery; blocks overlapping evaluation"  # noqa: E501
        elif kind == "rights":
            required = {
                "symbol",
                "isin",
                "type",
                "ex_date",
                "record_date",
                "entitlement_ratio",
                "subscription_price",
                "call_schedule",
            }
            critical = set(required)
            refs.extend(["nse_2020_rights", "ril_2020_rights_offer", "ril_2026_annual_report"])
            verified.update(required)
            terms.update(
                {
                    "entitlement_ratio": "1 new share for 15 existing shares",
                    "subscription_price_inr_per_share": "1257",
                    "payment_schedule": [
                        {"amount_inr": "314.25", "stage": "application (25%)"},
                        {"amount_inr": "314.25", "stage": "first call (25%)", "timing": "May 2021"},
                        {
                            "amount_inr": "628.50",
                            "stage": "final call (50%)",
                            "timing": "November 2021",
                        },
                    ],
                    "ex_date": "2020-05-13",
                    "record_date": "2020-05-14",
                }
            )
            accounting = "unsupported_rights_cash_calls_entitlement_election_and_new_security_accounting; blocks overlapping evaluation"  # noqa: E501

        # Verified terms are scoped to specific archived primary sources. A row from
        # the provider by itself does not satisfy the external evidence requirement.
        if kind == "dividend" and event_date in {
            "2016-03-17",
            "2017-07-13",
            "2018-06-27",
            "2019-08-02",
            "2020-07-02",
            "2021-06-11",
            "2022-08-18",
        }:
            refs.append("ril_2023_agm_notice")
            verified.update({"amount", "currency"})
        status, unresolved = classify_event_evidence(
            required_fields=required,
            verified_fields=verified.intersection(required),
            critical_fields=critical,
        )
        event_profiles[event["event_group"]] = {
            **event,
            "event_type": kind,
            "instrument": {"symbol": first.get("symbol"), "isin": first.get("isin")},
            "terms": {**event["provider_terms"], **terms},
            "evidence_status": status,
            "verified_fields": sorted(verified.intersection(required)),
            "unresolved_fields": unresolved,
            "source_ids": sorted(set(refs)),
            "accounting_status": accounting,
            "notes": notes,
            "provider_response_is_completeness_proof": False,
        }

    events = list(event_profiles.values())
    event_counts = Counter(row["evidence_status"] for row in events)
    Counter(row["accounting_status"] for row in events)
    duplicate_count = sum(row["duplicate_exchange_representation"] for row in grouped)
    missing_fields = Counter(field for event in events for field in event["unresolved_fields"])
    source_failures = [
        {
            "url": "https://www.nseindia.com/get-quote/equity/RELIANCE/reliance-industries-ltd.",
            "outcome": "HTTP retrieval succeeded but returned a generic page shell without event rows in retained bytes; excluded from term verification",  # noqa: E501
            "local_path": "data/reference/milestone_2l/source_archive/nse_reliance_quote_corporate_actions_snapshot_20261024.html",  # noqa: E501
            "sha256": file_sha256(
                root
                / "data/reference/milestone_2l/source_archive/nse_reliance_quote_corporate_actions_snapshot_20261024.html"  # noqa: E501
            ),
        }
    ]
    report = {
        "schema_version": "milestone-2l-corporate-action-audit-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "scope": {
            "instrument": "RELIANCE",
            "isin": "INE002A01018",
            "exchange_representations": ["NSE", "BSE"],
            "provider_event_period": "2010-05-10 through 2026-06-05",
            "provider_rows": len(registry["events"]),
            "economic_event_groups": len(events),
            "statement": "This audits known provider discoveries and selected official evidence; it does not establish complete corporate-action history.",  # noqa: E501
        },
        "paper_only": True,
        "backtest_run": False,
        "decision": "BLOCKED",
        "sources": sources,
        "provider_provenance": provider_coverage["sources"],
        "nse_action_response": {
            "path": nse_path.relative_to(root).as_posix(),
            "url": source_definitions["nse_actions_api"][1],
            "sha256": file_sha256(nse_path),
            "row_count": len(nse_rows),
            "retrieval_date": "2026-10-24",
            "retrieved_at_utc": None,
            "retrieval_time_note": "Exact retrieval time was not captured; file timestamp is not claimed as retrieval time.",  # noqa: E501
            "identity_validation": {"symbol": "RELIANCE", "isin": "INE002A01018", "series": "EQ"},
            "historical_coverage_limit": "Endpoint response contains 20 rows; provider registry has 21 unique event groups. The missing 2010 action is not inferred absent.",  # noqa: E501
        },
        "counts": {
            "provider_rows": len(registry["events"]),
            "economic_events": len(events),
            "duplicate_cross_exchange_representation_groups": duplicate_count,
            "fully_verified_event_terms": event_counts.get("fully_verified", 0),
            "partially_corroborated_event_terms": event_counts.get("partially_corroborated", 0),
            "unresolved_event_terms": event_counts.get("unresolved", 0),
            "dividend_exact_payment_dates_unresolved": sum(
                1 for row in events if row["event_type"] == "dividend"
            ),
            "unresolved_field_counts": dict(sorted(missing_fields.items())),
        },
        "events": events,
        "known_conflicts_and_resolution": [
            {
                "topic": "2025 dividend record date",
                "result": "resolved to 2025-08-14",
                "basis": [
                    "RIL issuer record-date filing dated 2025-07-31 specifies 2025-08-14.",
                    "RIL FY2024-25 annual report specifies 2025-08-14.",
                    "The retained symbol-bound NSE action response identifies RELIANCE/INE002A01018/EQ with ex and record date 2025-08-14.",  # noqa: E501
                    "The earlier 2025-08-13 observation came from a non-symbol-specific NSE page; it is not conflicting RELIANCE evidence. No correction notice was found or needed to establish the date from the issuer filing.",  # noqa: E501
                ],
                "remaining": "Exact payment date is not identified; issuer report gives a payment window only.",  # noqa: E501
            },
            {
                "topic": "2026 dividend payment date",
                "result": "unresolved exact date",
                "basis": "Issuer filing sets record date 2026-06-05 and payment within seven days after the 2026-06-19 AGM; the annual report confirms ₹6 per share but no exact payment date was found.",  # noqa: E501
                "consequence": "Dividend receivable cannot be converted to cash on an invented date; affected accounting evaluation remains blocked.",  # noqa: E501
            },
        ],
        "duplicate_representation_policy": "Four NSE/BSE pairs with matching identity, event group, dates and terms are one economic event each. Keep exchange source rows for provenance; count each event once in portfolio accounting.",  # noqa: E501
        "coverage_limitations": [
            "The provider response explicitly makes no completeness guarantee.",
            "The symbol-bound NSE endpoint returned 20 rows versus 21 provider economic groups; the 2010 provider action lacks matching rows in this response.",  # noqa: E501
            "The NSE response omits record dates for older events where recDate is '-'; the audit preserves those as unresolved rather than filling from provider-only values.",  # noqa: E501
            "Exact payment dates remain unresolved for all 17 dividend economic events; available issuer statements provide periods or no date.",  # noqa: E501
            "No evidence of merger, buyback or delisting in the provider response is not proof those actions did not occur.",  # noqa: E501
            "Corporate-action coverage is limited to one issuer and selected source documents; it is not a complete market-wide or point-in-time event universe.",  # noqa: E501
        ],
        "unsupported_accounting": [
            {
                "type": "rights",
                "known_event_date": "2020-05-13",
                "reason": "Subscription elections, cash calls and allocation of resulting rights shares are not implemented in the portfolio ledger.",  # noqa: E501
            },
            {
                "type": "demerger",
                "known_event_date": "2023-07-20",
                "reason": "JFSL security delivery and economic cost-basis allocation across both securities are not implemented.",  # noqa: E501
            },
            {
                "type": "merger",
                "known_event_date": None,
                "reason": "Unsupported and absent from provider response; absence is not evidence of no event.",  # noqa: E501
            },
            {
                "type": "buyback",
                "known_event_date": None,
                "reason": "Unsupported and absent from provider response; absence is not evidence of no event.",  # noqa: E501
            },
            {
                "type": "delisting",
                "known_event_date": None,
                "reason": "Unsupported and absent from provider response; absence is not evidence of no event.",  # noqa: E501
            },
        ],
        "accounting_review": {
            "bonus_2024": "Verified 1:1 ratio and record date 2024-10-28; NSE allotment notice states allotment on 2024-10-29. Existing share, cost-basis and stop/target transformations are regression-tested; exact event is not inserted into canonical action manifest.",  # noqa: E501
            "dividends": "Model requires INR amount, eligibility dates and exact payment date. Verified amount/currency/record dates do not establish actual payment date; do not credit cash on a guessed day.",  # noqa: E501
            "rights_and_demerger": "Known event terms are preserved for audit, but unsupported ledger treatment blocks any overlapping evaluation.",  # noqa: E501
            "future_information": "Audit evidence is used only for readiness and event-date application; it does not authorize retroactive signals or a real-data performance run.",  # noqa: E501
        },
        "acceptance_criteria": [
            "Reconcile the 2010 provider event and every missing NSE record date against a symbol-bound issuer/exchange filing or retain explicit unresolved status.",  # noqa: E501
            "For every dividend, archive a primary issuer/exchange source proving actual payment date or keep the corresponding period blocked.",  # noqa: E501
            "Implement and test rights cash-call/entitlement accounting and demerger security/cost-basis allocation using verified event terms, or retain the affected evaluation block.",  # noqa: E501
            "Establish completeness of issuer actions from issuer/exchange history over the full evaluation interval, including action types absent from the provider feed.",  # noqa: E501
            "Keep historical cost, session/data-integrity and point-in-time universe gates satisfied independently before any backtest readiness decision.",  # noqa: E501
        ],
        "source_retrieval_notes": source_failures,
        "overall_readiness": "BLOCKED",
    }

    for filename in ("corporate_action_audit.json", "source_manifest.json", "readiness.md"):
        target = output / filename
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing artefact: {target}")
    (output / "corporate_action_audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": "milestone-2l-source-manifest-v1",
        "generated_at_utc": report["generated_at_utc"],
        "provider_raw": provider_coverage["sources"]["provider_raw_response"],
        "issuer_exchange_documents": list(sources.values()),
        "nse_api_response": report["nse_action_response"],
        "retrieval_failures": [],
        "non_evidence_retrievals": source_failures,
    }
    (output / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    counts = report["counts"]
    lines = [
        "# Milestone 2L — RELIANCE corporate-action evidence audit",
        "",
        "**Readiness: BLOCKED.** No strategy backtest or profitability evaluation was run.",
        "",
        "## Scope and reconciliation",
        "",
        "This audit covers the 25 rows in the immutable TejHQ response for RELIANCE/INE002A01018. It groups four matching NSE/BSE representation pairs into one economic event each, leaving 21 economic events. A symbol-bound NSE EQ action API response was also retrieved and fingerprinted; it returned 20 rows and omitted one older provider event. That omission is not treated as proof the event did not occur.",  # noqa: E501
        "",
        f"Event-term evidence: {counts['fully_verified_event_terms']} fully verified, {counts['partially_corroborated_event_terms']} partially corroborated, {counts['unresolved_event_terms']} unresolved. These counts measure event-term evidence only; they do not mean accounting is supported.",  # noqa: E501
        "",
        "## Findings",
        "",
        "- **2025 dividend date resolved:** issuer filings and the symbol-bound NSE response support record/ex-date 2025-08-14. The earlier 2025-08-13 value came from an unfiltered NSE page and was not a RELIANCE-specific conflict. The ₹5.50 amount is confirmed by the AGM outcome. Payment is reported only as a window; the exact date remains unknown.",  # noqa: E501
        "- **2026 dividend:** ₹6 and the 2026-06-05 record/ex-date are corroborated by issuer and NSE sources. The issuer specifies payment within seven days after the June 19 AGM, but the exact payment date remains unknown.",  # noqa: E501
        "- **2024 bonus:** the issuer filing confirms 1:1 and record date 2024-10-28; the NSE allotment notice confirms allotment on 2024-10-29. Existing accounting tests cover quantity, aggregate basis, stop/target rebasing and value continuity.",  # noqa: E501
        "- **2023 JFSL demerger:** the issuer annual report confirms appointed date 2023-03-31, effective date 2023-07-01, record date 2023-07-20 and one JFSL share per eligible RIL share. Portfolio accounting for the child security and basis allocation remains unsupported.",  # noqa: E501
        "- **2020 rights:** NSE terms and issuer annual-report call details establish the 1:15 entitlement, ₹1,257 subscription price and staged payments. Rights election, cash-call and resulting-share accounting remain unsupported.",  # noqa: E501
        "- **Dividends overall:** every one of the 17 economic dividend events still lacks a verified exact payment date. NSE action data omits record dates on older events; the 2010 provider event has no matching row in the retained NSE API response. Those facts remain unresolved rather than inferred.",  # noqa: E501
        "",
        "## Action evidence by event",
        "",
        "See `corporate_action_audit.json` for all 21 events, source row IDs, exchange representations, verified fields, unresolved fields, local source paths and hashes, accounting status and event-specific notes.",  # noqa: E501
        "",
        "## Remaining blockers and acceptance criteria",
        "",
    ]
    lines.extend(f"- {item}" for item in report["acceptance_criteria"])
    lines.extend(
        [
            "",
            "The source manifest records hashes for all retained bytes. Exact retrieval timestamps were not captured during the earlier fetch commands; file modification times are explicitly labeled as proxies, never as retrieval timestamps. The NSE quote-page retrieval returned a generic shell without event data and was excluded from term evidence. No prior raw provider files, candidate bars, canonical OHLCV, Milestone 2F–2K reports or readiness defaults were changed.",  # noqa: E501
            "",
        ]
    )
    (output / "readiness.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("reports/milestone_2l_v1"))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    report = build(root, output)
    print(
        json.dumps(
            {"decision": report["decision"], "counts": report["counts"], "output": str(output)},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
