"""Offline regression tests for evidence-backed calendar corrections."""

import json
from pathlib import Path

import pytest

from nse_swing_agent.session_calendar import (
    CalendarExceptionError,
    apply_verified_exceptions,
    classify_calendar_observation,
    load_verified_exceptions,
    read_calendar,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/reference/nse_cm_calendar_2018_2024.csv"
REGISTRY = ROOT / "data/reference/milestone_2o/session_calendar_exceptions_v1.json"


def test_verified_2024_01_20_session_overrides_weekend_only_in_derived_calendar() -> None:
    base = read_calendar(BASE)
    source_status = base["2024-01-20"]["status"]
    exceptions = load_verified_exceptions(REGISTRY, BASE)
    effective = apply_verified_exceptions(base, exceptions)
    assert source_status == "WEEKEND"
    assert base["2024-01-20"]["status"] == "WEEKEND"
    assert effective["2024-01-20"]["status"] == "SPECIAL_SESSION"
    assert effective["2024-01-20"]["correction_id"] == "NSE-CM-2024-01-20-MSD59999"
    assert (
        classify_calendar_observation(
            effective["2024-01-20"]["status"],
            provider_bar_present=True,
            candidate_bar_available=False,
        )
        == "provider_bar_on_verified_special_session"
    )


@pytest.mark.parametrize(
    ("status", "observed", "candidate", "expected"),
    [
        ("WEEKEND", False, False, "inferred_weekend_non_session_no_bar"),
        ("HOLIDAY", False, False, "confirmed_exchange_holiday"),
        ("SESSION", False, False, "provider_omission_on_inferred_ordinary_session"),
        ("SPECIAL_SESSION", False, False, "provider_omission_on_verified_special_session"),
        ("UNRESOLVED", False, False, "unresolved_calendar_expectation"),
    ],
)
def test_weekends_holidays_omissions_and_unresolved_dates_are_distinct(
    status: str, observed: bool, candidate: bool, expected: str
) -> None:
    assert (
        classify_calendar_observation(
            status, provider_bar_present=observed, candidate_bar_available=candidate
        )
        == expected
    )


def test_provider_bar_on_unregistered_weekend_is_review_not_a_session_inference() -> None:
    assert (
        classify_calendar_observation(
            "WEEKEND", provider_bar_present=True, candidate_bar_available=False
        )
        == "provider_bar_on_inferred_weekend_review"
    )


def test_candidate_bhavcopy_is_direct_session_evidence_without_merging() -> None:
    assert (
        classify_calendar_observation(
            "SESSION", provider_bar_present=False, candidate_bar_available=True
        )
        == "official_candidate_unmerged_confirms_session"
    )


def test_registry_fails_closed_if_base_calendar_fingerprint_changes(tmp_path: Path) -> None:
    copied_base = tmp_path / "data/reference" / BASE.name
    copied_base.parent.mkdir(parents=True)
    copied_base.write_bytes(BASE.read_bytes() + b"\n")
    with pytest.raises(CalendarExceptionError, match="fingerprint differs"):
        load_verified_exceptions(REGISTRY, copied_base)


def test_registry_fails_closed_if_exception_source_hash_is_falsified(tmp_path: Path) -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    registry["exceptions"][0]["source"]["sha256"] = "0" * 64
    copy = tmp_path / "registry.json"
    copy.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(CalendarExceptionError, match="fingerprint mismatch"):
        load_verified_exceptions(copy, BASE)


def test_milestone_2o_audit_preserves_candidate_rows_and_stays_blocked() -> None:
    audit_path = ROOT / "reports/milestone_2o_v4/audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["decision"] == "BLOCKED"
    assert audit["candidate_bars_merged"] is False
    assert audit["recovery_candidate_reconciliation"]["candidate_rows"] == 8
    assert audit["recovery_candidate_reconciliation"]["all_sources_rehashed_and_matched"] is True
    assert audit["instrument_identity"]["scope"] == "RELIANCE/NSE only"
    assert audit["instrument_identity"]["provider"]["isin_field_present"] is False
    assert audit["instrument_identity"]["provider"]["series_field_present"] is False
    assert audit["independent_readiness_gates"]["corporate_action_completeness"] == "BLOCKED"
    assert audit["independent_readiness_gates"]["historical_transaction_cost_coverage"] == "BLOCKED"
    assert audit["bar_quality_review_dates"] == ["2024-01-20"]
    assert audit["unresolved_calendar_periods"][0]["start"] == "2025-01-01"


def test_effective_calendar_is_separate_and_has_provenance_hash() -> None:
    base = read_calendar(BASE)
    effective_path = ROOT / "data/reference/milestone_2o/calendar_effective_v4.csv"
    provenance_path = ROOT / "data/reference/milestone_2o/calendar_effective_v4.provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    import hashlib

    assert hashlib.sha256(BASE.read_bytes()).hexdigest() == provenance["source_calendar_sha256"]
    assert (
        hashlib.sha256(effective_path.read_bytes()).hexdigest()
        == provenance["effective_calendar_sha256"]
    )
    assert base["2024-01-20"]["status"] == "WEEKEND"
