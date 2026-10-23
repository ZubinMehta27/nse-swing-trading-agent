import json
from datetime import UTC, datetime
from pathlib import Path

from nse_swing_agent.corporate_actions import sha256_file
from nse_swing_agent.readiness_evidence import (
    build_milestone_2h,
    compare_bars,
    validate_action_evidence,
    validate_cost_evidence,
)


def test_action_registry_rejects_missing_dividend_fields_and_conflicting_rows():
    rows = [
        {
            "symbol": "RELIANCE",
            "ex_date": "2026-06-05",
            "type": "dividend",
            "cash_amount": 6,
            "verification_status": "unverified",
        },
        {
            "symbol": "RELIANCE",
            "ex_date": "2026-06-05",
            "type": "dividend",
            "cash_amount": 7,
            "verification_status": "unverified",
        },
    ]
    errors = validate_action_evidence(rows)
    assert any("conflicting" in error for error in errors)
    assert any("payment date or currency" in error for error in errors)
    assert any("duplicate same-exchange" in error for error in errors)


def test_exact_duplicate_action_record_is_not_silently_accepted():
    row = {
        "symbol": "RELIANCE",
        "isin": "INE002A01018",
        "exchange": "NSE",
        "ex_date": "2024-10-28",
        "type": "bonus",
        "ratio_num": 1,
        "ratio_den": 1,
        "verification_status": "unverified",
    }
    errors = validate_action_evidence([row, dict(row)])
    assert any("duplicate same-exchange source row" in error for error in errors)


def test_action_registry_blocks_incomplete_rights_and_demerger_terms():
    rows = [
        {
            "symbol": "X",
            "ex_date": "2020-01-01",
            "type": "rights",
            "verification_status": "unverified",
        },
        {
            "symbol": "X",
            "ex_date": "2020-01-02",
            "type": "demerger",
            "verification_status": "unverified",
        },
    ]
    errors = validate_action_evidence(rows)
    assert any("rights terms incomplete" in error for error in errors)
    assert any("demerger terms incomplete" in error for error in errors)


def test_cost_evidence_requires_all_components_and_rejects_overlap_or_missing_dates():
    components = [
        {
            "component": name,
            "status": "verified",
            "value": "0.01",
            "effective_from": "2025-01-01",
            "effective_to": "2025-12-31",
            "source_url": "https://example.test",
        }
        for name in (
            "brokerage",
            "stt",
            "exchange_transaction",
            "gst",
            "stamp_duty",
            "delivery_sale_dp",
            "sebi_turnover",
        )
    ]
    components.append(
        {
            "component": "stt",
            "status": "verified",
            "value": "0.01",
            "effective_from": "2025-06-01",
            "effective_to": None,
            "source_url": "https://example.test",
        }
    )
    errors = validate_cost_evidence(components)
    assert any("effective-date coverage is incomplete" in error for error in errors)
    assert any("overlapping effective intervals" in error for error in errors)
    assert validate_cost_evidence(components[:-1]) == []
    assumed = [dict(item) for item in components[:-1]]
    assumed[0]["unsupported_assumptions"] = ["minimum brokerage omitted"]
    assert any(
        "unsupported or unselected assumptions" in error
        for error in validate_cost_evidence(assumed)
    )


def test_bar_compare_keeps_missing_and_identity_mismatch_explicit():
    official = {
        "symbol": "RELIANCE",
        "isin": "INE002A01018",
        "open": "10",
        "high": "11",
        "low": "9",
        "close": "10",
        "volume": 100,
    }
    assert compare_bars(None, official)["comparison"] == "provider_bar_missing"
    provider = {
        "symbol": "RELIANCE",
        "isin": "WRONG",
        "open": "10",
        "high": "11",
        "low": "9",
        "close": "10",
        "volume": 100,
    }
    result = compare_bars(provider, official)
    assert result["comparison"] == "mismatch"
    assert result["identity_match"] is False
    provider["isin"] = official["isin"]
    provider.pop("isin")
    identity_check = compare_bars(provider, official)
    assert identity_check["comparison"] == "identity_unverified_isin_unavailable"
    assert identity_check["identity_match"] is None
    provider["isin"] = official["isin"]
    provider["close"] = "10.01"
    assert compare_bars(provider, official)["comparison"] == "mismatch"


def test_milestone_report_reconciles_eight_bars_fail_closed_and_preserves_sources(tmp_path):
    root = Path(__file__).resolve().parents[1]
    raw = next((root / "data/raw/nse").glob("tejhq_actions_RELIANCE_*.json"))
    source_files = [
        raw,
        *(
            root / "data/raw/nse" / name
            for name in (
                "cm07NOV2018bhav.csv.zip",
                "cm04NOV2021bhav.csv.zip",
                "cm24OCT2022bhav.csv.zip",
                "BhavCopy_NSE_CM_0_0_0_20241101_F_0000.csv.zip",
                "BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip",
                "BhavCopy_NSE_CM_0_0_0_20260615_F_0000.csv.zip",
                "BhavCopy_NSE_CM_0_0_0_20260616_F_0000.csv.zip",
                "BhavCopy_NSE_CM_0_0_0_20260622_F_0000.csv.zip",
            )
        ),
    ]
    before = {path: sha256_file(path) for path in source_files}
    output_dir = tmp_path / "milestone_2h"
    report = build_milestone_2h(
        root,
        datetime(2026, 10, 23, 12, tzinfo=UTC),
        output_dir=output_dir,
    )
    assert report["decision"] == "BLOCKED"
    assert report["real_data_backtest_ready"] is False
    assert report["profitability_evaluation_run"] is False
    assert report["missing_bars"]["count"] == 8
    assert report["missing_bars"]["provider_present_count"] == 0
    assert report["missing_bars"]["provider_missing_count"] == 8
    assert report["missing_bars"]["provider_value_mismatch_count"] == 0
    assert report["missing_bars"]["merged"] is False
    assert {path: sha256_file(path) for path in source_files} == before
    out = output_dir
    bars = json.loads((out / "bar_reconciliation.json").read_text())["bars"]
    assert len(bars) == 8
    assert all(item["comparison"] == "provider_bar_missing" for item in bars)
    assert all(item["official"]["isin"] == "INE002A01018" for item in bars)
    registry = json.loads((out / "corporate_action_evidence_registry.json").read_text())
    assert len(registry["events"]) == 25
    assert all(event["raw_file_sha256"] == before[raw] for event in registry["events"])
    assert report["cost_schedule"]["status"] == "INCOMPLETE_UNVERIFIED"
