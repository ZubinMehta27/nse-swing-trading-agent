"""Validate the small Milestone 2I dataset; never executes the strategy/backtester."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from nse_swing_agent.gap_audit import audit_gaps
from nse_swing_agent.historical_data import load_historical_file

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "data/validation/milestone_2i"
OUTPUT_DIR = ROOT / "reports/milestone_2i"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    fixture = FIXTURE_DIR / "reliance_provider_sample.csv"
    calendar = FIXTURE_DIR / "exchange_calendar_excerpt.csv"
    provenance_path = FIXTURE_DIR / "provenance.json"
    manifest = json.loads(provenance_path.read_text(encoding="utf-8"))
    if sha256(fixture) != manifest["fixture_sha256"]:
        raise ValueError("fixture hash differs from immutable provenance manifest")
    if sha256(calendar) != manifest["calendar_excerpt_sha256"]:
        raise ValueError("calendar excerpt hash differs from immutable provenance manifest")
    records = load_historical_file(fixture)
    if len(records) != 6 or {row.bar.symbol for row in records} != {"RELIANCE"}:
        raise ValueError("fixture must contain exactly six RELIANCE rows")

    with tempfile.TemporaryDirectory(prefix="m2i-gap-audit-") as temporary:
        gap = audit_gaps(fixture, calendar, [], Path(temporary))
        gap_rows = json.loads((Path(temporary) / "gap_audit.json").read_text(encoding="utf-8"))
        import csv

        with (Path(temporary) / "gap_audit.csv").open(encoding="utf-8", newline="") as handle:
            classifications = list(csv.DictReader(handle))
    blocker = json.loads((ROOT / "reports/milestone_2h/readiness.json").read_text(encoding="utf-8"))
    report = {
        "milestone": "2I",
        "validation_only": True,
        "profitability_evaluation_run": False,
        "real_data_backtest_run": False,
        "fixture": {
            "path": fixture.relative_to(ROOT).as_posix(),
            "sha256": sha256(fixture),
            "rows": len(records),
            "symbol": "RELIANCE",
            "date_range": [
                records[0].session_date.isoformat(),
                records[-1].session_date.isoformat(),
            ],
            "schema_validation": "passed using existing canonical loader",
            "source_status": (
                "TejHQ provider-sourced; not independently bhavcopy-verified; ISIN unavailable"
            ),
            "adjustment_status": manifest["adjustment_policy"],
        },
        "exchange_calendar": {
            "excerpt_path": calendar.relative_to(ROOT).as_posix(),
            "sha256": sha256(calendar),
            "audit_classifications": {
                row["session_date"]: row["classification"] for row in classifications
            },
            "automatic_fills": gap["automatic_fills"],
            "2024-10-02": "holiday from NSE 2024 holiday-master evidence",
            "2024-10-10": (
                "expected session absent from six-row fixture; correctly unresolved, "
                "not synthesized"
            ),
            "limitation": (
                "Calendar SESSION dates derive from NSE weekly trading rule and holiday master; "
                "no daily bhavcopy supplied for sample OHLCV dates."
            ),
        },
        "evidence_categories": {
            "independently_verified_historical_fact": (
                "2024-10-02 exchange holiday, from retained NSE annual holiday-master response"
            ),
            "provider_sourced_not_independently_verified": (
                "six RELIANCE OHLCV observations from cached TejHQ daily response"
            ),
            "synthetic_accounting_tests": (
                "existing and extended pytest fixtures only; never presented as historical events"
            ),
            "unverified_assumptions": [
                "ISIN for sample rows",
                "completeness of corporate-action history",
                "complete historical transaction-cost profile",
            ],
        },
        "accounting_validation": {
            "fixtures": "synthetic unit data in tests/test_corporate_actions.py",
            "production_changes": (
                "none to event terms or strategy; existing split/bonus/dividend ledger is tested"
            ),
            "fractional_entitlements": "blocked pending explicit cash-in-lieu terms",
            "unsupported_events": ["rights", "demerger", "merger", "buyback", "delisting"],
            "future_action_leakage": (
                "event is applied only at its ex-date; unit test asserts earlier pending "
                "decision remains earlier"
            ),
        },
        "cost_model": (
            "INCOMPLETE_UNVERIFIED; no full historical cost-inclusive profile is authorized"
        ),
        "existing_readiness_gate": {
            "source": "reports/milestone_2h/readiness.json",
            "decision": blocker["decision"],
            "real_data_backtest_ready": blocker["real_data_backtest_ready"],
            "unchanged_by_fixture_validation": True,
        },
        "provenance_path": provenance_path.relative_to(ROOT).as_posix(),
        "provenance_sha256": sha256(provenance_path),
        "gap_audit_schema_version": gap_rows["schema_version"],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "validation_report.json"
    md_path = OUTPUT_DIR / "validation_report.md"
    write_report(json_path, (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode())
    markdown = """# Milestone 2I — Bounded Validation Report

**Decision: validation fixture passes canonical data validation; real-data backtest remains
blocked.** No strategy backtest or profitability evaluation was run.

## Evidence status

- Six OHLCV rows are selected without transformation from the cached TejHQ response. They have not
  been independently compared with official daily bhavcopy files; the provider response has no
  ISIN field.
- 2024-10-02 is explicitly marked as the NSE cash-market holiday in the retained annual
  holiday-master response. The selected bars bracket that date and resume on 2024-10-03.
- 2024-10-10 is an expected session in the excerpt but is absent from this intentionally bounded
  sample. Audit classifies it as unresolved; it does not impute a bar. No automatic fills are
  performed.
- Synthetic accounting unit tests are not historical corporate-action evidence. The six-row
  fixture contains no asserted action.

## Validation and accounting

The canonical loader validates the fixture’s required columns, ISO session dates, Decimal OHLC
values, OHLC invariants, integer nonnegative volume, duplicates and deterministic date ordering.
The reusable gap audit records holiday versus absent expected session separately.

Split and bonus quantity rebasing, per-share and aggregate cost basis, protective level
adjustment, dividend receivables/payment, fractional-share blocking, unsupported event blocking,
duplicate rejection and event-date timing use explicitly synthetic tests.

## Cost specification

See `cost_model_specification.md`. The historical profile is incomplete and unverified; the
cost-inclusive readiness gate stays closed.

## Readiness

The existing Milestone 2H readiness report remains authoritative and blocked. This fixture report
does not modify or override it. Provider OHLCV lacks independently verified instrument identity,
the sample is not sufficient for the configured strategy warm-up, corporate-action coverage is
not complete, and historical statutory, exchange, broker and DP charges lack a fully verified
date-effective schedule.

See `validation_report.json` and `data/validation/milestone_2i/provenance.json` for hashes, input
references and exact classifications.
"""
    write_report(md_path, markdown.encode())
    print(f"Validated {len(records)} canonical fixture rows; report: {json_path.relative_to(ROOT)}")


def write_immutable(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"refusing to overwrite existing evidence: {path}")
        return
    path.write_bytes(content)


def write_report(path: Path, content: bytes) -> None:
    """Refresh only this milestone's generated report; input evidence is never changed."""
    if path.exists() and path.parent != OUTPUT_DIR:
        raise FileExistsError(f"refusing to overwrite evidence outside Milestone 2I: {path}")
    path.write_bytes(content)


if __name__ == "__main__":
    main()
