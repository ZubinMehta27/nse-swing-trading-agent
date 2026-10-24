"""Evidence-backed, versioned session-calendar exception handling."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any


class CalendarExceptionError(ValueError):
    """A calendar exception is unverifiable, conflicting, or out of scope."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_calendar(path: Path) -> dict[str, dict[str, str]]:
    """Read the immutable source calendar; duplicate or malformed dates fail closed."""
    rows: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"session_date", "status", "source", "source_url"}
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise CalendarExceptionError("source calendar lacks required provenance columns")
        for line, row in enumerate(reader, 2):
            value = row.get("session_date", "")
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError("date is not canonical ISO format")
            except (TypeError, ValueError) as exc:
                raise CalendarExceptionError(f"calendar row {line}: invalid session date") from exc
            if value in rows:
                raise CalendarExceptionError(f"calendar row {line}: duplicate session date {value}")
            if not row.get("status") or not row.get("source") or not row.get("source_url"):
                raise CalendarExceptionError(f"calendar row {line}: status and provenance required")
            rows[value] = {key: value for key, value in row.items() if value is not None}
    return rows


def load_verified_exceptions(
    registry_path: Path, base_calendar_path: Path
) -> dict[str, dict[str, Any]]:
    """Load overrides only when base and official source fingerprints match."""
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalendarExceptionError(f"cannot read exception registry: {exc}") from exc
    if registry.get("schema_version") != "nse-session-calendar-exceptions-v1":
        raise CalendarExceptionError("unsupported calendar exception registry version")
    base_evidence = registry.get("base_calendar", {})
    declared_path = Path(str(base_evidence.get("path", ""))).as_posix()
    actual_path = base_calendar_path.resolve().as_posix()
    if not actual_path.endswith(declared_path):
        raise CalendarExceptionError("registry base calendar path does not match input")
    if sha256_file(base_calendar_path) != base_evidence.get("sha256"):
        raise CalendarExceptionError("base calendar fingerprint differs from registry")
    base = read_calendar(base_calendar_path)
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(registry.get("exceptions", []), 1):
        try:
            day = item["session_date"]
            date.fromisoformat(day)
            if item["verification_status"] != "verified":
                raise ValueError("exception is not marked verified")
            if item["correction_kind"] != "special_session_override":
                raise ValueError("unsupported correction_kind")
            if item["corrected_status"] != "SPECIAL_SESSION":
                raise ValueError("special-session override must resolve to SPECIAL_SESSION")
            if day not in base:
                raise ValueError("exception date is outside source calendar")
            if base[day]["status"] != item["expected_base_status"]:
                raise ValueError("base calendar status differs from exception expectation")
            if day in result:
                raise ValueError(f"duplicate exception for {day}")
            source = item["source"]
            source_path = base_calendar_path.parent.parent.parent / source["archive_path"]
            if not source.get("url") or not source_path.is_file():
                raise ValueError("official source URL or archived bytes are missing")
            if sha256_file(source_path) != source.get("sha256"):
                raise ValueError("official source fingerprint mismatch")
            if not source.get("retrieved_at_utc") or not source.get("publication_date"):
                raise ValueError("source publication and retrieval dates are required")
            result[day] = item
        except (KeyError, TypeError, ValueError) as exc:
            raise CalendarExceptionError(f"exception {index}: {exc}") from exc
    return result


def apply_verified_exceptions(
    base_calendar: dict[str, dict[str, str]],
    exceptions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, str]]:
    """Return a separate corrected mapping; the caller's source mapping is untouched."""
    corrected = {day: dict(row) for day, row in base_calendar.items()}
    for day, item in exceptions.items():
        if day not in corrected:
            raise CalendarExceptionError(f"exception date {day} is outside source calendar")
        if corrected[day]["status"] != item["expected_base_status"]:
            raise CalendarExceptionError(f"unexpected source status for exception date {day}")
        corrected[day]["status"] = item["corrected_status"]
        corrected[day]["correction_id"] = str(item["exception_id"])
        corrected[day]["correction_source_url"] = str(item["source"]["url"])
        corrected[day]["correction_source_sha256"] = str(item["source"]["sha256"])
        corrected[day]["calendar_basis"] = "verified_date_specific_exchange_circular"
    return corrected


def classify_calendar_observation(
    status: str,
    *,
    provider_bar_present: bool,
    candidate_bar_available: bool,
) -> str:
    """Classify observed bars separately from inferred calendar expectations."""
    normalized = status.strip().upper()
    if normalized == "HOLIDAY":
        return (
            "provider_bar_on_confirmed_holiday_review"
            if provider_bar_present
            else "confirmed_exchange_holiday"
        )
    if normalized in {"WEEKEND", "WEEKEND_HOLIDAY"}:
        return (
            "provider_bar_on_inferred_weekend_review"
            if provider_bar_present
            else "inferred_weekend_non_session_no_bar"
        )
    if normalized not in {"SESSION", "SPECIAL_SESSION", "UNRESOLVED"}:
        raise CalendarExceptionError(f"unsupported calendar status: {status!r}")
    if normalized == "UNRESOLVED":
        return "unresolved_calendar_expectation"
    if provider_bar_present:
        return (
            "provider_bar_on_verified_special_session"
            if normalized == "SPECIAL_SESSION"
            else "provider_bar_on_inferred_ordinary_session"
        )
    if candidate_bar_available:
        return "official_candidate_unmerged_confirms_session"
    return (
        "provider_omission_on_verified_special_session"
        if normalized == "SPECIAL_SESSION"
        else "provider_omission_on_inferred_ordinary_session"
    )
