from __future__ import annotations

from pathlib import Path

import pytest

from nse_swing_agent.session_calendar import sha256_file
from nse_swing_agent.source_reconciliation import classify_source_reconciliation
from scripts.build_milestone_2q_report import build, write_report

ROOT = Path(__file__).resolve().parents[1]


def test_2025_10_21_official_row_resolves_provider_omission(tmp_path: Path) -> None:
    result = build(ROOT, tmp_path / "report")
    assert result["session_evidence"]["status"] == "verified_special_cash_market_session"
    rows = result["row_reconciliation"]
    assert rows["reliance_eq_symbol_series_row_count"] == 1
    assert rows["exact_reliance_eq_isin_row_count"] == 1
    assert rows["canonical_row_count"] == 0
    assert rows["canonical_row_status"] == "absent"
    assert result["raw_provider"]["raw_response_rows_for_session"] == 0
    assert rows["reconciliation_outcome"] == "official_bar_present_provider_row_missing"
    assert rows["canonical_data_modified"] is False
    assert result["readiness_gates"] == {
        "calendar_and_bar_coverage": "BLOCKED",
        "corporate_actions": "BLOCKED",
        "historical_costs": "BLOCKED",
        "instrument_universe": "BLOCKED",
    }
    assert rows["matching_rows"][0] == {
        "session_date": "2025-10-21",
        "exchange_segment": "CM",
        "source": "NSE",
        "instrument_type": "STK",
        "instrument_id": "2885",
        "isin": "INE002A01018",
        "symbol": "RELIANCE",
        "series": "EQ",
        "instrument_name": "RELIANCE INDUSTRIES LTD",
        "open": "1468.00",
        "high": "1474.00",
        "low": "1460.00",
        "close": "1465.20",
        "volume": 2_066_169,
        "traded_value": "3032861642.80",
        "trade_count": "86819",
        "session_id": "F1",
        "trading_date": "2025-10-21",
        "business_date": "2025-10-21",
    }


def test_multiple_conflicting_official_rows_are_not_arbitrarily_selected() -> None:
    row_a = {"open": "100", "high": "102", "low": "99", "close": "101", "volume": 10}
    row_b = {"open": "100", "high": "103", "low": "99", "close": "101", "volume": 10}
    assert classify_source_reconciliation([row_a, row_b], []) == "conflicting_official_rows"
    assert (
        classify_source_reconciliation([row_a, dict(row_a)], [])
        == "duplicate_identical_official_rows"
    )


def test_missing_official_security_row_is_distinct_from_missing_archive() -> None:
    assert classify_source_reconciliation([], []) == "no_matching_official_security_row"


def test_versioned_report_is_write_once_and_does_not_change_source_bytes(tmp_path: Path) -> None:
    output = tmp_path / "milestone_2q_vtest"
    result = build(ROOT, output)
    raw_path = ROOT / "data/raw/nse/BhavCopy_NSE_CM_0_0_0_20251021_F_0000.csv.zip"
    archive_hash = sha256_file(raw_path)
    write_report(ROOT, output, result)
    report_hash = sha256_file(output / "reconciliation.json")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_report(ROOT, output, result)
    assert sha256_file(output / "reconciliation.json") == report_hash
    assert sha256_file(raw_path) == archive_hash
