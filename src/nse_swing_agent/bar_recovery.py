"""Controlled construction of non-merged candidate bars from retained NSE reports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from .cost_profiles import CostProfile
from .gap_audit import read_official_bhavcopy
from .historical_data import load_historical_file

RECOVERY_DATES = (
    "2018-11-07",
    "2021-11-04",
    "2022-10-24",
    "2024-11-01",
    "2026-06-05",
    "2026-06-15",
    "2026-06-16",
    "2026-06-22",
)
CANONICAL_COLUMNS = ("symbol", "session_date", "open", "high", "low", "close", "volume")


class RecoveryError(ValueError):
    """Candidate bar evidence is missing, conflicting or fails validation."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RecoveryError(f"JSON evidence must be an object: {path}")
    return payload


def build_recovery_candidate(
    *,
    root: Path,
    reconciliation_path: Path,
    provider_path: Path,
    readiness_path: Path,
    action_registry_path: Path,
    cost_profile: CostProfile,
    output_dir: Path,
    expected_dates: tuple[str, ...] = RECOVERY_DATES,
    symbol: str = "RELIANCE",
    isin: str = "INE002A01018",
) -> dict[str, Any]:
    """Validate sources and write an immutable, standalone candidate-only CSV/manifest.

    Existing source data are read only. Candidate files are created only for absent
    provider dates with one validated NSE source identity. The function never merges.
    """
    reconciliation = _json(reconciliation_path)
    comparisons = reconciliation.get("bars")
    if not isinstance(comparisons, list):
        raise RecoveryError("bar reconciliation must have a bars array")
    wanted = set(expected_dates)
    if len(wanted) != len(expected_dates) or not wanted:
        raise RecoveryError("expected recovery dates must be unique and non-empty")
    comparison_by_date = {str(row.get("date")): row for row in comparisons}
    if set(comparison_by_date).intersection(wanted) != wanted:
        raise RecoveryError(
            "Milestone 2H reconciliation does not cover exactly the requested dates"
        )
    provider_records = load_historical_file(provider_path)
    provider_by_date = {
        record.session_date.isoformat(): record
        for record in provider_records
        if record.bar.symbol == symbol.upper()
    }
    if len(provider_by_date) != sum(
        record.bar.symbol == symbol.upper() for record in provider_records
    ):
        raise RecoveryError("provider data contain duplicate symbol/date rows")

    bars: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    for iso_day in expected_dates:
        comparison = comparison_by_date[iso_day]
        source_rel = Path(comparison["source_path"])
        if source_rel.is_absolute() or ".." in source_rel.parts:
            raise RecoveryError(f"unsafe source path for {iso_day}: {source_rel}")
        source_path = root / source_rel
        if not source_path.is_file():
            raise RecoveryError(f"official source file missing for {iso_day}: {source_path}")
        source_hash = _sha(source_path)
        if source_hash != comparison.get("source_sha256"):
            raise RecoveryError(f"source fingerprint mismatch for {iso_day}: {source_path}")
        source_rows, parser_hash = read_official_bhavcopy(source_path)
        if parser_hash != source_hash:
            raise RecoveryError(f"source changed while reading {source_path}")
        matches = [
            row
            for row in source_rows
            if row.session_date == date.fromisoformat(iso_day)
            and row.symbol == symbol.upper()
            and row.isin == isin.upper()
        ]
        record: dict[str, Any] = {
            "date": iso_day,
            "source_path": source_rel.as_posix(),
            "source_filename": source_path.name,
            "source_sha256": source_hash,
            "source_row_id": comparison.get("source_row_id"),
            "source_url": comparison.get("source_url"),
            "source_retrieved_at_utc": comparison.get("retrieved_at_utc"),
            "source_timestamp_basis": comparison.get("source_timestamp_basis"),
            "symbol": symbol.upper(),
            "isin": isin.upper(),
            "exchange": "NSE",
            "series": "EQ",
            "provider_value": None,
            "provider_comparison": "no_provider_value",
            "validation": "failed",
            "disposition": "omitted",
        }
        if len(matches) != 1:
            reason = (
                f"{iso_day}: expected exactly one source row for "
                f"{symbol.upper()} / {isin.upper()}, found {len(matches)}"
            )
            record["error"] = reason
            problems.append(reason)
            bars.append(record)
            continue
        source_row = matches[0]
        official = comparison.get("official", {})
        if (
            source_row.open != Decimal(str(official.get("open")))
            or source_row.high != Decimal(str(official.get("high")))
            or source_row.low != Decimal(str(official.get("low")))
            or source_row.close != Decimal(str(official.get("close")))
            or source_row.volume != int(official.get("volume"))
        ):
            reason = f"{iso_day}: parsed source OHLCV conflicts with Milestone 2H reconciliation"
            record["error"] = reason
            problems.append(reason)
            bars.append(record)
            continue
        provider = provider_by_date.get(iso_day)
        if provider is not None:
            provider_values = (
                provider.bar.open,
                provider.bar.high,
                provider.bar.low,
                provider.bar.close,
                provider.bar.volume,
            )
            official_values = (
                source_row.open,
                source_row.high,
                source_row.low,
                source_row.close,
                source_row.volume,
            )
            record["provider_value"] = {
                "symbol": provider.bar.symbol,
                "open": str(provider.bar.open),
                "high": str(provider.bar.high),
                "low": str(provider.bar.low),
                "close": str(provider.bar.close),
                "volume": provider.bar.volume,
            }
            record["provider_comparison"] = (
                "provider_match" if provider_values == official_values else "provider_conflict"
            )
            record["error"] = f"{iso_day}: provider already has a row; not a missing-bar candidate"
            problems.append(record["error"])
            bars.append(record)
            continue
        record.update(
            {
                "validation": "passed",
                "disposition": "include_in_standalone_candidate_only",
                "ohlcv": {
                    "open": str(source_row.open),
                    "high": str(source_row.high),
                    "low": str(source_row.low),
                    "close": str(source_row.close),
                    "volume": source_row.volume,
                },
                "source_validation": [
                    "source SHA-256 matched the preserved Milestone 2H reconciliation",
                    "report date equals requested session date",
                    "parser selected NSE cash-market STK/EQ series rows "
                    "where the UDiFF schema was present",
                    "symbol and ISIN matched the required RELIANCE identity",
                    "OHLC invariants and nonnegative volume passed source parser validation",
                    "source OHLCV exactly matches the previously reviewed Milestone 2H row",
                ],
            }
        )
        rows.append(
            {
                "symbol": symbol.upper(),
                "session_date": iso_day,
                "open": str(source_row.open),
                "high": str(source_row.high),
                "low": str(source_row.low),
                "close": str(source_row.close),
                "volume": source_row.volume,
            }
        )
        bars.append(record)

    candidate_stream = io.StringIO(newline="")
    writer = csv.DictWriter(candidate_stream, fieldnames=CANONICAL_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    candidate_bytes = candidate_stream.getvalue().encode("utf-8")
    candidate_status = "complete" if len(rows) == len(wanted) else "partial" if rows else "blocked"

    readiness = _readiness(
        root,
        readiness_path,
        action_registry_path,
        provider_records,
        cost_profile,
        [date.fromisoformat(value) for value in expected_dates],
    )
    manifest = {
        "schema_version": "1.0",
        "milestone": "2J",
        "candidate_status": candidate_status,
        "candidate_rows": len(rows),
        "requested_dates": list(expected_dates),
        "candidate_dataset_path": "candidate_missing_bars.csv",
        "candidate_dataset_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "candidate_is_standalone": True,
        "source_data_modified": False,
        "automatic_merge_performed": False,
        "source_reconciliation": {
            "path": reconciliation_path.relative_to(root).as_posix(),
            "sha256": _sha(reconciliation_path),
        },
        "provider_dataset": {
            "path": provider_path.relative_to(root).as_posix(),
            "sha256": _sha(provider_path),
        },
        "instrument": {
            "symbol": symbol.upper(),
            "isin": isin.upper(),
            "exchange": "NSE",
            "series": "EQ",
        },
        "adjustment_policy": {
            "provider": "raw_unadjusted per preserved Milestone 2H import metadata",
            "nse_bhavcopy": "official exchange session OHLCV; "
            "no corporate-action adjustment applied by this builder",
            "compatibility": "price conventions are raw; do not merge until "
            "corporate-action continuity and all-date action coverage are resolved",
            "merge_authorized": False,
        },
        "recovery_plan": {
            "candidate_bars_only": True,
            "proposed_source": "NSE official cash-market bhavcopy files named per bar below",
            "required_migration_review": [
                "verify each source fingerprint and canonical record",
                "check candidate dates against action ex-dates and position/indicator policy",
                "retain TejHQ response and all existing manifests unchanged",
                "approve a separately versioned dataset migration before any use",
            ],
            "automatic_replacement_or_merge": False,
        },
        "bars": bars,
        "source_failures": problems,
        "overall_evaluation_readiness": readiness,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_once(output_dir / "candidate_missing_bars.csv", candidate_bytes)
    _write_once(output_dir / "recovery_manifest.json", manifest_bytes)
    return manifest


def _readiness(
    root: Path,
    readiness_path: Path,
    action_registry_path: Path,
    provider_records: list[Any],
    cost_profile: CostProfile,
    candidate_dates: list[date],
) -> dict[str, Any]:
    readiness = _json(readiness_path)
    action_registry = _json(action_registry_path)
    costs = []
    for record in provider_records:
        costs.append(record.session_date)
    # Check every provider session and every proposed candidate date.
    provider_sessions = set(costs)
    uncovered_provider = [
        day for day in sorted(provider_sessions) if cost_profile.coverage_errors(day)
    ]
    uncovered_candidates = [day for day in candidate_dates if cost_profile.coverage_errors(day)]
    corporate = readiness.get("corporate_actions", {})
    blockers = list(readiness.get("blockers", []))
    identities = {record.bar.symbol for record in provider_records}
    return {
        "decision": "BLOCKED",
        "real_data_backtest_authorized": False,
        "identity": {
            "candidate_bars_have_verified_isin": True,
            "full_history_provider_identity_verified": False,
            "reason": "TejHQ canonical OHLCV history is symbol-only; "
            "source-borrowed candidate identities do not verify the rest of history.",
            "provider_symbols": sorted(identities),
        },
        "corporate_actions": {
            "source_registry_path": action_registry_path.relative_to(root).as_posix(),
            "provider_action_rows": len(action_registry.get("events", [])),
            "complete_verified_coverage": False,
            "missing_dividend_terms": corporate.get("missing_dividend_payment_dates_or_currency"),
            "unsupported_event_types": corporate.get("blocked_event_types", []),
        },
        "cost_coverage": {
            "profile_version": cost_profile.version,
            "profile_status": cost_profile.status,
            "checked_provider_session_count": len(set(costs)),
            "uncovered_provider_session_count": len(uncovered_provider),
            "first_uncovered_date": (
                uncovered_provider[0].isoformat() if uncovered_provider else None
            ),
            "last_uncovered_date": (
                uncovered_provider[-1].isoformat() if uncovered_provider else None
            ),
            "checked_candidate_session_count": len(candidate_dates),
            "uncovered_candidate_session_count": len(uncovered_candidates),
            "candidate_session_dates_also_uncovered": bool(uncovered_candidates),
        },
        "existing_milestone_2h_blockers": blockers,
    }


def _write_once(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(f"refusing to overwrite candidate evidence: {path}")
        return
    path.write_bytes(payload)
