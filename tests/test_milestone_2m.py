"""Offline evidence and safety regressions for the Milestone 2M audit."""

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from nse_swing_agent.corporate_actions import (
    ActionKind,
    CorporateAction,
    unsupported_action_reason,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/milestone_2m_v4/corporate_action_audit.json"
MANIFEST = ROOT / "reports/milestone_2m_v4/source_manifest.json"
TIMING_READINESS = ROOT / "reports/milestone_2m_v5/payment_timing_readiness.json"


def test_2010_provider_event_is_reconciled_without_creating_a_new_group() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    event = next(row for row in report["events"] if row["event_group"] == "5061a9fcd61e1c1b")
    supplement = event["milestone_2m_supplement"]
    assert report["scope"]["economic_event_groups"] == 21
    assert supplement["same_group_as_milestone_2l"] is True
    assert supplement["record_date"] == "2010-05-11"
    assert supplement["amount_inr_per_share"] == "7.00"
    assert "primary-source ex-date confirmation" in supplement["unresolved"]
    assert report["decision"] == "BLOCKED"
    assert report["real_data_backtest_run"] is False


def test_supplemental_source_hashes_and_prior_audit_fingerprint_are_valid() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    previous = ROOT / "reports/milestone_2l_v1/corporate_action_audit.json"
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == report["prior_audit"]["sha256"]
    for source in manifest["supplemental_sources"].values():
        path = ROOT / source["archive_path"]
        assert source["retrieved_at_utc"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]


def test_payment_window_cannot_be_substituted_for_exact_dividend_payment_date() -> None:
    with pytest.raises(ValueError, match="payment_date"):
        CorporateAction(
            symbol="RELIANCE",
            isin="INE002A01018",
            kind=ActionKind.DIVIDEND,
            ex_date=date(2020, 7, 2),
            record_date=date(2020, 7, 3),
            payment_date=None,
            cash_per_share=Decimal("6.50"),
            currency="INR",
            source="synthetic-window-test",
            source_fingerprint="a" * 64,
            retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
            verification_status="verified",
        )


@pytest.mark.parametrize("kind", [ActionKind.RIGHTS, ActionKind.DEMERGER])
def test_rights_and_demerger_remain_explicitly_unsupported(kind: ActionKind) -> None:
    event = CorporateAction(
        symbol="RELIANCE",
        isin="INE002A01018",
        kind=kind,
        ex_date=date(2020, 1, 2),
        source="synthetic-blocking-test",
        source_fingerprint="b" * 64,
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        verification_status="verified",
    )
    reason = unsupported_action_reason(event)
    assert reason is not None
    assert kind.value in reason


def test_payment_timing_readiness_distinguishes_dates_windows_and_unknowns() -> None:
    report = json.loads(TIMING_READINESS.read_text(encoding="utf-8"))
    assert report["payment_timing_counts"] == {
        "EXACT_DATE": 0,
        "DOCUMENTED_WINDOW": 3,
        "UNKNOWN": 14,
    }
    assert report["accounting_support"]["DOCUMENTED_WINDOW"].startswith("unsupported")
    assert report["cash_safety"]["credit_at_earliest_window_date"] is False
    assert report["cash_safety"]["credit_at_latest_window_date_as_exact"] is False
    assert report["overall_readiness"] == "BLOCKED"
    assert report["eligible_historical_window"] is None
    assert report["real_data_backtest_run"] is False
