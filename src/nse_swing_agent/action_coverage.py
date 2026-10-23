"""Auditable corporate-action feed coverage; discovery is not completeness evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


class ActionCoverageError(ValueError):
    """Action registry and retained provider response do not reconcile."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_action_coverage(registry_path: Path, raw_path: Path) -> dict[str, Any]:
    """Audit registered provider discoveries against immutable response bytes."""
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ActionCoverageError(f"cannot read corporate-action evidence: {exc}") from exc
    if not isinstance(registry, dict) or not isinstance(raw, dict):
        raise ActionCoverageError("registry and raw response must be JSON objects")
    response = registry.get("source_response")
    if not isinstance(response, dict) or _sha(raw_path) != response.get("sha256"):
        raise ActionCoverageError("raw action response fingerprint differs from registry")
    raw_events = raw.get("data", raw.get("actions"))
    events = registry.get("events")
    if not isinstance(raw_events, list) or not isinstance(events, list):
        raise ActionCoverageError("raw response and registry must contain event arrays")
    if len(raw_events) != len(events) or len(events) != response.get("rows"):
        raise ActionCoverageError("raw response row count differs from registry provenance")

    indexed: dict[str, dict[str, Any]] = {}
    for index, source_event in enumerate(raw_events, 1):
        indexed[f"tejhq-actions-row-{index:02d}"] = source_event
    type_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    group_representations: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    missing_terms: Counter[str] = Counter()
    unresolved_dates: list[dict[str, str]] = []
    event_report: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            raise ActionCoverageError("registry event must be an object")
        row_id = event.get("source_row_id")
        original = indexed.get(row_id)
        if original is None:
            raise ActionCoverageError(f"unknown source_row_id: {row_id!r}")
        # Require exact agreement on the provider fields that the registry records.
        fields = ("exchange", "symbol", "isin", "ex_date", "record_date", "type", "cash_amount")
        if any(event.get(field) != original.get(field) for field in fields):
            raise ActionCoverageError(f"registered event disagrees with provider row {row_id}")
        kind = str(event.get("type", "unknown"))
        status = str(event.get("verification_status", "unverified"))
        type_counts[kind] += 1
        status_counts[status] += 1
        group = str(event.get("event_group", ""))
        group_representations[group].add(
            (str(event.get("exchange", "")), str(event.get("ex_date", "")), kind)
        )
        missing = []
        required = {
            "dividend": ("cash_amount", "currency", "record_date", "payment_date"),
            "split": ("ratio_num", "ratio_den", "record_date", "effective_date"),
            "bonus": ("ratio_num", "ratio_den", "record_date", "effective_date"),
            "rights": ("ratio_num", "ratio_den", "record_date", "subscription_price"),
            "demerger": ("record_date", "effective_date", "consideration"),
            "merger": ("record_date", "effective_date", "consideration"),
            "buyback": ("record_date", "effective_date", "consideration"),
            "delisting": ("effective_date", "consideration"),
        }.get(kind, ("event_terms",))
        missing = [name for name in required if event.get(name) in (None, "")]
        missing_terms.update(f"{kind}.{name}" for name in missing)
        independent = event.get("independent_evidence")
        independent_path = (
            registry_path.parent.parent.parent / independent.get("local_path")
            if isinstance(independent, dict) and independent.get("local_path")
            else None
        )
        independently_archived = bool(
            isinstance(independent, dict)
            and independent.get("status") == "verified"
            and independent.get("local_sha256")
            and independent_path is not None
            and independent_path.is_file()
            and _sha(independent_path) == independent.get("local_sha256")
        )
        classification = (
            "independently_verified_terms"
            if status == "verified" and independently_archived
            else "partial_external_corroboration"
            if status == "partially_verified"
            else "provider_discovery_only"
        )
        event_report.append(
            {
                "source_row_id": row_id,
                "exchange": event.get("exchange"),
                "symbol": event.get("symbol"),
                "isin": event.get("isin"),
                "ex_date": event.get("ex_date"),
                "record_date": event.get("record_date"),
                "type": kind,
                "reported_terms": {
                    name: event.get(name)
                    for name in (
                        "cash_amount",
                        "currency",
                        "ratio_num",
                        "ratio_den",
                        "subscription_price",
                        "entitlement_ratio",
                        "effective_date",
                        "payment_date",
                        "consideration",
                    )
                },
                "missing_accounting_terms": missing,
                "event_group": group,
                "exchange_duplicate_row_ids": event.get("exchange_duplicate_row_ids", []),
                "provider_row_verified_against_raw": True,
                "verification_status": status,
                "coverage_classification": classification,
                "independent_evidence": independent,
                "independent_source_bytes_verified": independently_archived,
                "provider_source_is_completeness_proof": False,
                "backtest_eligibility": "blocked_pending_complete_verified_action_coverage",
            }
        )
        date_fields_by_type = {
            "dividend": ("ex_date", "record_date", "payment_date"),
            "split": ("ex_date", "record_date", "effective_date"),
            "bonus": ("ex_date", "record_date", "effective_date"),
            "rights": ("ex_date", "record_date", "effective_date"),
            "demerger": ("ex_date", "record_date", "effective_date"),
            "merger": ("ex_date", "record_date", "effective_date"),
            "buyback": ("ex_date", "record_date", "effective_date"),
            "delisting": ("ex_date", "effective_date"),
        }
        for date_field in date_fields_by_type.get(kind, ("ex_date", "effective_date")):
            if event.get(date_field) in (None, ""):
                unresolved_dates.append({"source_row_id": str(row_id), "field": date_field})

    duplicate_groups = {
        group: sorted(representations)
        for group, representations in group_representations.items()
        if len(representations) > 1
    }
    unsupported_types = ("rights", "demerger", "merger", "buyback", "delisting")
    summary = {
        "decision": "BLOCKED",
        "complete_historical_coverage": False,
        "discovery_feed_completeness_guaranteed": False,
        "event_count": len(events),
        "event_type_counts": dict(sorted(type_counts.items())),
        "verification_status_counts": dict(sorted(status_counts.items())),
        "missing_accounting_term_counts": dict(sorted(missing_terms.items())),
        "unresolved_event_dates": unresolved_dates,
        "duplicate_event_group_count": len(duplicate_groups),
        "unsupported_event_record_counts": {
            kind: type_counts.get(kind, 0) for kind in unsupported_types
        },
        "unsupported_types_absent_from_feed_are_not_proven_absent": [
            kind for kind in unsupported_types if type_counts.get(kind, 0) == 0
        ],
        "blockers": [
            "TejHQ action endpoint states historical feed completeness is not guaranteed.",
            "Provider discoveries are not independent evidence of complete event terms.",
            "Some known action types are unsupported by portfolio accounting.",
            "An absent event type is not evidence that no such event occurred.",
        ],
    }
    return {
        "schema_version": "1.0",
        "report_type": "corporate_action_coverage_audit",
        "sources": {
            "registry": {"path": str(registry_path), "sha256": _sha(registry_path)},
            "provider_raw_response": {
                "path": str(raw_path),
                "sha256": _sha(raw_path),
                "provider": "TejHQ",
                "retrieved_at_utc": response.get("retrieved_at_utc"),
                "coverage_limit": response.get("coverage_limit"),
            },
        },
        "summary": summary,
        "duplicate_event_groups": duplicate_groups,
        "events": event_report,
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render concise human-readable findings from the machine-readable audit."""
    summary = report["summary"]
    lines = [
        "# Corporate-action coverage audit",
        "",
        "Decision: **BLOCKED**. Provider action rows are discovery evidence. "
        "This report does not establish complete historical coverage.",
        "",
        f"- Events: {summary['event_count']}",
        "- Verification statuses: "
        f"`{json.dumps(summary['verification_status_counts'], sort_keys=True)}`",
        f"- Event types: `{json.dumps(summary['event_type_counts'], sort_keys=True)}`",
        f"- Duplicate representation groups: {summary['duplicate_event_group_count']}",
        "- Missing terms: "
        f"`{json.dumps(summary['missing_accounting_term_counts'], sort_keys=True)}`",
        f"- Unresolved action dates: {len(summary['unresolved_event_dates'])}",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- {item}" for item in summary["blockers"])
    lines.extend(["", "Raw source and registry fingerprints are recorded in the JSON report.", ""])
    return "\n".join(lines)
