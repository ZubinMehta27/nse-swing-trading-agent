"""Regression tests for conservative Milestone 2K readiness classification."""

import json
from pathlib import Path

import pytest

from nse_swing_agent.milestone_2k_audit import classify_bar_presence


@pytest.mark.parametrize(
    ("status", "observed", "candidate", "expected"),
    [
        ("SESSION", True, False, "observed_expected_session_bar"),
        ("SESSION", False, False, "missing_expected_session_unresolved"),
        (
            "SPECIAL_SESSION",
            False,
            True,
            "provider_bar_missing_official_candidate_available_unmerged",
        ),
        ("HOLIDAY", False, False, "confirmed_exchange_holiday"),
        ("WEEKEND", False, False, "weekend_no_bar_expected"),
        (
            "HOLIDAY",
            True,
            False,
            "observed_bar_on_calendar_non_session_review",
        ),
    ],
)
def test_calendar_classification_never_infers_holiday(
    status: str, observed: bool, candidate: bool, expected: str
) -> None:
    assert classify_bar_presence(status, observed=observed, candidate=candidate) == expected


def test_unknown_calendar_status_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported calendar status"):
        classify_bar_presence("MISSING", observed=False, candidate=False)


def test_milestone_2k_report_if_built_remains_blocked() -> None:
    report = Path("reports/milestone_2k_v4/audit.json")
    if report.exists():
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["decision"] == "BLOCKED"
        assert payload["performance_evaluation_run"] is False
        assert payload["inputs"]["candidate"]["merged"] is False
        bars = payload["candidate_reconciliation"]["bars"]
        assert len(bars) == 8
        assert all(bar["validation"] == "passed" for bar in bars)
        assert all(bar["source_sha256"] == bar["expected_source_sha256"] for bar in bars)
        assert (
            payload["corporate_action_coverage"]["summary"]["complete_historical_coverage"] is False
        )
        special = [
            row
            for row in payload["official_source_archive"]
            if row["path"].endswith("nse_special_session_2024_01_20_MSD59999.pdf")
        ]
        assert len(special) == 1
        assert special[0]["sha256"] == (
            "614b965d1152ed636052e983a01206117ff6af224365348fa00b7165a6baa243"
        )
