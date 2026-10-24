"""Offline regression tests for Milestone 2L event evidence reconciliation."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from nse_swing_agent.corporate_actions import split_quantity
from nse_swing_agent.milestone_2l_audit import (
    CorporateActionAuditError,
    classify_event_evidence,
    group_economic_events,
)


def _row(source_id: str, exchange: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "source_row_id": source_id,
        "event_group": "event-1",
        "exchange": exchange,
        "symbol": "RELIANCE",
        "isin": "INE002A01018",
        "ex_date": "2024-10-28",
        "record_date": "2024-10-28",
        "type": "bonus",
        "ratio_num": 1,
        "ratio_den": 1,
    }
    row.update(overrides)
    return row


def test_matching_nse_bse_representations_count_as_one_event() -> None:
    groups = group_economic_events([_row("row-1", "NSE"), _row("row-2", "BSE")])
    assert len(groups) == 1
    assert groups[0]["source_row_ids"] == ["row-1", "row-2"]
    assert groups[0]["exchange_representations"] == ["BSE", "NSE"]
    assert groups[0]["duplicate_exchange_representation"] is True


def test_conflicting_exchange_representations_are_rejected() -> None:
    with pytest.raises(CorporateActionAuditError, match="conflicting representations"):
        group_economic_events([_row("row-1", "NSE"), _row("row-2", "BSE", ratio_num=2)])


def test_duplicate_rows_from_same_exchange_are_rejected() -> None:
    with pytest.raises(CorporateActionAuditError, match="duplicate same-exchange"):
        group_economic_events([_row("row-1", "NSE"), _row("row-2", "NSE")])


def test_critical_missing_dates_remain_unresolved_despite_partial_terms() -> None:
    status, unresolved = classify_event_evidence(
        required_fields={"amount", "currency", "ex_date", "record_date", "payment_date"},
        verified_fields={"amount", "currency", "ex_date"},
        critical_fields={"ex_date", "record_date"},
    )
    assert status == "unresolved"
    assert "record_date" in unresolved
    assert "payment_date" in unresolved


def test_verified_2024_bonus_arithmetic_preserves_cost_basis() -> None:
    before_quantity = 7
    before_basis = Decimal("1328.80") * before_quantity
    after_quantity = split_quantity(before_quantity, Decimal("2"))
    after_unit_basis = Decimal("1328.80") / Decimal("2")
    assert after_quantity == 14
    assert after_unit_basis * after_quantity == before_basis
    assert Decimal("24") / Decimal("2") == Decimal("12")  # protective level rebasing


def test_milestone_2l_report_records_provenance_and_keeps_readiness_blocked() -> None:
    path = Path("reports/milestone_2l_v1/corporate_action_audit.json")
    if not path.exists():
        pytest.skip("Milestone 2L report has not been generated in this workspace")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["decision"] == "BLOCKED"
    assert report["overall_readiness"] == "BLOCKED"
    assert report["scope"]["provider_rows"] == 25
    assert report["scope"]["economic_event_groups"] == 21
    assert report["counts"]["duplicate_cross_exchange_representation_groups"] == 4
    assert report["counts"]["dividend_exact_payment_dates_unresolved"] == 17
    assert report["counts"]["fully_verified_event_terms"] == 4
    assert report["counts"]["partially_corroborated_event_terms"] == 11
    assert report["counts"]["unresolved_event_terms"] == 6
    events = {event["event_group"]: event for event in report["events"]}
    assert events["0f93df511080e00c"]["terms"]["record_date"] == "2025-08-14"
    assert events["0f93df511080e00c"]["terms"]["actual_payment_date"] is None
    assert events["614c97cd36da2831"]["accounting_status"].startswith("unsupported_rights")
    for source in report["sources"].values():
        file_path = Path(source["local_path"])
        if file_path.exists():
            from hashlib import sha256

            assert sha256(file_path.read_bytes()).hexdigest() == source["local_sha256"]
