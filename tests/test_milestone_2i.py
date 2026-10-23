import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from nse_swing_agent.gap_audit import audit_gaps
from nse_swing_agent.historical_data import import_to_cache, load_historical_file

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data/validation/milestone_2i/reliance_provider_sample.csv"
CALENDAR = ROOT / "data/validation/milestone_2i/exchange_calendar_excerpt.csv"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_bounded_fixture_normalizes_without_changing_provider_inputs():
    manifest = json.loads((FIXTURE.parent / "provenance.json").read_text(encoding="utf-8"))
    source_hashes = {entry["path"]: entry["sha256"] for entry in manifest["source_files"]}
    before = {path: sha(ROOT / path.replace("\\", "/")) for path in source_hashes}
    assert before == source_hashes
    raw = ROOT / manifest["source_files"][0]["path"].replace("\\", "/")
    processed = ROOT / manifest["source_files"][1]["path"].replace("\\", "/")
    assert sha(raw) == source_hashes[manifest["source_files"][0]["path"]]
    assert sha(processed) == source_hashes[manifest["source_files"][1]["path"]]

    records = load_historical_file(FIXTURE)
    assert len(records) == 6
    assert [row.session_date.isoformat() for row in records] == [
        "2024-10-01",
        "2024-10-03",
        "2024-10-04",
        "2024-10-07",
        "2024-10-08",
        "2024-10-09",
    ]
    assert records[0].bar.open == Decimal("2961.3")
    assert records[0].bar.volume == 8215821
    assert all(row.adjustment_policy == "raw_unadjusted" for row in records)
    assert manifest["isin"] is None
    assert "not independently verified" in manifest["identity_status"]
    assert {path: sha(ROOT / path.replace("\\", "/")) for path in source_hashes} == before


def test_holiday_and_missing_session_are_distinct_and_never_filled(tmp_path: Path):
    summary = audit_gaps(FIXTURE, CALENDAR, [], tmp_path)
    rows = {
        row["session_date"]: row
        for row in csv.DictReader((tmp_path / "gap_audit.csv").open(encoding="utf-8"))
    }
    assert rows["2024-10-02"]["classification"] == "confirmed_exchange_holiday"
    assert rows["2024-10-10"]["calendar_status"] == "SESSION"
    assert rows["2024-10-10"]["classification"] == "unresolved"
    assert summary["automatic_fills"] == 0
    assert rows["2024-10-10"]["observed_bar"] == "False"


def test_repeated_cache_import_is_idempotent_and_does_not_rewrite_files(tmp_path: Path):
    cache = tmp_path / "cache"
    first = import_to_cache(FIXTURE, cache, source="Milestone 2I bounded provider fixture")
    before = {
        path: (sha(path), path.stat().st_mtime_ns)
        for path in (first.cache_path, first.metadata_path)
    }
    second = import_to_cache(FIXTURE, cache, source="Milestone 2I bounded provider fixture")
    after = {
        path: (sha(path), path.stat().st_mtime_ns)
        for path in (second.cache_path, second.metadata_path)
    }
    assert (first.cache_path, first.metadata_path) == (second.cache_path, second.metadata_path)
    assert before == after


def test_fixture_validation_does_not_override_real_data_readiness_gate():
    readiness = json.loads((ROOT / "reports/milestone_2h/readiness.json").read_text())
    assert readiness["decision"] == "BLOCKED"
    assert readiness["real_data_backtest_ready"] is False
    report = json.loads(
        (ROOT / "reports/milestone_2i/validation_report.json").read_text(encoding="utf-8")
    )
    assert report["real_data_backtest_run"] is False
    assert report["existing_readiness_gate"]["unchanged_by_fixture_validation"] is True
