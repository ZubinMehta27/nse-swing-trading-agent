"""Build a write-once, evidence-only reconciliation for NSE session 2025-10-21."""

from __future__ import annotations

import argparse
import csv
import io
import json
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from nse_swing_agent.gap_audit import read_official_bhavcopy
from nse_swing_agent.historical_data import DataValidationError, load_historical_file
from nse_swing_agent.session_calendar import sha256_file
from nse_swing_agent.source_reconciliation import classify_source_reconciliation

ROOT = Path(__file__).resolve().parents[1]
SESSION_DATE = date(2025, 10, 21)
ARCHIVE = Path("data/raw/nse/BhavCopy_NSE_CM_0_0_0_20251021_F_0000.csv.zip")
ARCHIVE_PROVENANCE = Path("data/raw/nse/BhavCopy_NSE_CM_0_0_0_20251021_F_0000.csv.provenance.json")
PROVIDER = Path(
    "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv"
)
PROVIDER_MANIFEST = Path(
    "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.json"
)
TEJHQ_RAW_SHA = "fd48f50f69338ee1f9b705bd889af7e7f0c8767751dfa0ab5126be6c7e502633"
P2_AUDIT = Path("reports/milestone_2p_v5/audit.json")
P2_SOURCE_MANIFEST = Path("data/reference/milestone_2p/source_archive_manifest_v1.json")
P2_SOURCE_ID = "NSE-CMTR-70319-2025"
SOURCE_URL = (
    "https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20251021_F_0000.csv.zip"
)
DEFAULT_OUTPUT = Path("reports/milestone_2q_v1")

REQUIRED_UDIff_COLUMNS = {
    "TradDt",
    "BizDt",
    "Sgmt",
    "Src",
    "FinInstrmTp",
    "FinInstrmId",
    "ISIN",
    "TckrSymb",
    "SctySrs",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
    "TtlTradgVol",
}


def _parse_zip(path: Path) -> tuple[list[str], list[dict[str, str]], str]:
    try:
        with ZipFile(path) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise DataValidationError(
                    f"expected one CSV member in official daily archive; found {len(csv_names)}"
                )
            member = csv_names[0]
            payload = archive.read(member)
    except (BadZipFile, OSError) as exc:
        raise DataValidationError(f"invalid official NSE ZIP archive: {exc}") from exc
    try:
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
        if not reader.fieldnames or not REQUIRED_UDIff_COLUMNS.issubset(reader.fieldnames):
            raise DataValidationError("official archive lacks required NSE CM-UDiFF fields")
        return reader.fieldnames, list(reader), member
    except UnicodeDecodeError as exc:
        raise DataValidationError(f"official CSV is not UTF-8 text: {exc}") from exc


