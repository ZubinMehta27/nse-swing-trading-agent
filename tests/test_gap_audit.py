import csv
import hashlib
import zipfile
from pathlib import Path

import pytest

from nse_swing_agent.gap_audit import audit_gaps
from nse_swing_agent.historical_data import DataValidationError

HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,"
    "OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol\n"
)
ROW = "2026-06-05,2026-06-05,CM,NSE,STK,2885,INE002A01018,RELIANCE,EQ,100,102,99,101,1234\n"
OTHER_ROW = "2026-06-08,2026-06-08,CM,NSE,STK,123,INE0000000001,OTHER,EQ,10,11,9,10,50\n"


def test_gap_audit_verified_source_row_is_provider_discrepancy(tmp_path: Path):
    observed = tmp_path / "observed.csv"
    observed.write_text(
        "symbol,session_date,open,high,low,close,volume\nRELIANCE,2026-06-04,100,102,99,101,1000\n",
        encoding="utf-8",
    )
    calendar = tmp_path / "calendar.csv"
    calendar.write_text(
        "session_date,status,source\n2026-06-05,SPECIAL_SESSION,NSE calendar circular\n",
        encoding="utf-8",
    )
    source = tmp_path / "bhav.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("bhav.csv", HEADER + ROW)
        archive.writestr("another_day.csv", HEADER + OTHER_ROW)
    output = tmp_path / "audit"
    summary = audit_gaps(observed, calendar, [source], output)
    assert summary["classifications"] == {"provider_source_discrepancy": 1}
    row = next(csv.DictReader((output / "gap_audit.csv").open(encoding="utf-8")))
    assert row["official_daily_report_available"] == "True"
    assert row["daily_report_validation_status"] == "valid"
    assert row["classification"] == "provider_source_discrepancy"
    assert row["evidence_classification"] == "confirmed_special_session_with_reliance_row"
    assert summary["source_files"][0]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert summary["automatic_fills"] == 0
    second_output = tmp_path / "audit-again"
    audit_gaps(observed, calendar, [source], second_output)
    for name in ("gap_audit.csv", "gap_audit.json", "gap_audit.md"):
        assert (output / name).read_bytes() == (second_output / name).read_bytes()


def test_gap_audit_rejects_ambiguous_source_headers(tmp_path: Path):
    observed = tmp_path / "observed.csv"
    observed.write_text(
        "symbol,session_date,open,high,low,close,volume\nRELIANCE,2026-06-04,100,102,99,101,1000\n",
        encoding="utf-8",
    )
    calendar = tmp_path / "calendar.csv"
    calendar.write_text(
        "session_date,status,source\n2026-06-05,SESSION,calendar\n", encoding="utf-8"
    )
    source = tmp_path / "bad.csv"
    source.write_text("date,symbol,open,close\n", encoding="utf-8")
    with pytest.raises(DataValidationError, match="ambiguous/unsupported"):
        audit_gaps(observed, calendar, [source], tmp_path / "out")
