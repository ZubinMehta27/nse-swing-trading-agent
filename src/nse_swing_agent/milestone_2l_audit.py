"""Strict grouping and evidence classification for the Milestone 2L audit."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class CorporateActionAuditError(ValueError):
    """Provider representations cannot be reconciled without guessing."""


def group_economic_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group same-event NSE/BSE rows; reject conflicting terms within a group."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        group = row.get("event_group")
        if not isinstance(group, str) or not group:
            raise CorporateActionAuditError("provider event is missing event_group")
        grouped[group].append(row)

    result: list[dict[str, Any]] = []
    compared_fields = (
        "symbol",
        "isin",
        "ex_date",
        "record_date",
        "type",
        "cash_amount",
        "ratio_num",
        "ratio_den",
        "subscription_price",
        "effective_date",
        "payment_date",
    )
    for group, representations in sorted(grouped.items()):
        first = representations[0]
        for row in representations[1:]:
            differences = [field for field in compared_fields if row.get(field) != first.get(field)]
            if differences:
                raise CorporateActionAuditError(
                    f"conflicting representations in event_group {group}: " + ", ".join(differences)
                )
        exchanges = [str(row.get("exchange", "")) for row in representations]
        if len(exchanges) != len(set(exchanges)):
            raise CorporateActionAuditError(f"duplicate same-exchange rows in event_group {group}")
        result.append(
            {
                "event_group": group,
                "source_row_ids": sorted(str(row["source_row_id"]) for row in representations),
                "exchange_representations": sorted(exchanges),
                "representation_count": len(representations),
                "duplicate_exchange_representation": len(representations) > 1,
                "provider_terms": {field: first.get(field) for field in compared_fields},
            }
        )
    return result


def classify_event_evidence(
    *,
    required_fields: set[str],
    verified_fields: set[str],
    critical_fields: set[str] | None = None,
) -> tuple[str, list[str]]:
    """Classify completeness from explicit field evidence, never from provider presence."""
    if not verified_fields <= required_fields:
        extra = sorted(verified_fields - required_fields)
        raise CorporateActionAuditError(
            "verified fields are not in the event requirements: " + ", ".join(extra)
        )
    unresolved = sorted(required_fields - verified_fields)
    if not unresolved:
        return "fully_verified", []
    if critical_fields and critical_fields.intersection(unresolved):
        return "unresolved", unresolved
    if verified_fields:
        return "partially_corroborated", unresolved
    return "unresolved", unresolved
