"""Build a write-once session-calendar correction and RELIANCE data audit."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from nse_swing_agent.session_calendar import (
    apply_verified_exceptions,
    classify_calendar_observation,
    load_verified_exceptions,
    read_calendar,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_CALENDAR = Path("data/reference/nse_cm_calendar_2018_2024.csv")
REGISTRY = Path("data/reference/milestone_2o/session_calendar_exceptions_v1.json")
PROVENANCE = Path("data/reference/nse_cm_calendar_2018_2024.provenance.json")
PROVIDER = Path(
    "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv"
)
PROVIDER_MANIFEST = Path(
    "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.json"
)
PREVIOUS_AUDIT = Path("reports/milestone_2k_v4/audit.json")
CANDIDATE_MANIFEST = Path(
    "data/validation/recovery_candidates/milestone_2j_a_v2/recovery_manifest.json"
)
CANDIDATE_CSV = Path(
    "data/validation/recovery_candidates/milestone_2j_a_v2/candidate_missing_bars.csv"
)
OUT = Path("reports/milestone_2o_v2")
EFFECTIVE_DIRECTORY = Path("data/reference/milestone_2o")


def _sha(root: Path, relative: Path) -> str:
    return sha256_file(root / relative)


def _load_csv_dates(path: Path, column: str) -> dict[str, dict[str, str]]:
    rows = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = row[column]
            if key in rows:
                raise ValueError(f"duplicate {column} in {path}: {key}")
            rows[key] = row
    return rows


def build(root: Path = ROOT, output: Path = OUT) -> dict[str, Any]:
    root = root.resolve()
    output = output if output.is_absolute() else root / output
    version = output.name.rsplit("_", 1)[-1]
    effective_calendar_relative = EFFECTIVE_DIRECTORY / f"calendar_effective_{version}.csv"
    effective_provenance_relative = EFFECTIVE_DIRECTORY / (
        f"calendar_effective_{version}.provenance.json"
    )
    base_path = root / BASE_CALENDAR
    registry_path = root / REGISTRY
    base = read_calendar(base_path)
    exception_map = load_verified_exceptions(registry_path, base_path)
    effective = apply_verified_exceptions(base, exception_map)
    effective_path = root / effective_calendar_relative
    effective_provenance_path = root / effective_provenance_relative
    targets = [
        output / "date_by_date_calendar_audit.csv",
        output / "audit.json",
        output / "readiness.md",
        effective_path,
        effective_provenance_path,
    ]
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise FileExistsError("refusing to overwrite write-once outputs: " + ", ".join(existing))

    provider_path = root / PROVIDER
    provider_rows = _load_csv_dates(provider_path, "session_date")
    provider_manifest = json.loads((root / PROVIDER_MANIFEST).read_text(encoding="utf-8"))
    if provider_manifest.get("normalized_file") != str(PROVIDER).replace("/", "\\"):
        # Windows manifests use backslashes. Validate the expected stable file identity below too.
        if Path(provider_manifest.get("normalized_file", "")).name != PROVIDER.name:
            raise ValueError("provider manifest points at a different normalized file")
    if provider_manifest.get("row_count") != len(provider_rows):
        raise ValueError("provider manifest row count does not match normalized data")
    raw_provider_relative = Path(provider_manifest["raw_file"].replace("\\", "/"))
    raw_provider_path = root / raw_provider_relative
    if sha256_file(raw_provider_path) != provider_manifest.get("raw_file_sha256"):
        raise ValueError("provider raw response fingerprint differs from its manifest")
    candidate_manifest = json.loads((root / CANDIDATE_MANIFEST).read_text(encoding="utf-8"))
    candidate_sha = _sha(root, CANDIDATE_CSV)
    if candidate_sha != candidate_manifest.get("candidate_dataset_sha256"):
        raise ValueError("candidate data fingerprint differs from its manifest")
    candidate_rows = _load_csv_dates(root / CANDIDATE_CSV, "session_date")
    candidate_manifest_rows = {row["date"]: row for row in candidate_manifest["bars"]}
    old_audit = json.loads((root / PREVIOUS_AUDIT).read_text(encoding="utf-8"))
    old_candidate_rows = {row["date"]: row for row in old_audit["candidate_reconciliation"]["bars"]}
    if set(candidate_manifest_rows) != set(candidate_rows) or set(candidate_rows) != set(
        old_candidate_rows
    ):
        raise ValueError(
            "recovery candidate dates differ across candidate and Milestone 2K evidence"
        )

    date_rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for day, base_row in sorted(effective.items()):
        observed = day in provider_rows
        candidate = day in candidate_rows
        classification = classify_calendar_observation(
            base_row["status"],
            provider_bar_present=observed,
            candidate_bar_available=candidate,
        )
        counts[classification] += 1
        if base_row["status"] == "HOLIDAY":
            expectation_basis = "confirmed_by_nse_annual_holiday_master"
        elif base_row["status"] == "SPECIAL_SESSION":
            expectation_basis = (
                "verified_date_specific_exception_registry"
                if day in exception_map
                else "existing_special_session_circular_and_bhavcopy_provenance"
            )
        elif base_row["status"] in {"SESSION", "WEEKEND", "WEEKEND_HOLIDAY"}:
            expectation_basis = "inferred_from_nse_weekly_rule_and_annual_holiday_master"
        else:
            expectation_basis = "unresolved_calendar_expectation"
        candidate_record = candidate_manifest_rows.get(day)
        candidate_source_verified = False
        candidate_source_sha = None
        candidate_identity = None
        if candidate_record:
            actual_candidate = old_candidate_rows[day]
            source_path = root / candidate_record["source_path"]
            source_sha = sha256_file(source_path)
            candidate_source_sha = source_sha
            candidate_source_verified = (
                source_sha
                == candidate_record["source_sha256"]
                == candidate_record["expected_source_sha256"]
                and actual_candidate["source_sha256"] == source_sha
                and candidate_record["validation"] == "passed"
            )
            if not candidate_source_verified:
                raise ValueError(f"candidate source reconciliation failed for {day}")
            candidate_identity = {
                "symbol": candidate_record["symbol"],
                "isin": candidate_record["isin"],
                "exchange": candidate_record["exchange"],
                "series": candidate_record["series"],
            }
        date_rows.append(
            {
                "session_date": day,
                "source_calendar_status": base[day]["status"],
                "effective_calendar_status": base_row["status"],
                "calendar_expectation_basis": expectation_basis,
                "calendar_source": base_row.get("source"),
                "calendar_source_url": base_row.get("source_url"),
                "exception_id": base_row.get("correction_id"),
                "exception_source_url": base_row.get("correction_source_url"),
                "exception_source_sha256": base_row.get("correction_source_sha256"),
                "provider_bar_observed": observed,
                "provider_bar_identity_fields": (
                    "symbol only; canonical rows have no ISIN/series columns"
                ),
                "candidate_bar_available": candidate,
                "candidate_source_sha256": candidate_source_sha,
                "candidate_source_validated": candidate_source_verified if candidate else None,
                "candidate_instrument_identity": json.dumps(candidate_identity, sort_keys=True)
                if candidate_identity
                else "",
                "classification": classification,
                "candidate_merge_performed": False,
            }
        )

    candidate_audit = []
    for day, row in sorted(candidate_manifest_rows.items()):
        if not row["source_sha256"] == row["expected_source_sha256"]:
            raise ValueError(f"candidate manifest hash disagreement for {day}")
        source_sha = sha256_file(root / row["source_path"])
        prior = old_candidate_rows[day]
        if source_sha != row["source_sha256"] or source_sha != prior["source_sha256"]:
            raise ValueError(f"candidate source file no longer matches preserved evidence: {day}")
        candidate_audit.append(
            {
                "date": day,
                "symbol": row["symbol"],
                "isin": row["isin"],
                "exchange": row["exchange"],
                "series": row["series"],
                "source_url": row["source_url"],
                "source_filename": row["source_filename"],
                "source_sha256": source_sha,
                "source_retrieved_at_utc": row["source_retrieved_at_utc"],
                "source_timestamp_basis": row["source_timestamp_basis"],
                "ohlcv": row["ohlcv"],
                "validation": row["validation"],
                "matched_existing_milestone_2k_reconciliation": True,
                "merged": False,
            }
        )

    exceptions = [
        {
            **item,
            "source": {
                **item["source"],
                "verified_local_sha256": sha256_file(root / item["source"]["archive_path"]),
            },
        }
        for item in exception_map.values()
    ]
    calendar_provenance = json.loads((root / PROVENANCE).read_text(encoding="utf-8"))
    if calendar_provenance.get("range") != ["2018-01-01", "2024-12-31"]:
        raise ValueError("calendar provenance range differs from the expected audit period")
    provider_header = list(provider_rows[next(iter(provider_rows))]) if provider_rows else []
    identity = {
        "scope": "RELIANCE/NSE only",
        "provider": {
            "symbol_field_present": "symbol" in provider_header,
            "isin_field_present": "isin" in provider_header,
            "exchange_field_present": "exchange" in provider_header,
            "series_field_present": "series" in provider_header,
            "source_context": provider_manifest.get("endpoint"),
            "interpretation": (
                "TejHQ response is requested through its NSE symbol endpoint, but its "
                "normalized canonical rows do not carry ISIN or EQ series. Do not claim "
                "per-row identity validation from symbol alone."
            ),
        },
        "recovery_candidates": {
            "candidate_rows_have_symbol_isin_exchange_series": all(
                row["symbol"] == "RELIANCE"
                and row["isin"] == "INE002A01018"
                and row["exchange"] == "NSE"
                and row["series"] == "EQ"
                for row in candidate_audit
            ),
            "candidate_dates": len(candidate_audit),
            "merged": False,
        },
        "coverage_limit": (
            "RELIANCE-only evidence does not establish all-market or point-in-time-universe "
            "coverage."
        ),
    }
    unresolved = [
        row["session_date"]
        for row in date_rows
        if row["classification"]
        in {
            "provider_omission_on_inferred_ordinary_session",
            "provider_omission_on_verified_special_session",
            "unresolved_calendar_expectation",
            "provider_bar_on_confirmed_holiday_review",
            "provider_bar_on_inferred_weekend_review",
        }
    ]
    bar_quality_review_dates = [
        day for day in exception_map if day in provider_rows and day not in candidate_manifest_rows
    ]
    provider_actual_end = max(provider_rows)
    calendar_end = max(effective)
    unresolved_calendar_periods = []
    if provider_actual_end > calendar_end:
        unresolved_calendar_periods.append(
            {
                "start": (date.fromisoformat(calendar_end) + timedelta(days=1)).isoformat(),
                "end": provider_actual_end,
                "reason": (
                    "no full date-by-date official NSE session calendar is present after "
                    "the sourced 2018-2024 calendar"
                ),
            }
        )
    report = {
        "schema_version": "milestone-2o-session-calendar-data-readiness-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "decision": "BLOCKED",
        "real_data_backtest_run": False,
        "candidate_bars_merged": False,
        "scope": {
            "calendar_start": min(effective),
            "calendar_end": max(effective),
            "calendar_rows": len(effective),
            "provider_symbol": "RELIANCE",
            "provider_rows": len(provider_rows),
        },
        "inputs": {
            "base_calendar": {
                "path": BASE_CALENDAR.as_posix(),
                "sha256": _sha(root, BASE_CALENDAR),
            },
            "calendar_provenance": {
                "path": PROVENANCE.as_posix(),
                "sha256": _sha(root, PROVENANCE),
            },
            "exception_registry": {"path": REGISTRY.as_posix(), "sha256": _sha(root, REGISTRY)},
            "provider_dataset": {"path": PROVIDER.as_posix(), "sha256": _sha(root, PROVIDER)},
            "provider_manifest": {
                "path": PROVIDER_MANIFEST.as_posix(),
                "sha256": _sha(root, PROVIDER_MANIFEST),
            },
            "provider_raw_response": {
                "path": raw_provider_relative.as_posix(),
                "sha256": _sha(root, raw_provider_relative),
            },
            "candidate_dataset": {"path": CANDIDATE_CSV.as_posix(), "sha256": candidate_sha},
            "candidate_manifest": {
                "path": CANDIDATE_MANIFEST.as_posix(),
                "sha256": _sha(root, CANDIDATE_MANIFEST),
            },
            "prior_milestone_2k_audit": {
                "path": PREVIOUS_AUDIT.as_posix(),
                "sha256": _sha(root, PREVIOUS_AUDIT),
            },
        },
        "calendar_corrections": exceptions,
        "calendar_classification_counts": dict(sorted(counts.items())),
        "date_by_date_audit_path": (
            output.relative_to(root).as_posix() + "/date_by_date_calendar_audit.csv"
        ),
        "unresolved_or_review_dates": unresolved,
        "bar_quality_review_dates": bar_quality_review_dates,
        "unresolved_calendar_periods": unresolved_calendar_periods,
        "recovery_candidate_reconciliation": {
            "candidate_rows": len(candidate_audit),
            "all_sources_rehashed_and_matched": True,
            "all_rows_match_existing_milestone_2k_reconciliation": True,
            "merged": False,
            "bars": candidate_audit,
        },
        "instrument_identity": identity,
        "data_gaps": [
            "Provider canonical bars are symbol-only and lack per-row ISIN and EQ-series fields.",
            (
                "2024-01-20 is a verified live session, but the TejHQ OHLCV row was not "
                "compared with that day's official bhavcopy in this audit."
            ),
            (
                "Ordinary weekdays are expected by the exchange-week rule plus holiday "
                "master; this is calendar inference, not date-specific bhavcopy validation."
            ),
            "Calendar audit stops at 2024-12-31; no full 2025-2026 calendar is supplied.",
            "RELIANCE-only data does not establish full-market or point-in-time-universe coverage.",
        ],
        "independent_readiness_gates": {
            "corporate_action_completeness": "BLOCKED",
            "historical_transaction_cost_coverage": "BLOCKED",
            "instrument_universe_identity": "BLOCKED",
            "historical_session_and_bar_coverage": "BLOCKED",
        },
        "source_calendar_modified": False,
        "effective_calendar_path": effective_calendar_relative.as_posix(),
    }

    output.mkdir(parents=True, exist_ok=True)
    effective_path.parent.mkdir(parents=True, exist_ok=True)
    effective_provenance_path.parent.mkdir(parents=True, exist_ok=True)
    if any(path.exists() for path in targets):
        raise FileExistsError("refusing to overwrite existing Milestone 2O artifact")
    with effective_path.open("x", encoding="utf-8", newline="") as handle:
        fields = [
            "session_date",
            "status",
            "description",
            "source",
            "source_url",
            "calendar_basis",
            "correction_id",
            "correction_source_sha256",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for _, row in sorted(effective.items()):
            if "calendar_basis" not in row:
                row["calendar_basis"] = (
                    "confirmed_nse_annual_holiday_master"
                    if row["status"] == "HOLIDAY"
                    else "existing_date_specific_muhurat_circular_and_bhavcopy"
                    if row["status"] == "SPECIAL_SESSION"
                    else "inferred_from_nse_weekly_rule_and_annual_holiday_master"
                )
            writer.writerow({key: row.get(key, "") for key in fields})
    effective_provenance = {
        "schema_version": "nse-effective-calendar-v1",
        "source_calendar_path": BASE_CALENDAR.as_posix(),
        "source_calendar_sha256": _sha(root, BASE_CALENDAR),
        "exception_registry_path": REGISTRY.as_posix(),
        "exception_registry_sha256": _sha(root, REGISTRY),
        "exceptions_applied": [item["exception_id"] for item in exception_map.values()],
        "effective_calendar_sha256": sha256_file(effective_path),
        "original_calendar_modified": False,
        "generated_at_utc": report["generated_at_utc"],
    }
    effective_provenance_path.write_text(
        json.dumps(effective_provenance, indent=2) + "\n", encoding="utf-8"
    )
    audit_csv = output / "date_by_date_calendar_audit.csv"
    with audit_csv.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=date_rows[0].keys())
        writer.writeheader()
        writer.writerows(date_rows)
    report["outputs"] = {
        "effective_calendar_sha256": sha256_file(effective_path),
        "effective_calendar_provenance_sha256": sha256_file(effective_provenance_path),
        "date_by_date_audit_sha256": sha256_file(audit_csv),
    }
    (output / "audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    readiness = [
        "# Milestone 2O — Session calendar and data-readiness audit",
        "",
        "**Decision: BLOCKED. No real-data backtest or profitability evaluation was run.**",
        "",
        (
            "The original NSE calendar and historical dataset are unchanged. A separate "
            "verified exception registry promotes 2024-01-20 from the source calendar's "
            "WEEKEND label to SPECIAL_SESSION in a derived effective calendar. NSE "
            "Circular MSD59999, dated 2023-12-28, explicitly designates this a special "
            "live equity session. SHA-256: "
            "`614b965d1152ed636052e983a01206117ff6af224365348fa00b7165a6baa243`."
        ),
        "",
        (
            f"The RELIANCE TejHQ file has {len(provider_rows)} observed rows. Its "
            "canonical schema has symbol but no ISIN or series. The date-by-date CSV "
            "separates observed bars from calendar expectations. Ordinary sessions "
            "derive from the weekly rule and holiday master; missing bars are not "
            "classified as holidays."
        ),
        "",
        (
            f"All {len(candidate_audit)} candidate bars were re-hashed against their "
            "source records and Milestone 2K reconciliation. They remain in a separate "
            "candidate file and were not merged."
        ),
        "",
        (
            "The NSE daily calendar evidence ends 2024-12-31; provider history after that "
            "date lacks a full session calendar. Provider and candidate evidence cover "
            "RELIANCE only. Corporate-action completeness, transaction costs, instrument "
            "identity/universe coverage and session/bar coverage remain separate BLOCKED gates."
        ),
        "",
        (
            "The 2024-01-20 RELIANCE bar needs review: the session is verified, but the "
            "circular does not verify its OHLCV and this audit did not retrieve the day's "
            "bhavcopy. The normalized row also lacks ISIN/series identity."
        ),
        "",
        (
            "See `audit.json` for hashes and counts, "
            "`data/reference/milestone_2o/session_calendar_exceptions_v1.json` for the "
            f"registry, and `{effective_calendar_relative.as_posix()}` for the derived "
            "calendar."
        ),
    ]
    (output / "readiness.md").write_text("\n".join(readiness) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    report = build(args.root, args.output)
    print(
        f"decision={report['decision']} rows={report['scope']['calendar_rows']} "
        f"exceptions={len(report['calendar_corrections'])} "
        f"candidate_rows={report['recovery_candidate_reconciliation']['candidate_rows']}"
    )


if __name__ == "__main__":
    main()