def _validate_target_rows(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    target = [
        row
        for row in rows
        if row.get("TckrSymb", "").strip().upper() == "RELIANCE"
        and row.get("SctySrs", "").strip().upper() == "EQ"
        and row.get("ISIN", "").strip().upper() == "INE002A01018"
    ]
    identity_rows = [
        row
        for row in rows
        if row.get("TckrSymb", "").strip().upper() == "RELIANCE"
        and row.get("SctySrs", "").strip().upper() == "EQ"
    ]
    for row in target:
        if row["Sgmt"].strip().upper() != "CM" or row["Src"].strip().upper() != "NSE":
            raise DataValidationError("matching RELIANCE row is not an NSE cash-market record")
        if row["FinInstrmTp"].strip().upper() != "STK":
            raise DataValidationError("matching RELIANCE row is not a stock instrument")
        if row["TradDt"].strip() != SESSION_DATE.isoformat():
            raise DataValidationError("official bar trading date does not match archive date")
        if row["BizDt"].strip() != SESSION_DATE.isoformat():
            raise DataValidationError("official bar business date differs from trading date")
        try:
            prices = {
                field: Decimal(row[source].strip())
                for field, source in {
                    "open": "OpnPric",
                    "high": "HghPric",
                    "low": "LwPric",
                    "close": "ClsPric",
                }.items()
            }
            volume = int(row["TtlTradgVol"].strip())
        except (InvalidOperation, ValueError) as exc:
            raise DataValidationError(f"invalid OHLCV field in official bar: {exc}") from exc
        if any(not value.is_finite() or value <= 0 for value in prices.values()) or volume < 0:
            raise DataValidationError("official row has nonpositive prices or negative volume")
        if prices["high"] < max(prices.values()) or prices["low"] > min(prices.values()):
            raise DataValidationError("official row violates OHLC high/low consistency")
    return target, identity_rows


def build(root: Path = ROOT, output: Path = DEFAULT_OUTPUT) -> dict:
    root = root.resolve()
    output = output if output.is_absolute() else root / output
    output_files = [
        output / "reconciliation.json",
        output / "provenance.json",
        output / "readiness.md",
    ]
    existing = [path for path in output_files if path.exists()]
    if existing:
        raise FileExistsError("refusing to overwrite write-once Milestone 2Q outputs")

    archive_path = root / ARCHIVE
    if not archive_path.is_file():
        raise FileNotFoundError(f"official NSE archive is not available locally: {ARCHIVE}")
    archive_sha = sha256_file(archive_path)
    archive_provenance = json.loads((root / ARCHIVE_PROVENANCE).read_text(encoding="utf-8"))
    if (
        archive_provenance.get("sha256") != archive_sha
        or archive_provenance.get("url") != SOURCE_URL
        or archive_provenance.get("archive_filename") != ARCHIVE.name
        or archive_provenance.get("http_status") != 200
        or archive_provenance.get("byte_length") != archive_path.stat().st_size
    ):
        raise DataValidationError("official archive hash differs from its retrieval provenance")
    headers, raw_rows, member = _parse_zip(archive_path)
    target_raw, identity_raw = _validate_target_rows(raw_rows)

    # Reuse the repository's official-bhavcopy parser for schema, OHLCV and file validation.
    parsed_rows, parser_sha = read_official_bhavcopy(archive_path)
    if parser_sha != archive_sha:
        raise DataValidationError("source parser fingerprint differs from archived bytes")
    parsed_target = [
        row
        for row in parsed_rows
        if row.session_date == SESSION_DATE
        and row.symbol == "RELIANCE"
        and row.series == "EQ"
        and row.isin == "INE002A01018"
    ]
    if len(parsed_target) != len(target_raw):
        raise DataValidationError(
            "NSE parser result count differs from direct UDiFF row inspection"
        )

    provider_path = root / PROVIDER
    provider_manifest_path = root / PROVIDER_MANIFEST
    provider_manifest = json.loads(provider_manifest_path.read_text(encoding="utf-8"))
    raw_provider_path = root / Path(provider_manifest["raw_file"].replace("\\", "/"))
    if (
        sha256_file(raw_provider_path) != TEJHQ_RAW_SHA
        or provider_manifest.get("raw_file_sha256") != TEJHQ_RAW_SHA
    ):
        raise DataValidationError("preserved TejHQ raw response hash differs from the 2P manifest")
    raw_provider = json.loads(raw_provider_path.read_text(encoding="utf-8"))
    raw_provider_matches = [
        row
        for row in raw_provider.get("data", [])
        if str(row.get("date", ""))[:10] == SESSION_DATE.isoformat()
    ]
    provider_rows = load_historical_file(provider_path)
    canonical_matches = [
        item
        for item in provider_rows
        if item.session_date == SESSION_DATE and item.bar.symbol == "RELIANCE"
    ]
    canonical = [
        {
            "open": item.bar.open,
            "high": item.bar.high,
            "low": item.bar.low,
            "close": item.bar.close,
            "volume": item.bar.volume,
        }
        for item in canonical_matches
    ]
    official = [
        {
            "open": Decimal(row["OpnPric"]),
            "high": Decimal(row["HghPric"]),
            "low": Decimal(row["LwPric"]),
            "close": Decimal(row["ClsPric"]),
            "volume": int(row["TtlTradgVol"]),
        }
        for row in target_raw
    ]
    outcome = classify_source_reconciliation(official, canonical)

    p2_audit = json.loads((root / P2_AUDIT).read_text(encoding="utf-8"))
    if SESSION_DATE.isoformat() not in p2_audit["calendar_evidence"]["provider_omission_dates"]:
        raise DataValidationError("Milestone 2P does not record the expected provider omission")
    session_row = next(
        row
        for row in csv.DictReader(
            (root / "reports/milestone_2p_v5/date_by_date_audit.csv").open(encoding="utf-8")
        )
        if row["session_date"] == SESSION_DATE.isoformat()
    )
    if (
        session_row["status"] != "SPECIAL_SESSION"
        or session_row["source_sha256"]
        != "19b7d88003cb05eb8c6abdc8d1bfad5df821a17e4f9ae36f75e327a68a48d258"
    ):
        raise DataValidationError("Milestone 2P does not verify the 2025-10-21 CM session")
    p2_sources = json.loads((root / P2_SOURCE_MANIFEST).read_text(encoding="utf-8"))
    session_source = next(
        item for item in p2_sources["sources"] if item["source_id"] == P2_SOURCE_ID
    )
    if sha256_file(root / session_source["archive_path"]) != session_source["sha256"]:
        raise DataValidationError("archived CM Muhurat circular hash mismatch")

    matching = [
        {
            "session_date": SESSION_DATE.isoformat(),
            "exchange_segment": row["Sgmt"],
            "source": row["Src"],
            "instrument_type": row["FinInstrmTp"],
            "instrument_id": row["FinInstrmId"],
            "isin": row["ISIN"],
            "symbol": row["TckrSymb"],
            "series": row["SctySrs"],
            "instrument_name": row["FinInstrmNm"],
            "open": row["OpnPric"],
            "high": row["HghPric"],
            "low": row["LwPric"],
            "close": row["ClsPric"],
            "volume": int(row["TtlTradgVol"]),
            "traded_value": row["TtlTrfVal"],
            "trade_count": row["TtlNbOfTxsExctd"],
            "session_id": row["SsnId"],
            "trading_date": row["TradDt"],
            "business_date": row["BizDt"],
        }
        for row in target_raw
    ]
    result = {
        "schema_version": "milestone-2q-single-date-reconciliation-v1",
        "decision": "BLOCKED",
        "evaluation_run": False,
        "session_date": SESSION_DATE.isoformat(),
        "session_evidence": {
            "status": "verified_special_cash_market_session",
            "calendar_status": session_row["status"],
            "circular_source_id": P2_SOURCE_ID,
            "circular_title": "Muhurat Trading session on account of Diwali",
            "circular_publication_date": session_source["publication_or_trading_date"],
            "circular_url": session_source["url"],
            "circular_archive_path": session_source["archive_path"],
            "circular_sha256": session_source["sha256"],
        },
        "official_archive": {
            "status": "retrieved_and_validated",
            "url": SOURCE_URL,
            "archive_filename": ARCHIVE.name,
            "archive_path": ARCHIVE.as_posix(),
            "retrieved_at_utc": archive_provenance["retrieved_at_utc"],
            "http_status": archive_provenance["http_status"],
            "content_type": archive_provenance["content_type"],
            "content_length_header": archive_provenance["content_length_header"],
            "last_modified": archive_provenance["last_modified"],
            "etag": archive_provenance["etag"],
            "byte_length": archive_path.stat().st_size,
            "sha256": archive_sha,
            "zip_member": member,
            "schema_headers": headers,
            "parser_validation": "passed using nse_swing_agent.gap_audit.read_official_bhavcopy",
        },
        "row_reconciliation": {
            "archive_row_count": len(raw_rows),
            "reliance_eq_symbol_series_row_count": len(identity_raw),
            "exact_reliance_eq_isin_row_count": len(target_raw),
            "matching_rows": matching,
            "row_validation": "passed" if len(target_raw) == 1 else "not_single_unambiguous_row",
            "ohlc_valid": len(target_raw) == 1,
            "canonical_row_count": len(canonical_matches),
            "canonical_dataset_path": PROVIDER.as_posix(),
            "canonical_dataset_sha256": sha256_file(provider_path),
            "canonical_row_status": (
                "absent" if not canonical_matches else "present; compare in source artifact"
            ),
            "canonical_data_modified": False,
            "reconciliation_outcome": outcome,
            "official_values_compared_to_canonical": bool(canonical_matches),
            "field_mapping": {
                "date": "TradDt",
                "symbol": "TckrSymb",
                "series": "SctySrs",
                "isin": "ISIN",
                "open": "OpnPric",
                "high": "HghPric",
                "low": "LwPric",
                "close": "ClsPric",
                "volume": "TtlTradgVol",
            },
        },
        "raw_provider": {
            "path": provider_manifest["raw_file"].replace("\\", "/"),
            "sha256": TEJHQ_RAW_SHA,
            "adjustment_policy": "raw_unadjusted",
            "row_exists_for_session": bool(canonical_matches),
            "raw_response_rows_for_session": len(raw_provider_matches),
        },
        "candidate_data": {
            "candidate_created": False,
            "existing_eight_candidate_bars_unchanged": True,
            "merge_performed": False,
        },
        "readiness_gates": {
            "calendar_and_bar_coverage": "BLOCKED",
            "corporate_actions": "BLOCKED",
            "historical_costs": "BLOCKED",
            "instrument_universe": "BLOCKED",
        },
    }
    return result


def write_report(root: Path, output: Path, result: dict) -> None:
    output = output if output.is_absolute() else root / output
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty evidence directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    result["generated_at_utc"] = datetime.now(UTC).isoformat()
    with (output / "reconciliation.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    provenance = {
        "schema_version": "nse-single-date-source-provenance-v1",
        "retrieval_provider": "National Stock Exchange of India Limited official archives",
        "retrieval_url": SOURCE_URL,
        "retrieved_at_utc": result["official_archive"]["retrieved_at_utc"],
        "local_archive_path": result["official_archive"]["archive_path"],
        "sha256": result["official_archive"]["sha256"],
        "byte_length": result["official_archive"]["byte_length"],
        "http_status": result["official_archive"]["http_status"],
        "content_type": result["official_archive"]["content_type"],
        "last_modified": result["official_archive"]["last_modified"],
        "etag": result["official_archive"]["etag"],
        "bytes_preserved_unchanged": True,
    }
    with (output / "provenance.json").open("x", encoding="utf-8") as handle:
        json.dump(provenance, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    row_count = result["row_reconciliation"]["exact_reliance_eq_isin_row_count"]
    if row_count == 1:
        bar = result["row_reconciliation"]["matching_rows"][0]
        bar_text = (
            f"OHLCV: {bar['open']} / {bar['high']} / {bar['low']} / {bar['close']} / "
            f"{bar['volume']:,}."
        )
    else:
        bar_text = f"Exact identity matching row count: {row_count}; no row was selected."
    markdown = [
        "# Milestone 2Q — RELIANCE 2025-10-21 reconciliation",
        "",
        (
            "**Decision: BLOCKED. Evidence-only validation; no backtest or profitability "
            "evaluation was run.**"
        ),
        "",
        (
            "NSE’s official CM Muhurat circular verifies the session. The official CM-UDiFF "
            "final bhavcopy was retrieved and validated. The archive contains exactly one "
            "RELIANCE EQ / INE002A01018 row. " + bar_text
        ),
        "",
        (
            f"The existing TejHQ canonical dataset has "
            f"{result['row_reconciliation']['canonical_row_count']} rows for this symbol/date. "
            f"The source outcome is `{result['row_reconciliation']['reconciliation_outcome']}`. "
            "The official row is not merged or appended."
        ),
        "",
        (
            f"Archive: `{result['official_archive']['archive_path']}`; SHA-256 "
            f"`{result['official_archive']['sha256']}`; downloaded at "
            f"{result['official_archive']['retrieved_at_utc']} UTC."
        ),
        "",
        (
            "The canonical dataset, raw provider response and eight prior recovery candidates "
            "remain unchanged. Overall readiness remains blocked by broader session/bar "
            "coverage, corporate-action completeness, historical transaction-cost evidence, "
            "and instrument/universe identity coverage."
        ),
        "",
        (
            "See `reconciliation.json` for all identity fields, source schema, exact field "
            "mapping, validation status and provenance. `provenance.json` records retrieval "
            "metadata."
        ),
    ]
    with (output / "readiness.md").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(markdown) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build(args.root, args.output)
    write_report(args.root.resolve(), args.output, report)
    print(
        f"decision={report['decision']} official_rows="
        f"{report['row_reconciliation']['exact_reliance_eq_isin_row_count']} "
        f"canonical_rows={report['row_reconciliation']['canonical_row_count']} "
        f"outcome={report['row_reconciliation']['reconciliation_outcome']}"
    )


if __name__ == "__main__":
    main()
