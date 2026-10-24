"""Small validation helpers for source-backed NSE calendar audits."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zipfile import BadZipFile, ZipFile


class CalendarEvidenceError(ValueError):
    """Raised when archived exchange evidence is malformed or conflicting."""


def validate_exception_entries(entries: list[dict[str, Any]]) -> None:
    """Reject duplicate exception dates/identifiers and unsupported statuses."""
    seen_dates: set[str] = set()
    seen_ids: set[str] = set()
    for entry in entries:
        try:
            day = str(entry["date"])
            date.fromisoformat(day)
            identifier = str(entry["exception_id"])
            status = str(entry["status"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CalendarEvidenceError(f"malformed calendar exception: {exc}") from exc
        if day in seen_dates or identifier in seen_ids:
            raise CalendarEvidenceError(f"duplicate calendar exception date or ID: {day}")
        if status not in {"HOLIDAY", "SPECIAL_SESSION"}:
            raise CalendarEvidenceError(f"unsupported calendar exception status {status!r}")
        if not entry.get("source_ids"):
            raise CalendarEvidenceError(f"calendar exception has no source reference: {day}")
        if entry.get("verification_status") not in {
            "verified",
            "verified_session_only",
            "verified_session_and_bar",
        }:
            raise CalendarEvidenceError(f"calendar exception is not verified: {day}")
        seen_dates.add(day)
        seen_ids.add(identifier)


def calendar_status_for_date(
    day: date,
    *,
    holidays: dict[date, str],
    weekend_holidays: dict[date, str] | None = None,
    special_sessions: dict[date, str],
    first_day: date,
    last_day: date,
) -> tuple[str, str]:
    """Return the evidenced exception or a rule-inferred ordinary/weekend status.

    Special sessions are checked before the generic weekend and holiday rules so
    that an official live-session notice can override either expectation.
    """
    if not first_day <= day <= last_day:
        return "UNRESOLVED", "outside_sourced_calendar_range"
    if day in special_sessions:
        return "SPECIAL_SESSION", f"verified_special_session:{special_sessions[day]}"
    if weekend_holidays and day in weekend_holidays:
        return "WEEKEND_HOLIDAY", f"verified_cm_holiday_on_weekend:{weekend_holidays[day]}"
    if day in holidays and day.weekday() < 5:
        return "HOLIDAY", f"verified_cm_holiday:{holidays[day]}"
    if day.weekday() >= 5:
        return "WEEKEND", "inferred_from_official_equities_weekly_rule"
    return "SESSION", "inferred_ordinary_session_from_official_weekly_rule_and_cm_holidays"


def inclusive_dates(first_day: date, last_day: date) -> list[date]:
    """Enumerate dates chronologically; reject reversed bounds."""
    if last_day < first_day:
        raise CalendarEvidenceError("calendar end date precedes start date")
    result: list[date] = []
    current = first_day
    while current <= last_day:
        result.append(current)
        current += timedelta(days=1)
    return result


def verify_legacy_nse_bhavcopy(
    payload: bytes, *, session_date: date, symbol: str, series: str, isin: str
) -> dict[str, Any]:
    """Read one instrument from an archived NSE legacy cash-market bhavcopy."""
    try:
        with ZipFile(io.BytesIO(payload)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise CalendarEvidenceError(
                    f"expected one CSV in bhavcopy ZIP; found {len(csv_names)}"
                )
            text = archive.read(csv_names[0]).decode("utf-8-sig")
    except (BadZipFile, UnicodeDecodeError, OSError) as exc:
        raise CalendarEvidenceError(f"invalid NSE bhavcopy archive: {exc}") from exc

    rows = list(csv.DictReader(io.StringIO(text)))
    required = {
        "SYMBOL",
        "SERIES",
        "OPEN",
        "HIGH",
        "LOW",
        "CLOSE",
        "TOTTRDQTY",
        "TIMESTAMP",
        "ISIN",
    }
    if not rows or not required.issubset(rows[0]):
        raise CalendarEvidenceError("NSE bhavcopy is missing required identity or OHLCV columns")
    matches = [
        row
        for row in rows
        if row["SYMBOL"].strip() == symbol
        and row["SERIES"].strip() == series
        and row["ISIN"].strip() == isin
    ]
    if len(matches) != 1:
        raise CalendarEvidenceError(
            f"expected exactly one {symbol}/{series}/{isin} row; found {len(matches)}"
        )
    row = matches[0]
    if row["TIMESTAMP"].strip() != session_date.strftime("%d-%b-%Y").upper():
        raise CalendarEvidenceError("bhavcopy row timestamp does not match requested session date")
    try:
        values = {
            key: Decimal(row[source].strip())
            for key, source in {
                "open": "OPEN",
                "high": "HIGH",
                "low": "LOW",
                "close": "CLOSE",
            }.items()
        }
        volume = int(row["TOTTRDQTY"].strip())
    except (InvalidOperation, ValueError) as exc:
        raise CalendarEvidenceError(f"malformed OHLCV value in official row: {exc}") from exc
    if any(value <= 0 for value in values.values()) or volume < 0:
        raise CalendarEvidenceError("official row has nonpositive price or negative volume")
    if values["low"] > min(values["open"], values["close"]):
        raise CalendarEvidenceError("official low exceeds open or close")
    if values["high"] < max(values["open"], values["close"]):
        raise CalendarEvidenceError("official high is below open or close")
    return {
        "archive_member": csv_names[0],
        "symbol": symbol,
        "series": series,
        "isin": isin,
        "session_date": session_date.isoformat(),
        **{key: format(value, "f") for key, value in values.items()},
        "volume": volume,
    }


def compare_bar_values(official: dict[str, Any], provider: dict[str, str]) -> dict[str, bool]:
    """Compare all OHLCV fields numerically; no missing field is treated as a match."""
    fields = ("open", "high", "low", "close")
    result = {field: Decimal(str(official[field])) == Decimal(provider[field]) for field in fields}
    result["volume"] = int(official["volume"]) == int(provider["volume"])
    return result
