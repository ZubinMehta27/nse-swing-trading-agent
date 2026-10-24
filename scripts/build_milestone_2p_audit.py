"""Build a write-once NSE calendar and independent RELIANCE bar audit."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from nse_swing_agent.calendar_evidence import (
    CalendarEvidenceError,
    calendar_status_for_date,
    compare_bar_values,
    inclusive_dates,
    validate_exception_entries,
    verify_legacy_nse_bhavcopy,
)
from nse_swing_agent.session_calendar import (
    apply_verified_exceptions,
    load_verified_exceptions,
    read_calendar,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("data/reference/milestone_2p/session_calendar_registry_v2.json")
SOURCE_MANIFEST = Path("data/reference/milestone_2p/source_archive_manifest_v1.json")
PROVIDER = Path(
    "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv"
)
PROVIDER_MANIFEST = Path(
    "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.json"
)
CANDIDATE = Path("data/validation/recovery_candidates/milestone_2j_a_v2/candidate_missing_bars.csv")
CANDIDATE_MANIFEST = Path(
    "data/validation/recovery_candidates/milestone_2j_a_v2/recovery_manifest.json"
)
PREVIOUS_AUDIT = Path("reports/milestone_2k_v4/audit.json")
BASE_CALENDAR = Path("data/reference/nse_cm_calendar_2018_2024.csv")
BASE_EXCEPTIONS = Path("data/reference/milestone_2o/session_calendar_exceptions_v1.json")
OFFICIAL_JAN20 = Path("data/reference/milestone_2p/source_archive/nse_cm_bhavcopy_2024_01_20.zip")
DEFAULT_OUTPUT = Path("reports/milestone_2p_v1")
FIRST_DAY = date(2018, 1, 1)
LAST_DAY = date(2026, 10, 22)


def _read_csv(path: Path, key: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line, row in enumerate(csv.DictReader(handle), 2):
            value = row.get(key, "")
            if value in result:
                raise CalendarEvidenceError(f"duplicate {key}={value!r} in {path} row {line}")
            result[value] = row
    return result


def _load_registry(root: Path) -> dict[str, Any]:
    registry = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    if registry.get("schema_version") != "nse-cm-session-calendar-registry-v2":
        raise CalendarEvidenceError("unsupported session calendar registry version")
    validate_exception_entries(registry.get("exceptions", []))

    manifest = json.loads((root / SOURCE_MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "nse-source-archive-manifest-v1":
        raise CalendarEvidenceError("unsupported source archive manifest")
    source_map: dict[str, dict[str, Any]] = {}
    for item in manifest.get("sources", []):
        archive = root / item["archive_path"]
        if not archive.is_file():
            raise CalendarEvidenceError(f"archived source bytes missing: {archive}")
        actual_hash = sha256_file(archive)
        if actual_hash != item.get("sha256"):
            raise CalendarEvidenceError(f"source hash mismatch: {archive}")
        if archive.stat().st_size != item.get("byte_length"):
            raise CalendarEvidenceError(f"source byte length mismatch: {archive}")
        if item.get("http_status") != 200 or not item.get("retrieved_at_utc"):
            raise CalendarEvidenceError(f"source retrieval provenance incomplete: {archive}")
        if item["source_id"] in source_map:
            raise CalendarEvidenceError(f"duplicate source ID {item['source_id']}")
        source_map[item["source_id"]] = item
    return {"registry": registry, "manifest": manifest, "source_map": source_map}


def _holiday_maps(
    registry: dict[str, Any],
) -> tuple[dict[date, str], dict[date, str], dict[date, str]]:
    holidays: dict[date, str] = {}
    weekend_holidays: dict[date, str] = {}
    for year, record in registry["annual_holidays"].items():
        if record["source_id"].startswith(("NSE-CD", "NSE-FO")) or "F&O" in record.get(
            "segment", ""
        ):
            raise CalendarEvidenceError("non-CM source cannot define cash-equity holidays")
        for day, _name in record["dates"]:
            parsed = date.fromisoformat(day)
            if parsed.year != int(year):
                raise CalendarEvidenceError(f"holiday {day} is stored under wrong year")
            holidays[parsed] = record["source_id"]
        for day, _name in record.get("weekend_holidays", []):
            parsed = date.fromisoformat(day)
            if parsed.year != int(year) or parsed.weekday() < 5:
                raise CalendarEvidenceError(f"invalid weekend holiday date {day}")
            weekend_holidays[parsed] = record["source_id"]
    for item in registry["exceptions"]:
        if item["status"] == "HOLIDAY":
            holidays[date.fromisoformat(item["date"])] = item["source_ids"][-1]
    specials = {
        date.fromisoformat(item["date"]): item["source_ids"][-1]
        for item in registry["exceptions"]
        if item["status"] == "SPECIAL_SESSION"
    }
    return holidays, weekend_holidays, specials


def _verify_jan20(root: Path, provider: dict[str, dict[str, str]]) -> dict[str, Any]:
    observed = provider.get("2024-01-20")
    if not observed:
        raise CalendarEvidenceError("TejHQ 2024-01-20 row is absent; cannot compare official bar")
    archive = root / OFFICIAL_JAN20
    official = verify_legacy_nse_bhavcopy(
        archive.read_bytes(),
        session_date=date(2024, 1, 20),
        symbol="RELIANCE",
        series="EQ",
        isin="INE002A01018",
    )
    comparison = compare_bar_values(official, observed)
    if not all(comparison.values()):
        raise CalendarEvidenceError(f"official and provider bars conflict: {comparison}")
    return {
        "session_date": "2024-01-20",
        "status": "independently_verified_ohlcv",
        "instrument": {"symbol": "RELIANCE", "series": "EQ", "isin": "INE002A01018"},
        "official_source_path": OFFICIAL_JAN20.as_posix(),
        "official_source_sha256": sha256_file(archive),
        "official_source_url": "https://archives.nseindia.com/content/historical/EQUITIES/2024/JAN/cm20JAN2024bhav.csv.zip",
        "archive_member": official["archive_member"],
        "official_ohlcv": {
            key: official[key] for key in ("open", "high", "low", "close", "volume")
        },
        "provider_ohlcv": {
            key: observed[key] for key in ("open", "high", "low", "close", "volume")
        },
        "field_matches": comparison,
        "all_fields_match": all(comparison.values()),
        "source_manifest_retrieved_at_utc": None,
    }


def build(root: Path = ROOT, output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    root = root.resolve()
    output = output if output.is_absolute() else root / output
    version = output.name.rsplit("_", 1)[-1]
    calendar_path = root / Path(
        f"data/reference/milestone_2p/calendar_2018_2026-10-22_{version}.csv"
    )
    calendar_provenance_path = calendar_path.with_suffix(".provenance.json")
    outputs = [
        output / "date_by_date_audit.csv",
        output / "audit.json",
        output / "readiness.md",
        calendar_path,
        calendar_provenance_path,
    ]
    existing = [str(item) for item in outputs if item.exists()]
    if existing:
        raise FileExistsError("refusing to overwrite write-once outputs: " + ", ".join(existing))

    provenance = _load_registry(root)
    registry = provenance["registry"]
    holidays, weekend_holidays, specials = _holiday_maps(registry)
    base_path = root / BASE_CALENDAR
    expected_base = registry["source_calendar_2018_2024"]
    if sha256_file(base_path) != expected_base["sha256"]:
        raise CalendarEvidenceError("immutable 2018-2024 calendar hash differs from registry")
    old_exceptions = load_verified_exceptions(root / BASE_EXCEPTIONS, base_path)
    base = apply_verified_exceptions(read_calendar(base_path), old_exceptions)
    provider = _read_csv(root / PROVIDER, "session_date")
    provider_manifest = json.loads((root / PROVIDER_MANIFEST).read_text(encoding="utf-8"))
    if provider_manifest.get("row_count") != len(provider):
        raise CalendarEvidenceError("provider manifest row count differs from canonical CSV")
    raw_path = root / Path(provider_manifest["raw_file"].replace("\\", "/"))
    if not raw_path.is_file() or sha256_file(raw_path) != provider_manifest.get("raw_file_sha256"):
        raise CalendarEvidenceError("provider raw response is missing or differs from manifest")
    candidates = _read_csv(root / CANDIDATE, "session_date")
    candidate_manifest = json.loads((root / CANDIDATE_MANIFEST).read_text(encoding="utf-8"))
    if sha256_file(root / CANDIDATE) != candidate_manifest.get("candidate_dataset_sha256"):
        raise CalendarEvidenceError("recovery candidate data differs from its manifest")
    previous_audit = json.loads((root / PREVIOUS_AUDIT).read_text(encoding="utf-8"))
    prior_candidates = {
        row["date"]: row for row in previous_audit["candidate_reconciliation"]["bars"]
    }
    manifest_candidates = {row["date"]: row for row in candidate_manifest["bars"]}
    if set(candidates) != set(manifest_candidates) or set(candidates) != set(prior_candidates):
        raise CalendarEvidenceError(
            "candidate dates differ across candidate and prior audit manifests"
        )
    candidate_source_audit = []
    for day, row in sorted(manifest_candidates.items()):
        source_path = root / Path(row["source_path"].replace("\\", "/"))
        source_sha = sha256_file(source_path) if source_path.is_file() else None
        if source_sha != row.get("expected_source_sha256") or source_sha != prior_candidates[
            day
        ].get("source_sha256"):
            raise CalendarEvidenceError(f"candidate source fingerprint mismatch for {day}")
        if (
            row.get("validation") != "passed"
            or row.get("isin") != "INE002A01018"
            or row.get("series") != "EQ"
            or row.get("exchange") != "NSE"
        ):
            raise CalendarEvidenceError(f"candidate identity or validation incomplete for {day}")
        output_row = candidates[day]
        for field in ("open", "high", "low", "close"):
            if Decimal(output_row[field]) != Decimal(row["ohlcv"][field]):
                raise CalendarEvidenceError(f"candidate {field} differs from manifest for {day}")
        if int(output_row["volume"]) != int(row["ohlcv"]["volume"]):
            raise CalendarEvidenceError(f"candidate volume differs from manifest for {day}")
        candidate_source_audit.append(
            {
                "date": day,
                "source_path": row["source_path"],
                "source_url": row["source_url"],
                "source_sha256": source_sha,
                "source_retrieved_at_utc": row.get("source_retrieved_at_utc"),
                "source_timestamp_basis": row.get("source_timestamp_basis"),
                "instrument": {
                    "symbol": row["symbol"],
                    "isin": row["isin"],
                    "exchange": row["exchange"],
                    "series": row["series"],
                },
                "validation": row["validation"],
                "matches_prior_milestone_2k": True,
                "merged": False,
            }
        )
    jan20 = _verify_jan20(root, provider)
    jan20["source_manifest_retrieved_at_utc"] = next(
        item["retrieved_at_utc"]
        for item in provenance["manifest"]["sources"]
        if item["archive_path"] == OFFICIAL_JAN20.as_posix()
    )

    calendar_rows: list[dict[str, Any]] = []
    for day in inclusive_dates(FIRST_DAY, LAST_DAY):
        key = day.isoformat()
        if key in base:
            old = base[key]
            status = old["status"]
            basis = old.get("calendar_basis", "existing_2018_2024_calendar_and_provenance")
            source_url = old.get("correction_source_url", old.get("source_url", ""))
            source_sha = old.get("correction_source_sha256", "")
            exception_id = old.get("correction_id", "")
        else:
            status, basis = calendar_status_for_date(
                day,
                holidays=holidays,
                weekend_holidays=weekend_holidays,
                special_sessions=specials,
                first_day=date(2025, 1, 1),
                last_day=LAST_DAY,
            )
            source_url = (
                "https://www.nseindia.com/resources/exchange-communication-holidays?apiversion=v2"
            )
            source_sha = provenance["source_map"]["NSE-MARKET-HOLIDAYS-RULES-PAGE"]["sha256"]
            exception_id = next(
                (item["exception_id"] for item in registry["exceptions"] if item["date"] == key),
                "",
            )
            if key in {
                item[0]
                for year_record in registry["annual_holidays"].values()
                for item in [
                    *year_record["dates"],
                    *year_record.get("weekend_holidays", []),
                ]
            }:
                source_url = next(
                    y["source_url"]
                    for y in registry["annual_holidays"].values()
                    if any(item[0] == key for item in [*y["dates"], *y.get("weekend_holidays", [])])
                )
                source_sha = next(
                    y["source_sha256"]
                    for y in registry["annual_holidays"].values()
                    if any(item[0] == key for item in [*y["dates"], *y.get("weekend_holidays", [])])
                )
            for exception in registry["exceptions"]:
                if exception["date"] == key:
                    source_id = exception["source_ids"][-1]
                    source = provenance["source_map"].get(source_id)
                    if source:
                        source_url = source["url"]
                        source_sha = source["sha256"]
        calendar_rows.append(
            {
                "session_date": key,
                "status": status,
                "expectation_basis": basis,
                "source_url": source_url,
                "source_sha256": source_sha,
                "exception_id": exception_id,
            }
        )

    verified_dates = {"2024-01-20"}
    classification_counts: Counter[str] = Counter()
    year_counts: dict[str, Counter[str]] = defaultdict(Counter)
    audit_rows: list[dict[str, Any]] = []
    unresolved: list[str] = []
    omissions: list[str] = []
    for row in calendar_rows:
        day = row["session_date"]
        status = row["status"]
        observed = day in provider
        candidate = day in candidates
        if status == "HOLIDAY":
            classification = (
                "provider_bar_on_confirmed_holiday_review"
                if observed
                else "confirmed_exchange_holiday"
            )
        elif status == "WEEKEND_HOLIDAY":
            classification = (
                "provider_bar_on_confirmed_weekend_holiday_review"
                if observed
                else "confirmed_exchange_holiday_on_weekend"
            )
        elif status == "WEEKEND":
            classification = (
                "provider_bar_on_inferred_weekend_review"
                if observed
                else "inferred_weekend_non_session_no_bar"
            )
        elif status == "SPECIAL_SESSION":
            if observed:
                classification = (
                    "independently_verified_special_session_bar"
                    if day in verified_dates
                    else "provider_bar_on_verified_special_session"
                )
            elif candidate:
                classification = "official_candidate_unmerged_confirms_session"
            else:
                classification = "provider_omission_on_verified_special_session"
        elif status == "SESSION":
            if observed:
                classification = "provider_bar_on_inferred_ordinary_session"
            elif candidate:
                classification = "official_candidate_unmerged_confirms_session"
            else:
                classification = "provider_omission_on_inferred_ordinary_session"
        else:
            classification = "unresolved_calendar_expectation"
        classification_counts[classification] += 1
        year_counts[day[:4]][status] += 1
        if classification.startswith("provider_omission"):
            omissions.append(day)
        if classification == "unresolved_calendar_expectation":
            unresolved.append(day)
        audit_rows.append(
            {
                **row,
                "provider_bar_observed": observed,
                "provider_identity": "RELIANCE symbol only; no canonical ISIN/series",
                "provider_raw_unadjusted": observed,
                "candidate_bar_available_unmerged": candidate,
                "classification": classification,
                "independent_ohlcv_verification": day in verified_dates,
            }
        )

    if not jan20["all_fields_match"]:
        raise CalendarEvidenceError("2024-01-20 independent bar verification failed")
    provider_verified_dates = sorted(day for day in verified_dates if day in provider)
    provider_unverified_dates = sorted(set(provider) - set(provider_verified_dates))
    source_fingerprints = {
        "registry": sha256_file(root / REGISTRY),
        "source_manifest": sha256_file(root / SOURCE_MANIFEST),
        "provider_dataset": sha256_file(root / PROVIDER),
        "provider_manifest": sha256_file(root / PROVIDER_MANIFEST),
        "provider_raw": sha256_file(raw_path),
        "candidate_dataset": sha256_file(root / CANDIDATE),
        "candidate_manifest": sha256_file(root / CANDIDATE_MANIFEST),
        "base_calendar": sha256_file(base_path),
    }
    report: dict[str, Any] = {
        "schema_version": "milestone-2p-independent-bar-calendar-audit-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "decision": "BLOCKED",
        "backtest_run": False,
        "candidate_bars_merged": False,
        "scope": {
            "start": FIRST_DAY.isoformat(),
            "end": LAST_DAY.isoformat(),
            "calendar_rows": len(calendar_rows),
            "symbol": "RELIANCE",
            "provider_rows": len(provider),
        },
        "jan_20_2024_bar_verification": jan20,
        "provider_bar_verification_summary": {
            "provider_rows": len(provider),
            "independently_verified_rows": len(provider_verified_dates),
            "not_independently_verified_rows": len(provider_unverified_dates),
            "verified_dates": provider_verified_dates,
            "unverified_dates": provider_unverified_dates,
            "verification_basis": (
                "Only dates compared with archived official NSE CM bhavcopy bytes count as "
                "independently verified."
            ),
        },
        "source_archives": [
            {key: value for key, value in item.items() if key != "content_review"}
            | {"content_review": item["content_review"]}
            for item in provenance["manifest"]["sources"]
        ],
        "source_fingerprints": source_fingerprints,
        "calendar_evidence": {
            "calendar_rule": registry["ordinary_session_rule"],
            "cash_market_sources_only": True,
            "f_and_o_sources_used": False,
            "year_status_counts": {
                year: dict(sorted(counts.items())) for year, counts in sorted(year_counts.items())
            },
            "classification_counts": dict(sorted(classification_counts.items())),
            "unresolved_calendar_dates": unresolved,
            "provider_omission_dates": omissions,
            "limitations": registry["limitations"],
        },
        "instrument_coverage": {
            "symbol": "RELIANCE",
            "provider_has_isin": False,
            "provider_has_exchange_field": False,
            "provider_has_series_field": False,
            "official_verified_bar_identity": {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "series": "EQ",
                "isin": "INE002A01018",
            },
            "scope_warning": (
                "RELIANCE-only evidence does not establish full-market or point-in-time-universe "
                "coverage."
            ),
        },
        "candidate_reconciliation": {
            "rows": len(candidates),
            "sha256": source_fingerprints["candidate_dataset"],
            "standalone": True,
            "merged": False,
            "dates": sorted(candidates),
            "all_source_hashes_match_both_manifests": True,
            "all_source_rows_match_candidate_data": True,
            "bars": candidate_source_audit,
        },
        "independent_readiness_gates": {
            "historical_session_and_bar_coverage": "BLOCKED",
            "corporate_action_completeness": "BLOCKED",
            "historical_transaction_cost_coverage": "BLOCKED",
            "instrument_universe_identity": "BLOCKED",
        },
        "effective_calendar_path": f"data/reference/milestone_2p/{calendar_path.name}",
    }

    output.mkdir(parents=True, exist_ok=True)
    calendar_path.parent.mkdir(parents=True, exist_ok=True)
    with calendar_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(calendar_rows[0]))
        writer.writeheader()
        writer.writerows(calendar_rows)
    calendar_hash = sha256_file(calendar_path)
    calendar_provenance = {
        "schema_version": "nse-derived-cm-calendar-v1",
        "calendar_path": f"data/reference/milestone_2p/{calendar_path.name}",
        "calendar_sha256": calendar_hash,
        "source_registry_path": REGISTRY.as_posix(),
        "source_registry_sha256": source_fingerprints["registry"],
        "source_manifest_path": SOURCE_MANIFEST.as_posix(),
        "source_manifest_sha256": source_fingerprints["source_manifest"],
        "source_calendar_2018_2024_unchanged": True,
        "candidate_bars_merged": False,
        "generated_at_utc": report["generated_at_utc"],
    }
    calendar_provenance_path.write_text(
        json.dumps(calendar_provenance, indent=2) + "\n", encoding="utf-8"
    )

    csv_path = output / "date_by_date_audit.csv"
    with csv_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audit_rows[0]))
        writer.writeheader()
        writer.writerows(audit_rows)
    report["outputs"] = {
        "date_by_date_csv": csv_path.relative_to(root).as_posix(),
        "date_by_date_csv_sha256": sha256_file(csv_path),
        "effective_calendar_sha256": calendar_hash,
        "effective_calendar_provenance_sha256": sha256_file(calendar_provenance_path),
    }
    (output / "audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    unresolved_text = (
        ", ".join(unresolved)
        if unresolved
        else (
            "None within the sourced date range; ordinary dates still follow the stated "
            "inference standard."
        )
    )
    readiness = [
        "# Milestone 2P — Independent bar verification and NSE calendar extension",
        "",
        "**Decision: BLOCKED. No strategy backtest or profitability evaluation was run.**",
        "",
        "## 2024-01-20 RELIANCE bar",
        "",
        (
            "The archived NSE CM bhavcopy contains exactly one RELIANCE EQ / INE002A01018 "
            "row. Its open, high, low, close and total traded quantity match the TejHQ row "
            "numerically at source precision. The source identifies symbol, series, ISIN and "
            "trading date. Session verification and OHLCV verification are recorded separately."
        ),
        "",
        (
            f"Official source SHA-256: `{jan20['official_source_sha256']}`. Raw provider and "
            "canonical files were not changed."
        ),
        "",
        (
            f"Across {len(provider)} TejHQ rows, {len(provider_verified_dates)} has "
            "independent official OHLCV verification in this audit; the remaining "
            f"{len(provider_unverified_dates)} are not independently source-checked here. "
            "The CSV records verification status date by date."
        ),
        "",
        "## Calendar scope and evidence standard",
        "",
        (
            "A derived daily calendar now covers 2018-01-01 through 2026-10-22. 2025 and "
            "2026 holiday evidence comes from NSE Capital Market circulars; special sessions "
            "override generic weekend or holiday classifications. Ordinary weekdays and "
            "weekends are classified using the official equities weekly rule plus the dated CM "
            "holiday schedule. This is a rule-based expectation, not individual bhavcopy proof "
            "for every day."
        ),
        "",
        f"Unresolved calendar dates: {unresolved_text}",
        "",
        (
            f"Provider omissions on expected sessions: {len(omissions)}; exact dates are "
            "listed in `audit.json` and `date_by_date_audit.csv`. A provider omission is not "
            "treated as an exchange closure."
        ),
        "",
        (
            "The 2025-02-01 Saturday live session and 2025-10-21 Muhurat session are "
            "separately evidenced. The 2026-01-15 Maharashtra municipal-election holiday is "
            "a CM-specific correction. F&O and settlement schedules were not used to define "
            "cash-equity sessions."
        ),
        "",
        "## Instrument and remaining readiness limits",
        "",
        (
            "The provider dataset remains RELIANCE-only and its canonical rows lack ISIN, "
            "exchange and series. The eight recovery candidates remain separate and unmerged. "
            "Full-market or point-in-time-universe coverage is not established."
        ),
        "",
        (
            "Four older candidate source timestamps remain local-file-mtime proxies. "
            "Candidate bytes and source fingerprints match existing manifests and the prior "
            "Milestone 2K audit, but those proxies are not verified retrieval times."
        ),
        "",
        (
            "Corporate-action completeness and verified historical transaction costs remain "
            "independent BLOCKED gates. Calendar and RELIANCE bar validation do not establish "
            "performance validity or profitability."
        ),
        "",
        (
            f"See `{output.relative_to(root).as_posix()}/audit.json`, "
            "`date_by_date_audit.csv`, the versioned calendar registry and source archive "
            f"manifest for evidence and fingerprints. The derived calendar is "
            f"`{report['effective_calendar_path']}`."
        ),
    ]
    (output / "readiness.md").write_text("\n".join(readiness) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build(args.root, args.output)
    print(
        f"decision={report['decision']} calendar_rows={report['scope']['calendar_rows']} "
        f"provider_rows={report['scope']['provider_rows']} "
        f"jan20_verified={report['jan_20_2024_bar_verification']['all_fields_match']} "
        f"provider_omissions={len(report['calendar_evidence']['provider_omission_dates'])}"
    )


if __name__ == "__main__":
    main()
