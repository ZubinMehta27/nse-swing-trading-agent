"""Helpers for evidence-only comparison of provider and exchange records."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

BAR_FIELDS = ("open", "high", "low", "close", "volume")


def _bar_signature(row: dict[str, Any]) -> tuple[Decimal | int, ...]:
    return tuple(
        int(row[field]) if field == "volume" else Decimal(str(row[field])) for field in BAR_FIELDS
    )


def classify_source_reconciliation(
    source_rows: list[dict[str, Any]], canonical_rows: list[dict[str, Any]]
) -> str:
    """Classify counts without selecting among duplicate or conflicting records."""
    if not source_rows:
        return "no_matching_official_security_row"
    if len(source_rows) > 1:
        signatures = {_bar_signature(row) for row in source_rows}
        return (
            "conflicting_official_rows"
            if len(signatures) > 1
            else "duplicate_identical_official_rows"
        )
    if not canonical_rows:
        return "official_bar_present_provider_row_missing"
    if len(canonical_rows) > 1:
        signatures = {_bar_signature(row) for row in canonical_rows}
        return (
            "conflicting_canonical_rows"
            if len(signatures) > 1
            else "duplicate_identical_canonical_rows"
        )
    return (
        "official_and_canonical_ohlcv_match"
        if _bar_signature(source_rows[0]) == _bar_signature(canonical_rows[0])
        else "official_and_canonical_ohlcv_differ"
    )
