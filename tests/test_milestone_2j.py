"""Milestone 2J cost arithmetic and candidate-recovery safety checks."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from nse_swing_agent.bar_recovery import RECOVERY_DATES, build_recovery_candidate
from nse_swing_agent.cost_profiles import (
    CostCoverageError,
    CostProfileError,
    CostTransaction,
    load_cost_profile,
)

ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_costs_are_itemized_once_and_dp_groups_per_symbol_day() -> None:
    profile = load_cost_profile(
        ROOT / "tests/fixtures/synthetic_cost_profile.json", allow_synthetic=True
    )
    transactions = [
        CostTransaction("b1", date(2025, 1, 2), "ABC", "BUY", Decimal("100000"), 10, "ob1"),
        CostTransaction("s1", date(2025, 1, 3), "ABC", "SELL", Decimal("100000"), 5, "os1", "T1"),
        CostTransaction("s2", date(2025, 1, 3), "ABC", "SELL", Decimal("100000"), 5, "os2", "T1"),
    ]
    result = profile.quote(transactions)
    lines = {(line.component, line.aggregation_key): line.amount for line in result.lines}
    assert lines[("dp", "2025-01-03:ABC")] == Decimal("13.00")
    assert lines[("gst_dp", "2025-01-03:ABC")] == Decimal("2.34")
    assert sum(line.amount for line in result.lines if "s1" in line.transaction_ids) == Decimal(
        "246.32"
    )
    assert sum(line.amount for line in result.lines if "s2" in line.transaction_ids) == Decimal(
        "246.32"
    )
    assert result.total == Decimal("728.28")
    # Shared one-per-day DP is charged once, not once for each sell fill.
    assert sum(line.amount for line in result.lines if line.component == "dp") == Decimal("13.00")


def test_synthetic_profile_requires_explicit_opt_in() -> None:
    with pytest.raises(CostProfileError, match="allow_synthetic"):
        load_cost_profile(ROOT / "tests/fixtures/synthetic_cost_profile.json")


def test_hypothetical_real_profile_fails_closed_for_all_dates() -> None:
    profile = load_cost_profile(
        ROOT / "config/cost_profiles/zerodha_resident_individual_nse_delivery_hypothetical.json"
    )
    assert profile.status == "partial"
    assert profile.coverage_errors(date(2025, 1, 2))
    with pytest.raises(CostCoverageError):
        profile.quote(
            [CostTransaction("x", date(2025, 1, 2), "RELIANCE", "BUY", Decimal("1000"), 1)]
        )


def test_cost_profile_rejects_overlapping_rules(tmp_path: Path) -> None:
    payload = json.loads((ROOT / "tests/fixtures/synthetic_cost_profile.json").read_text())
    payload["rules"].append(dict(payload["rules"][0], effective_from="2022-01-01"))
    payload_path = tmp_path / "overlap.json"
    payload_path.write_text(json.dumps(payload))
    with pytest.raises(CostProfileError, match="overlapping intervals"):
        load_cost_profile(payload_path, allow_synthetic=True)


@pytest.mark.parametrize(
    ("bound", "expected"), [("minimum_amount", "309.98"), ("cap_amount", "191.98")]
)
def test_cost_profile_applies_configured_minimum_and_cap(
    tmp_path: Path, bound: str, expected: str
) -> None:
    payload = json.loads((ROOT / "tests/fixtures/synthetic_cost_profile.json").read_text())
    brokerage = next(rule for rule in payload["rules"] if rule["component"] == "brokerage")
    brokerage[bound] = "150.00" if bound == "minimum_amount" else "50.00"
    path = tmp_path / f"{bound}.json"
    path.write_text(json.dumps(payload))
    profile = load_cost_profile(path, allow_synthetic=True)
    result = profile.quote(
        [CostTransaction("buy", date(2025, 1, 2), "ABC", "BUY", Decimal("100000"), 10)]
    )
    assert result.total == Decimal(expected)


def test_cost_profile_source_fingerprint_is_enforced(tmp_path: Path) -> None:
    source = tmp_path / "evidence.html"
    source.write_bytes(b"source evidence")
    provenance = {
        "sources": [
            {
                "source_id": "src",
                "status": "retrieved_bytes_archived",
                "file": "evidence.html",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        ]
    }
    (tmp_path / "provenance.json").write_text(json.dumps(provenance))
    profile = {
        "schema_version": "1.0",
        "version": "v1",
        "market": "NSE",
        "segment": "cash_delivery",
        "status": "partial",
        "synthetic": False,
        "provenance_manifest": "provenance.json",
        "required_components": [{"component": "x", "sides": ["BUY"]}],
        "rules": [
            {
                "component": "x",
                "category": "exchange",
                "basis": "notional",
                "aggregation": "per_fill",
                "sides": ["BUY"],
                "verification_status": "verified",
                "rounding": "half_up_paise",
                "effective_from": "2025-01-01",
                "effective_to": None,
                "source_id": "src",
                "rate": "0.001",
                "minimum_amount": None,
                "cap_amount": None,
                "gst_treatment": "not_taxable",
            }
        ],
        "assumptions": [],
    }
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile))
    assert load_cost_profile(path).rules[0].verification_status == "verified"
    source.write_bytes(b"changed")
    with pytest.raises(CostProfileError, match="fingerprint mismatch"):
        load_cost_profile(path)


def test_nse_recovery_candidate_is_standalone_and_does_not_authorize_evaluation(
    tmp_path: Path,
) -> None:
    profile = load_cost_profile(
        ROOT / "config/cost_profiles/zerodha_resident_individual_nse_delivery_hypothetical.json"
    )
    manifest = build_recovery_candidate(
        root=ROOT,
        reconciliation_path=ROOT / "reports/milestone_2h/bar_reconciliation.json",
        provider_path=ROOT
        / "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv",
        readiness_path=ROOT / "reports/milestone_2h/readiness.json",
        action_registry_path=ROOT / "reports/milestone_2h/corporate_action_evidence_registry.json",
        cost_profile=profile,
        output_dir=tmp_path / "candidate",
    )
    assert manifest["candidate_status"] == "complete"
    assert manifest["candidate_rows"] == len(RECOVERY_DATES)
    assert manifest["candidate_is_standalone"] is True
    assert manifest["automatic_merge_performed"] is False
    assert manifest["overall_evaluation_readiness"]["decision"] == "BLOCKED"
    assert manifest["overall_evaluation_readiness"]["real_data_backtest_authorized"] is False
    assert manifest["overall_evaluation_readiness"]["cost_coverage"][
        "uncovered_candidate_session_count"
    ] == len(RECOVERY_DATES)
    candidate_path = tmp_path / "candidate/candidate_missing_bars.csv"
    first_bytes = candidate_path.read_bytes()
    second = build_recovery_candidate(
        root=ROOT,
        reconciliation_path=ROOT / "reports/milestone_2h/bar_reconciliation.json",
        provider_path=ROOT
        / "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv",
        readiness_path=ROOT / "reports/milestone_2h/readiness.json",
        action_registry_path=ROOT / "reports/milestone_2h/corporate_action_evidence_registry.json",
        cost_profile=profile,
        output_dir=tmp_path / "candidate",
    )
    assert candidate_path.read_bytes() == first_bytes
    assert second["candidate_dataset_sha256"] == manifest["candidate_dataset_sha256"]


def test_recovery_candidate_refuses_different_existing_output(tmp_path: Path) -> None:
    profile = load_cost_profile(
        ROOT / "config/cost_profiles/zerodha_resident_individual_nse_delivery_hypothetical.json"
    )
    output = tmp_path / "candidate"
    output.mkdir()
    (output / "candidate_missing_bars.csv").write_text("user file\n")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build_recovery_candidate(
            root=ROOT,
            reconciliation_path=ROOT / "reports/milestone_2h/bar_reconciliation.json",
            provider_path=ROOT
            / "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv",
            readiness_path=ROOT / "reports/milestone_2h/readiness.json",
            action_registry_path=ROOT
            / "reports/milestone_2h/corporate_action_evidence_registry.json",
            cost_profile=profile,
            output_dir=output,
        )
