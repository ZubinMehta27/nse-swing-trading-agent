"""Fail-closed source evidence reports for Milestone 2H.

This module summarizes provenance already stored in the repository. It never changes
canonical bars, action data, or raw source files and is not a backtest entry point.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .corporate_actions import sha256_file
from .gap_audit import _source_rows
from .historical_data import load_historical_file

TARGET_DATES = (
    "2018-11-07",
    "2021-11-04",
    "2022-10-24",
    "2024-11-01",
    "2026-06-05",
    "2026-06-15",
    "2026-06-16",
    "2026-06-22",
)
MANDATORY_COSTS = (
    "brokerage",
    "stt",
    "exchange_transaction",
    "gst",
    "stamp_duty",
    "delivery_sale_dp",
    "sebi_turnover",
)


def validate_cost_evidence(components: list[dict[str, Any]]) -> list[str]:
    """Validate sourced date intervals without treating unknowns as zero."""
    errors: list[str] = []
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in components:
        name = item.get("component")
        if name not in MANDATORY_COSTS:
            errors.append(f"unsupported cost component: {name}")
            continue
        by_name[name].append(item)
        if item.get("status") != "verified":
            errors.append(f"{name}: source verification is incomplete")
        if not item.get("effective_from") or not item.get("effective_to"):
            errors.append(f"{name}: effective-date coverage is incomplete")
        if item.get("value") in (None, ""):
            errors.append(f"{name}: charge value is unknown")
        if item.get("status") == "verified":
            if not item.get("source_url"):
                errors.append(f"{name}: verified interval requires a source URL")
        start, end = item.get("effective_from"), item.get("effective_to")
        try:
            if start:
                date.fromisoformat(start)
            if end:
                date.fromisoformat(end)
            if start and end and date.fromisoformat(start) > date.fromisoformat(end):
                errors.append(f"{name}: effective_from is after effective_to")
        except (TypeError, ValueError):
            errors.append(f"{name}: invalid effective date")
    for name in MANDATORY_COSTS:
        records = sorted(by_name.get(name, []), key=lambda r: r.get("effective_from") or "")
        if not records:
            errors.append(f"{name}: no evidence record")
        for prior, current in zip(records, records[1:], strict=False):
            prior_end = prior.get("effective_to")
            current_start = current.get("effective_from")
            if (
                prior_end
                and current_start
                and date.fromisoformat(current_start) <= date.fromisoformat(prior_end)
            ):
                errors.append(f"{name}: overlapping effective intervals")
    if any(item.get("unsupported_assumptions") for item in components):
        errors.append("cost schedule contains unsupported or unselected assumptions")
    return errors


def compare_bars(provider: dict[str, Any] | None, official: dict[str, Any]) -> dict[str, Any]:
    """Compare canonical OHLCV and identity; absent provider observations remain absent."""
    if provider is None:
        return {"provider_present": False, "comparison": "provider_bar_missing"}
    symbol_ok = provider.get("symbol") == official.get("symbol")
    identity_ok: bool | None = (
        symbol_ok and provider.get("isin") == official.get("isin") if provider.get("isin") else None
    )
    names = ("open", "high", "low", "close", "volume")
    equal = all(str(provider.get(field)) == str(official.get(field)) for field in names)
    if not symbol_ok or identity_ok is False or not equal:
        comparison = "mismatch"
    elif identity_ok is None:
        comparison = "identity_unverified_isin_unavailable"
    else:
        comparison = "match"
    return {
        "provider_present": True,
        "identity_match": identity_ok,
        "ohlcv_match": equal,
        "comparison": comparison,
    }


def validate_action_evidence(events: list[dict[str, Any]]) -> list[str]:
    """Return completeness blockers for action records in an evidence registry."""
    errors: list[str] = []
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    seen_exchange_rows: set[tuple[str, str, str, str, str]] = set()
    for event in events:
        key = (event.get("symbol", ""), event.get("ex_date", ""), event.get("type", ""))
        exchange_key = (
            event.get("symbol", ""),
            event.get("isin", ""),
            event.get("ex_date", ""),
            event.get("type", ""),
            event.get("exchange", ""),
        )
        if exchange_key in seen_exchange_rows:
            errors.append(f"duplicate same-exchange source row: {exchange_key}")
        seen_exchange_rows.add(exchange_key)
        prior = seen.get(key)
        signature = (event.get("cash_amount"), event.get("ratio_num"), event.get("ratio_den"))
        if prior is not None:
            prior_sig = (prior.get("cash_amount"), prior.get("ratio_num"), prior.get("ratio_den"))
            if prior_sig != signature:
                errors.append(f"conflicting action evidence: {key}")
        else:
            seen[key] = event
        if event.get("verification_status") != "verified":
            errors.append(f"action not fully verified: {key}")
        kind = event.get("type")
        if kind == "dividend" and (not event.get("payment_date") or not event.get("currency")):
            errors.append(f"dividend lacks payment date or currency: {key}")
        if kind == "rights" and not all(
            event.get(field) for field in ("subscription_price", "entitlement_ratio", "record_date")
        ):
            errors.append(f"rights terms incomplete: {key}")
        if kind == "demerger" and not all(
            event.get(field) for field in ("consideration", "record_date", "effective_date")
        ):
            errors.append(f"demerger terms incomplete: {key}")
    return errors


def build_milestone_2h(
    root: Path,
    generated_at: datetime | None = None,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Build evidence registry, eight-bar comparison, cost schedule and readiness."""
    generated_at = generated_at or datetime.now(UTC)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    reports = root / "reports"
    out = output_dir or reports / "milestone_2h"
    out.mkdir(parents=True, exist_ok=True)

    action_paths = sorted((root / "data/raw/nse").glob("tejhq_actions_RELIANCE_*.json"))
    if len(action_paths) != 1:
        raise ValueError(
            f"expected exactly one action response for RELIANCE; found {len(action_paths)}"
        )
    action_path = action_paths[0]
    action_raw_hash = sha256_file(action_path)
    action_payload = json.loads(action_path.read_text(encoding="utf-8"))
    action_rows = action_payload.get("data", action_payload.get("actions", []))
    if not isinstance(action_rows, list):
        raise ValueError("TejHQ action response has no recognized data/actions array")
    action_manifest = json.loads((reports / "milestone_2g_corporate_action_audit.json").read_text())
    action_meta = action_manifest["raw_source"]
    if action_meta["sha256"] != action_raw_hash:
        raise ValueError("action response fingerprint differs from Milestone 2G report")
    grouped: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for index, row in enumerate(action_rows, 1):
        key = tuple(
            row.get(key)
            for key in (
                "symbol",
                "isin",
                "ex_date",
                "record_date",
                "type",
                "cash_amount",
                "ratio_num",
                "ratio_den",
            )
        )
        grouped[key].append(index)
    official_sources = {
        "2020-05-13": {
            "url": "https://nsearchives.nseindia.com/content/circulars/FAOP44356.pdf",
            "status": "partially_verified",
            "publication_date": "2020-05-12",
            "retrieval_status": "official web-indexed circular inspected; direct PDF archive attempt timed out before response validation",  # noqa: E501 -- evidence strings and serialized records retain full context
            "local_sha256": None,
            "notes": "NSE circular extract corroborates reported 1:15 rights ratio, issue price Rs 1,257 and record date May 14, 2020; complete terms and accounting remain unreviewed.",  # noqa: E501 -- evidence strings and serialized records retain full context
        },
        "2023-07-20": {
            "url": "https://nsearchives.nseindia.com/annual_reports/AR_24850_RELIANCE_2023_2024_07082024143222.pdf",
            "status": "partially_verified",
            "publication_date": "2024-08-07",
            "retrieval_status": "official web-indexed annual report inspected; direct PDF archive attempt timed out before response validation",  # noqa: E501 -- evidence strings and serialized records retain full context
            "local_sha256": None,
            "notes": "NSE-hosted issuer annual report extract states JFSL 1-for-1 consideration, appointed date 2023-03-31 and record date 2023-07-20; event-specific valuation/accounting is unsupported.",  # noqa: E501 -- evidence strings and serialized records retain full context
        },
        "2024-10-28": {
            "url": "https://nsearchives.nseindia.com/corporate/RELIANCE_16102024200409_SE_16102024.pdf",
            "status": "partially_verified",
            "publication_date": "2024-10-16",
            "retrieval_status": "official web-indexed filing inspected; direct PDF archive attempt timed out before response validation",  # noqa: E501 -- evidence strings and serialized records retain full context
            "local_sha256": None,
            "notes": "Issuer filing extract corroborates 1:1 bonus and record date 2024-10-28; allotment/adjustment implementation is not independently reconciled here.",  # noqa: E501 -- evidence strings and serialized records retain full context
        },
    }
    events = []
    for index, row in enumerate(action_rows, 1):
        event = dict(row)
        group_key = tuple(
            row.get(key)
            for key in (
                "symbol",
                "isin",
                "ex_date",
                "record_date",
                "type",
                "cash_amount",
                "ratio_num",
                "ratio_den",
            )
        )
        duplicate_rows = grouped[group_key]
        evidence = official_sources.get(row.get("ex_date"))
        status = evidence["status"] if evidence else "unverified"
        events.append(
            {
                **event,
                "source_row_id": f"tejhq-actions-row-{index:02d}",
                "provider_source": "TejHQ action response (discovery only)",
                "source_url": "https://api.tejhq.dev/v1/actions/RELIANCE",
                "raw_file": str(action_path.relative_to(root)).replace("\\", "/"),
                "raw_file_sha256": action_raw_hash,
                "retrieved_at_utc": action_meta["retrieved_at_utc"],
                "event_group": hashlib.sha256(repr(group_key).encode()).hexdigest()[:16],
                "exchange_duplicate_row_ids": [
                    f"tejhq-actions-row-{i:02d}" for i in duplicate_rows
                ],
                "independent_evidence": evidence,
                "independent_evidence_inspected_at_utc": (
                    generated_at.astimezone(UTC).isoformat() if evidence else None
                ),
                "verification_status": status,
                "announcement_date": None,
                "effective_date": None,
                "subscription_price": None,
                "entitlement_ratio": None,
                "consideration": None,
                "payment_date": None,
                "currency": None,
                "review_notes": (
                    "Provider row is not independently complete evidence. Missing values remain null; "  # noqa: E501 -- evidence strings and serialized records retain full context
                    "no event terms are inferred from raw_subject."
                ),
            }
        )
    action_blockers = validate_action_evidence(events)

    provider_paths = sorted(
        (root / "data/processed").glob("tejhq_RELIANCE_2018-01-01_2026-10-23_*.csv")
    )
    if len(provider_paths) != 1:
        raise ValueError(f"expected exactly one RELIANCE history CSV; found {len(provider_paths)}")
    provider_path = provider_paths[0]
    provider_records = load_historical_file(provider_path)
    provider_by_date = {record.session_date.isoformat(): record for record in provider_records}
    data_start = provider_records[0].session_date
    data_end = provider_records[-1].session_date
    for event in events:
        event_day = date.fromisoformat(event["ex_date"])
        event["within_available_bar_history"] = data_start <= event_day <= data_end
    gap2e = json.loads((reports / "milestone_2e_official_gap_evidence.json").read_text())
    recovery = json.loads((reports / "milestone_2f/recovery_manifest.json").read_text())
    evidence_by_day = {item["date"]: item for item in gap2e["items"]}
    evidence_by_day.update({item["date"]: item for item in recovery["candidate_missing_bars"]})
    bars = []
    for day in TARGET_DATES:
        item = evidence_by_day.get(day)
        if item is None:
            raise ValueError(f"missing preserved source report metadata for {day}")
        filename = item.get("source_filename")
        source_path = root / "data/raw/nse" / filename
        expected_hash = item.get("sha256", item.get("raw_file_sha256"))
        actual_hash = sha256_file(source_path)
        if actual_hash != expected_hash:
            raise ValueError(f"source fingerprint mismatch for {day}: {source_path}")
        source_rows, _ = _source_rows(source_path)
        rows = [
            row
            for row in source_rows
            if row.session_date.isoformat() == day
            and row.symbol == "RELIANCE"
            and row.isin == "INE002A01018"
        ]
        if len(rows) != 1:
            raise ValueError(f"expected one RELIANCE/ISIN source row for {day}, found {len(rows)}")
        source_row = rows[0]
        official = {
            "symbol": source_row.symbol,
            "isin": source_row.isin,
            "exchange": "NSE",
            "series": "EQ",
            "open": str(source_row.open),
            "high": str(source_row.high),
            "low": str(source_row.low),
            "close": str(source_row.close),
            "volume": source_row.volume,
        }
        local = provider_by_date.get(day)
        provider = None
        if local is not None:
            provider = {
                "symbol": local.bar.symbol,
                "open": str(local.bar.open),
                "high": str(local.bar.high),
                "low": str(local.bar.low),
                "close": str(local.bar.close),
                "volume": local.bar.volume,
            }
        comparison = compare_bars(provider, official)
        exact_retrieval = item.get("retrieved_at_utc")
        file_mtime = item.get("retrieved_at_utc_file_mtime")
        bars.append(
            {
                "date": day,
                "source_filename": filename,
                "source_path": str(source_path.relative_to(root)).replace("\\", "/"),
                "source_url": item.get("source_url"),
                "retrieved_at_utc": exact_retrieval,
                "source_timestamp_value": exact_retrieval or file_mtime,
                "source_timestamp_basis": (
                    "recorded_download_timestamp"
                    if exact_retrieval
                    else "local_file_mtime_proxy_not_verified_download_time"
                ),
                "source_sha256": actual_hash,
                "source_row_id": source_row.source,
                "provider": provider,
                "official": official,
                **comparison,
                "recommended_disposition": "retain provider dataset unchanged; candidate official bar requires an approved, versioned migration before use",  # noqa: E501 -- evidence strings and serialized records retain full context
            }
        )

    cost_url = "https://www.nseindia.com/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies"
    costs = [
        {
            "component": "stt",
            "value": "0.001 buy and sell",
            "effective_from": "2026-04-01",
            "effective_to": None,
            "observed_on_source_updated": "2026-04-17",
            "basis": "taxable delivery equity value; official page states VWAP basis",
            "status": "partially_verified",
            "source_url": cost_url,
            "source_published_or_updated": "2026-04-17",
            "limitations": "NSE table shows 0.100% from 2026-04-01 and the same rate through 2026-03-31; prior history and the exact model transaction basis are not established.",  # noqa: E501 -- evidence strings and serialized records retain full context
        },
        {
            "component": "exchange_transaction",
            "value": "0.0000297 each side",
            "effective_from": "2024-10-01",
            "effective_to": None,
            "basis": "traded value per side; Rs 2.97 per lakh",
            "status": "partially_verified",
            "source_url": "https://nsearchives.nseindia.com/content/circulars/FA64232.pdf",
            "source_publication_date": "2024-09-27",
            "limitations": "Rate effective date is sourced; an end date is not verified. Earlier slab and volume-dependent rates require date-versioned schedules.",  # noqa: E501 -- evidence strings and serialized records retain full context
        },
        {
            "component": "stamp_duty",
            "value": "0.00015 buy side",
            "effective_from": "2020-07-01",
            "effective_to": None,
            "basis": "delivery purchase",
            "status": "partially_verified",
            "source_url": cost_url,
            "source_published_or_updated": "2026-04-17",
            "limitations": "NSE page identifies nationwide collection effective date and rate; no end date or pre-2020 regime is sourced here.",  # noqa: E501 -- evidence strings and serialized records retain full context
        },
        {
            "component": "gst",
            "value": "0.18 on stock-broker services",
            "effective_from": None,
            "effective_to": None,
            "basis": "broker service value",
            "status": "partially_verified",
            "source_url": cost_url,
            "source_published_or_updated": "2026-04-17",
            "limitations": "Exact historical applicability and assessable broker fee components require verification for selected broker.",  # noqa: E501 -- evidence strings and serialized records retain full context
        },
        {
            "component": "brokerage",
            "value": None,
            "effective_from": None,
            "effective_to": None,
            "basis": None,
            "status": "unverified",
            "source_url": None,
            "limitations": "No hypothetical broker/plan selected; per-order minimums and rounding unknown.",  # noqa: E501 -- evidence strings and serialized records retain full context
        },
        {
            "component": "delivery_sale_dp",
            "value": None,
            "effective_from": None,
            "effective_to": None,
            "basis": None,
            "status": "unverified",
            "source_url": None,
            "limitations": "Depository participant and tariff not selected; per-settlement/order rules unknown.",  # noqa: E501 -- evidence strings and serialized records retain full context
        },
        {
            "component": "sebi_turnover",
            "value": "0.000001 per side",
            "effective_from": None,
            "effective_to": None,
            "basis": "purchase or sale price",
            "status": "partially_verified",
            "source_url": cost_url,
            "source_published_or_updated": "2026-04-17",
            "limitations": "NSE rate shown, but effective history and assessment/rounding conventions are not recorded in the existing CostSchedule.",  # noqa: E501 -- evidence strings and serialized records retain full context
        },
    ]
    cost_errors = validate_cost_evidence(costs)
    source_hashes = {
        str(path.relative_to(root)).replace("\\", "/"): sha256_file(path)
        for path in (action_path, provider_path)
    }
    provider_manifest_path = provider_path.with_suffix(".json")
    provider_manifest = json.loads(provider_manifest_path.read_text(encoding="utf-8"))
    provider_raw_path = root / provider_manifest["raw_file"]
    if sha256_file(provider_raw_path) != provider_manifest["raw_file_sha256"]:
        raise ValueError("TejHQ OHLCV raw file fingerprint differs from its provenance manifest")
    source_hashes[str(provider_raw_path.relative_to(root)).replace("\\", "/")] = sha256_file(
        provider_raw_path
    )
    source_hashes[str(provider_manifest_path.relative_to(root)).replace("\\", "/")] = sha256_file(
        provider_manifest_path
    )
    source_hashes.update({row["source_path"]: row["source_sha256"] for row in bars})
    source_hashes["reports/milestone_2e_official_gap_evidence.json"] = sha256_file(
        reports / "milestone_2e_official_gap_evidence.json"
    )
    source_hashes["reports/milestone_2f/recovery_manifest.json"] = sha256_file(
        reports / "milestone_2f/recovery_manifest.json"
    )
    source_hashes["reports/milestone_2g_corporate_action_audit.json"] = sha256_file(
        reports / "milestone_2g_corporate_action_audit.json"
    )
    calendar_provenance_path = root / "data/reference/nse_cm_calendar_2018_2024.provenance.json"
    calendar_provenance = json.loads(calendar_provenance_path.read_text(encoding="utf-8"))
    source_hashes[str(calendar_provenance_path.relative_to(root)).replace("\\", "/")] = sha256_file(
        calendar_provenance_path
    )
    for relative in (
        "data/reference/nse_cm_calendar_2018_2024.csv",
        "data/reference/nse_gap_calendar_2018_2024.csv",
        "reports/milestone_2f/readiness.json",
        "reports/milestone_2g_readiness.md",
    ):
        path = root / relative
        source_hashes[relative] = sha256_file(path)
    for year_source in calendar_provenance["sources"]:
        for key in ("file",):
            relative = year_source.get(key)
            if relative:
                path = root / relative.replace("\\", "/")
                if path.is_file():
                    source_hashes[str(path.relative_to(root)).replace("\\", "/")] = sha256_file(
                        path
                    )
        for evidence in year_source.get("special_session_circulars", []) + year_source.get(
            "special_session_reports", []
        ):
            relative = evidence.get("file")
            if relative:
                path = root / relative.replace("\\", "/")
                if path.is_file():
                    source_hashes[str(path.relative_to(root)).replace("\\", "/")] = sha256_file(
                        path
                    )
    blockers = [
        "TejHQ action feed is not completeness-verified; its 25 provider records are discovery evidence only.",  # noqa: E501 -- evidence strings and serialized records retain full context
        "Dividend payment dates and currency are absent; supported cash accounting cannot be sourced from provider response.",  # noqa: E501 -- evidence strings and serialized records retain full context
        "Rights and demerger events remain unsupported by the current position/cash accounting model.",  # noqa: E501 -- evidence strings and serialized records retain full context
        "Eight official NSE bars are confirmed absent from TejHQ and remain unmerged.",
        "Historical action coverage from dataset start through latest session is not complete or independently verified.",  # noqa: E501 -- evidence strings and serialized records retain full context
        "A broker/DP tariff and complete date-effective statutory charge schedule with bases and rounding are not verified.",  # noqa: E501 -- evidence strings and serialized records retain full context
        "Current CostSchedule omits minimum brokerage, SEBI turnover fee, statutory rounding and broker-specific DP tariff details.",  # noqa: E501 -- evidence strings and serialized records retain full context
        "Historical universe membership and survivorship limitations remain; no point-in-time universe is supplied.",  # noqa: E501 -- evidence strings and serialized records retain full context
    ]
    readiness = {
        "milestone": "2H",
        "generated_at_utc": generated_at.astimezone(UTC).isoformat(),
        "paper_only": True,
        "profitability_evaluation_run": False,
        "real_data_backtest_ready": False,
        "decision": "BLOCKED",
        "dataset": {
            "path": str(provider_path.relative_to(root)).replace("\\", "/"),
            "rows": len(provider_records),
            "date_range": [
                provider_records[0].session_date.isoformat(),
                provider_records[-1].session_date.isoformat(),
            ],
            "sha256": sha256_file(provider_path),
            "adjustment_policy": "raw_unadjusted",
        },
        "corporate_actions": {
            "source_rows": len(events),
            "event_groups": len(grouped),
            "source_rows_by_type": dict(Counter(row.get("type") for row in action_rows)),
            "duplicate_exchange_representations": sum(len(ids) > 1 for ids in grouped.values()),
            "verification_status_counts": dict(
                Counter(event["verification_status"] for event in events)
            ),
            "missing_dividend_payment_dates_or_currency": sum(
                event["type"] == "dividend"
                and (not event.get("payment_date") or not event.get("currency"))
                for event in events
            ),
            "provider_identifier_limitation": "TejHQ OHLCV CSV omits ISIN; symbol alone is insufficient for independent instrument identity reconciliation.",  # noqa: E501 -- evidence strings and serialized records retain full context
            "events_within_available_bar_history": sum(
                event["within_available_bar_history"] for event in events
            ),
            "blocked_event_types": ["rights", "demerger", "merger", "buyback", "delisting"],
            "blocker_count": len(action_blockers),
            "blockers": sorted(set(action_blockers)),
            "registry": "corporate_action_evidence_registry.json",
        },
        "missing_bars": {
            "count": len(bars),
            "provider_present_count": sum(row["provider_present"] for row in bars),
            "provider_missing_count": sum(
                row["comparison"] == "provider_bar_missing" for row in bars
            ),
            "provider_value_mismatch_count": sum(row["comparison"] == "mismatch" for row in bars),
            "official_validated_count": len(bars),
            "mismatches_or_missing": sum(row["comparison"] != "match" for row in bars),
            "merged": False,
            "report": "bar_reconciliation.json",
        },
        "cost_schedule": {
            "status": "INCOMPLETE_UNVERIFIED",
            "components": costs,
            "validation_errors": cost_errors,
            "rounding_modelled": False,
            "broker_selected": False,
        },
        "source_fingerprints": dict(sorted(source_hashes.items())),
        "blockers": blockers,
        "next_approval_decisions": [
            "Select whether to pursue a specific hypothetical broker/DP tariff for delivery trades.",  # noqa: E501 -- evidence strings and serialized records retain full context
            "Review an evidence-backed action manifest and explicitly approve a versioned policy for the eight source-verified missing bars.",  # noqa: E501 -- evidence strings and serialized records retain full context
            "Acquire and review a complete authoritative action history and resolve unsupported event accounting before evaluation.",  # noqa: E501 -- evidence strings and serialized records retain full context
        ],
    }
    registry = {
        "schema_version": "1.0",
        "generated_at_utc": readiness["generated_at_utc"],
        "source_response": {
            "path": str(action_path.relative_to(root)).replace("\\", "/"),
            "sha256": action_raw_hash,
            "retrieved_at_utc": action_meta["retrieved_at_utc"],
            "rows": len(action_rows),
            "coverage_limit": "Feed completeness not guaranteed; rows are discovery only.",
        },
        "events": events,
        "independent_sources": official_sources,
    }
    _write_json(out / "corporate_action_evidence_registry.json", registry)
    _write_json(
        out / "bar_reconciliation.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": readiness["generated_at_utc"],
            "bars": bars,
            "merged": False,
        },
    )
    _write_csv(out / "bar_reconciliation.csv", bars)
    _write_json(
        out / "cost_schedule_evidence.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": readiness["generated_at_utc"],
            "paper_only": True,
            "components": costs,
            "source_inspection": [
                {
                    "url": "https://nsearchives.nseindia.com/content/circulars/FA64232.pdf",
                    "published": "2024-09-27",
                    "inspection": "official web-indexed circular; Rs 2.97 per lakh per side effective 2024-10-01",  # noqa: E501 -- evidence strings and serialized records retain full context
                    "local_sha256": None,
                },
                {
                    "url": cost_url,
                    "updated": "2026-04-17",
                    "inspection": "official NSE levy guidance; no local HTML fingerprint",
                    "local_sha256": None,
                },
            ],
            "archive_download_attempt": {
                "status": "failed",
                "error": "Python urllib HTTPS request to official NSE PDF archive timed out after 20 seconds while reading the first response; no PDF file was created.",  # noqa: E501 -- evidence strings and serialized records retain full context
            },
            "validation_errors": cost_errors,
            "cost_inclusive_evaluation_ready": False,
        },
    )
    _write_json(out / "readiness.json", readiness)
    md = [
        "# Milestone 2H Source-Verified Readiness",
        "",
        "**Decision: BLOCKED. No real-data backtest or profitability evaluation was run.**",
        "",
        f"Generated: {readiness['generated_at_utc']}",
        "",
        "## Evidence status",
        "",
        f"- TejHQ action response: {len(events)} rows; provider rows are discovery-only. Cross-exchange representations retained as separate source rows.",  # noqa: E501 -- evidence strings and serialized records retain full context
        f"- Eight NSE official rows: {len(bars)} validated; {readiness['missing_bars']['provider_missing_count']} TejHQ bars absent; no provider OHLCV values were available for comparison; none merged.",  # noqa: E501 -- evidence strings and serialized records retain full context
        f"- Action coverage: {readiness['corporate_actions']['event_groups']} event groups; {readiness['corporate_actions']['events_within_available_bar_history']} source rows fall within available bar history; none fully verified.",  # noqa: E501 -- evidence strings and serialized records retain full context
        f"- Dividend gaps: "
        f"{readiness['corporate_actions']['missing_dividend_payment_dates_or_currency']} rows "
        "lack payment date and/or currency.",
        "- Cost profile: incomplete; no broker/DP selected, no complete historical tariff or rounding policy.",  # noqa: E501 -- evidence strings and serialized records retain full context
        "",
        "## Blocking reasons",
        "",
    ]
    md.extend(f"- {reason}" for reason in blockers)
    md.extend(
        [
            "",
            "## Eight-bar disposition",
            "",
            "Each date has one validated NSE RELIANCE EQ row (`INE002A01018`); "
            "no TejHQ row exists. Official values remain candidates only.",
            "",
            "| Date | NSE OHLC | Volume | Source file | SHA-256 |",
            "|---|---|---:|---|---|",
            *[
                f"| {row['date']} | {row['official']['open']} / "
                f"{row['official']['high']} / {row['official']['low']} / "
                f"{row['official']['close']} | {row['official']['volume']} | "
                f"`{row['source_filename']}` | `{row['source_sha256']}` |"
                for row in bars
            ],
            "",
            "No candidate was merged; every raw report was re-fingerprinted and parsed "
            "without editing the source file.",
            "",
            "## Corporate-action registry",
            "",
            "See `corporate_action_evidence_registry.json`. It preserves every provider row, row ID, exchange, raw subject, retrieval metadata, raw response hash, duplicate group and evidence pointer. Dividend payment dates/currency are absent. Rights and demerger terms remain incomplete for accounting. Selected filings are partially verified only; their local PDF retrieval timed out, so no local PDF hash is claimed.",  # noqa: E501 -- evidence strings and serialized records retain full context
            "",
            "## Cost evidence",
            "",
            "NSE's exchange circular sets cash transaction charges at Rs 2.97 per lakh each side from 2024-10-01. NSE levy guidance lists delivery STT, stamp duty, GST on broker services and SEBI turnover fees. This does not establish the complete 2018–2026 schedule. Brokerage/minimum and DP tariff are unselected; charge bases, per-order/day/settlement allocation and rounding remain incomplete. See `cost_schedule_evidence.json`.",  # noqa: E501 -- evidence strings and serialized records retain full context
            "",
            "## Next decisions",
            "",
        ]
    )
    md.extend(f"- {decision}" for decision in readiness["next_approval_decisions"])
    (out / "readiness.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return readiness


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "date",
        "source_filename",
        "source_path",
        "source_url",
        "retrieved_at_utc",
        "source_timestamp_value",
        "source_timestamp_basis",
        "source_sha256",
        "provider_present",
        "comparison",
        "provider_symbol",
        "provider_isin",
        "provider_open",
        "provider_high",
        "provider_low",
        "provider_close",
        "provider_volume",
        "official_symbol",
        "official_isin",
        "official_exchange",
        "official_series",
        "official_open",
        "official_high",
        "official_low",
        "official_close",
        "official_volume",
        "recommended_disposition",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            official = row["official"]
            provider = row["provider"] or {}
            writer.writerow(
                {
                    "date": row["date"],
                    "source_filename": row["source_filename"],
                    "source_path": row["source_path"],
                    "source_url": row["source_url"],
                    "retrieved_at_utc": row["retrieved_at_utc"],
                    "source_timestamp_value": row["source_timestamp_value"],
                    "source_timestamp_basis": row["source_timestamp_basis"],
                    "source_sha256": row["source_sha256"],
                    "provider_present": row["provider_present"],
                    "comparison": row["comparison"],
                    **{
                        f"provider_{key}": provider.get(key)
                        for key in ("symbol", "isin", "open", "high", "low", "close", "volume")
                    },
                    "official_symbol": official["symbol"],
                    "official_isin": official["isin"],
                    "official_exchange": official["exchange"],
                    "official_series": official["series"],
                    **{
                        f"official_{key}": official[key]
                        for key in ("open", "high", "low", "close", "volume")
                    },
                    "recommended_disposition": row["recommended_disposition"],
                }
            )
