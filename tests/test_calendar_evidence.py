from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from nse_swing_agent.calendar_evidence import (
    CalendarEvidenceError,
    calendar_status_for_date,
    compare_bar_values,
    inclusive_dates,
    validate_exception_entries,
    verify_legacy_nse_bhavcopy,
)
from nse_swing_agent.session_calendar import sha256_file

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data/reference/milestone_2p/source_archive"


def test_2024_01_20_bar_matches_independent_nse_cash_bhavcopy() -> None:
    payload = (ARCHIVE / "nse_cm_bhavcopy_2024_01_20.zip").read_bytes()
    official = verify_legacy_nse_bhavcopy(
        payload,
        session_date=date(2024, 1, 20),
        symbol="RELIANCE",
        series="EQ",
        isin="INE002A01018",
    )
    provider_file = next(
        (ROOT / "data/processed").glob("tejhq_RELIANCE_2018-01-01_2026-10-23*.csv")
    )
    with provider_file.open(encoding="utf-8-sig", newline="") as handle:
        provider = next(
            row for row in csv.DictReader(handle) if row["session_date"] == "2024-01-20"
        )
    assert official["archive_member"] == "cm20JAN2024bhav.csv"
    assert official["open"] == "2730"
    assert official["high"] == "2766.95"
    assert official["low"] == "2700"
    assert official["close"] == "2713.3"
    assert official["volume"] == 3_641_697
    assert all(compare_bar_values(official, provider).values())


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2024, 1, 20), "SPECIAL_SESSION"),
        (date(2025, 2, 1), "SPECIAL_SESSION"),
        (date(2025, 10, 21), "SPECIAL_SESSION"),
        (date(2025, 2, 2), "WEEKEND"),
        (date(2025, 6, 7), "WEEKEND_HOLIDAY"),
        (date(2025, 2, 26), "HOLIDAY"),
        (date(2025, 2, 27), "SESSION"),
        (date(2026, 1, 15), "HOLIDAY"),
        (date(2026, 10, 23), "UNRESOLVED"),
    ],
)
def test_special_holidays_weekends_and_unresolved_classification(day: date, expected: str) -> None:
    holidays = {
        date(2025, 2, 26): "NSE-CMTR-65587-2025",
        date(2026, 1, 15): "NSE-CMTR-72260-2026",
        date(2025, 10, 21): "NSE-CMTR-65587-2025",
    }
    weekend_holidays = {date(2025, 6, 7): "NSE-CMTR-65587-2025"}
    specials = {
        date(2024, 1, 20): "NSE-MSD59999-2024",
        date(2025, 2, 1): "NSE-CMTR-65729-2025",
        date(2025, 10, 21): "NSE-CMTR-70319-2025",
    }
    status, _basis = calendar_status_for_date(
        day,
        holidays=holidays,
        weekend_holidays=weekend_holidays,
        special_sessions=specials,
        first_day=date(2018, 1, 1),
        last_day=date(2026, 10, 22),
    )
    assert status == expected


def test_cash_market_registry_does_not_accept_f_and_o_source() -> None:
    registry = json.loads(
        (ROOT / "data/reference/milestone_2p/session_calendar_registry_v2.json").read_text(
            encoding="utf-8"
        )
    )
    assert registry["cash_market_identity_policy"].startswith(
        "Only sources explicitly marked CAPITAL MARKET"
    )
    assert "2025-02-01" in {item["date"] for item in registry["exceptions"]}
    assert all(
        "F&O" not in record.get("segment", "") for record in registry["annual_holidays"].values()
    )
    registry["annual_holidays"]["2025"]["source_id"] = "NSE-FO-FAKE"
    from scripts.build_milestone_2p_audit import _holiday_maps

    with pytest.raises(CalendarEvidenceError, match="non-CM source"):
        _holiday_maps(registry)


def test_duplicate_exceptions_and_invalid_effective_dates_fail() -> None:
    base = {
        "exception_id": "NSE-CM-TEST",
        "date": "2025-02-01",
        "status": "SPECIAL_SESSION",
        "source_ids": ["source"],
        "verification_status": "verified_session_only",
    }
    validate_exception_entries([base])
    with pytest.raises(CalendarEvidenceError, match="duplicate"):
        validate_exception_entries([base, dict(base, exception_id="OTHER")])
    with pytest.raises(CalendarEvidenceError, match="malformed"):
        validate_exception_entries([dict(base, date="2025-02-30")])


def test_source_provenance_hashes_and_candidate_recovery_are_unchanged() -> None:
    manifest = json.loads(
        (ROOT / "data/reference/milestone_2p/source_archive_manifest_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(manifest["sources"]) == 7
    for item in manifest["sources"]:
        path = ROOT / item["archive_path"]
        assert path.stat().st_size == item["byte_length"]
        assert sha256_file(path) == item["sha256"]
        assert item["http_status"] == 200
        assert item["retrieved_at_utc"]
    candidate_manifest = json.loads(
        (
            ROOT / "data/validation/recovery_candidates/milestone_2j_a_v2/recovery_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert candidate_manifest["candidate_rows"] == 8
    assert candidate_manifest["automatic_merge_performed"] is False
    for bar in candidate_manifest["bars"]:
        assert sha256_file(ROOT / bar["source_path"]) == bar["expected_source_sha256"]


def test_idempotent_calendar_generation_bounds_and_missing_bar_source_block() -> None:
    assert inclusive_dates(date(2025, 1, 1), date(2025, 1, 2)) == [
        date(2025, 1, 1),
        date(2025, 1, 2),
    ]
    with pytest.raises(CalendarEvidenceError, match="precedes"):
        inclusive_dates(date(2025, 2, 2), date(2025, 2, 1))
    payload = (ARCHIVE / "nse_cm_bhavcopy_2024_01_20.zip").read_bytes()
    with pytest.raises(CalendarEvidenceError, match="exactly one"):
        verify_legacy_nse_bhavcopy(
            payload,
            session_date=date(2024, 1, 20),
            symbol="RELIANCE",
            series="EQ",
            isin="INE0000000000",
        )
    report_path = ROOT / "reports/milestone_2p_v1/audit.json"
    original_digest = sha256_file(report_path)
    from scripts.build_milestone_2p_audit import build

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build(ROOT, ROOT / "reports/milestone_2p_v1")
    assert sha256_file(report_path) == original_digest
