"""Evidence-based comparison of local bars with an explicit calendar and NSE files."""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .historical_data import DataValidationError, load_historical_file

NSE_FIELDS = {
    "date": "TradDt",
    "symbol": "TckrSymb",
    "isin": "ISIN",
    "open": "OpnPric",
    "high": "HghPric",
    "low": "LwPric",
    "close": "ClsPric",
    "volume": "TtlTradgVol",
}
LEGACY_FIELDS = {
    "date": "TIMESTAMP",
    "symbol": "SYMBOL",
    "isin": "ISIN",
    "open": "OPEN",
    "high": "HIGH",
    "low": "LOW",
    "close": "CLOSE",
    "volume": "TOTTRDQTY",
}


@dataclass(frozen=True, slots=True)
class SourceRow:
    session_date: date
    symbol: str
    isin: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source: str


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_rows(path: Path) -> tuple[list[SourceRow], str]:
    """Read an official NSE CSV or CSV member of a ZIP, without extracting or changing it."""
    digest = _sha(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not names:
                raise DataValidationError(f"{path}: ZIP archive contains no CSV members")
            rows = []
            for name in names:
                with archive.open(name) as raw:
                    import io

                    text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
                    rows.extend(_parse_source_csv(text, path, name))
            return rows, digest
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return _parse_source_csv(handle, path, path.name), digest
    except OSError as exc:
        raise DataValidationError(f"cannot read source file {path}: {exc}") from exc


def read_official_bhavcopy(path: Path) -> tuple[list[SourceRow], str]:
    """Read validated NSE rows and return the unchanged source-file SHA-256."""
    return _source_rows(path)


def _parse_source_csv(handle, path: Path, member: str) -> list[SourceRow]:
    reader = csv.DictReader(handle)
    if reader.fieldnames is None:
        raise DataValidationError(f"{path}: source CSV has no header")
    if set(NSE_FIELDS.values()).issubset(reader.fieldnames):
        fields = NSE_FIELDS
    elif set(LEGACY_FIELDS.values()) - {"ISIN"} <= set(reader.fieldnames):
        fields = LEGACY_FIELDS
    else:
        raise DataValidationError(
            f"{path}: ambiguous/unsupported NSE schema; expected verified UDiFF fields "
            f"{list(NSE_FIELDS.values())} or legacy fields {list(LEGACY_FIELDS.values())}"
        )
    output = []
    for line, item in enumerate(reader, 2):
        # The verified UDiFF mapping is for cash-equity STK/EQ records only.
        if fields is NSE_FIELDS and (
            item.get("FinInstrmTp") != "STK" or item.get("SctySrs") != "EQ"
        ):
            continue
        if fields is LEGACY_FIELDS and item.get("SERIES") not in {None, "EQ"}:
            continue
        try:
            day = (
                date.fromisoformat(item[fields["date"]])
                if fields is NSE_FIELDS
                else datetime.strptime(item[fields["date"]], "%d-%b-%Y").date()
            )
            values = {
                name: Decimal(item[fields[name]]) for name in ("open", "high", "low", "close")
            }
            volume = int(item[fields["volume"]])
            if any(not value.is_finite() or value <= 0 for value in values.values()) or volume < 0:
                raise ValueError("nonpositive price or negative volume")
            if values["high"] < max(values["open"], values["close"], values["low"]) or values[
                "low"
            ] > min(values["open"], values["close"], values["high"]):
                raise ValueError("OHLC invariant violated")
            isin = item.get(fields["isin"], "").strip().upper()
            output.append(
                SourceRow(
                    day,
                    item[fields["symbol"]].strip().upper(),
                    isin,
                    values["open"],
                    values["high"],
                    values["low"],
                    values["close"],
                    volume,
                    f"{path.name}::{member}",
                )
            )
        except (KeyError, ValueError, InvalidOperation, TypeError) as exc:
            raise DataValidationError(
                f"{path}:{line}: malformed official source row: {exc}"
            ) from exc
    return output


def audit_gaps(
    observed_path: Path,
    calendar_path: Path,
    source_paths: list[Path],
    output_dir: Path,
    *,
    symbol: str = "RELIANCE",
    isin: str = "INE002A01018",
) -> dict:
    """Classify missing observed rows only where calendar and file evidence supports it."""
    observed = load_historical_file(observed_path)
    relevant = [r for r in observed if r.bar.symbol == symbol.upper()]
    dates = {r.session_date: r for r in relevant}
    calendar: dict[date, dict[str, str]] = {}
    with calendar_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not {"session_date", "status"}.issubset(reader.fieldnames):
            raise DataValidationError(
                "calendar must have session_date,status columns and explicit source provenance"
            )
        if "source" not in reader.fieldnames:
            raise DataValidationError("calendar must include source column")
        for line, row in enumerate(reader, 2):
            try:
                day = date.fromisoformat(row["session_date"])
                status = row["status"].strip().upper()
                if (
                    status
                    not in {
                        "SESSION",
                        "SPECIAL_SESSION",
                        "HOLIDAY",
                        "WEEKEND",
                        "WEEKEND_HOLIDAY",
                    }
                    or not row["source"].strip()
                ):
                    raise ValueError("unsupported calendar status or empty source")
                if day in calendar:
                    raise ValueError("duplicate calendar date")
                calendar[day] = row
            except ValueError as exc:
                raise DataValidationError(f"calendar row {line}: {exc}") from exc
    sources: dict[date, list[SourceRow]] = {}
    fingerprints = []
    for path in source_paths:
        rows, fingerprint = _source_rows(path)
        fingerprints.append(
            {
                "file": str(path),
                "sha256": fingerprint,
                "retrieved_at": None,
                "retrieval_status": "local file supplied; consult source provenance manifest",
                "validation_status": "valid",
            }
        )
        for row in rows:
            sources.setdefault(row.session_date, []).append(row)
    report = []
    for day, calendar_row in sorted(calendar.items()):
        calendar_status = calendar_row["status"].strip().upper()
        local = dates.get(day)
        source_matches = [
            r
            for r in sources.get(day, [])
            if r.symbol == symbol.upper() or (isin and r.isin == isin.upper())
        ]
        if calendar_status == "HOLIDAY":
            classification = "confirmed_exchange_holiday"
            reason = "explicit sourced calendar marks holiday"
        elif calendar_status in {"WEEKEND", "WEEKEND_HOLIDAY"}:
            classification = "confirmed_non_trading_date"
            reason = "explicit calendar marks weekend/non-trading date"
        elif len(source_matches) > 1:
            identities = {
                (x.symbol, x.isin, x.open, x.high, x.low, x.close, x.volume) for x in source_matches
            }
            if len(identities) != 1:
                raise DataValidationError(f"conflicting official source records for {symbol} {day}")
            source_matches = source_matches[:1]
            classification = (
                "provider_source_discrepancy" if local is None else "verified_bar_match"
            )
            reason = (
                "official symbol/ISIN bar found; duplicate identical rows"
                if local is None
                else "official source row matches observed session"
            )
        elif source_matches:
            row = source_matches[0]
            if row.isin and isin and row.isin != isin.upper():
                classification, reason = "unresolved", "symbol matched but ISIN differs"
            elif local is None:
                classification, reason = (
                    "provider_source_discrepancy",
                    "official RELIANCE bar exists; observed dataset is missing the session",
                )
            else:
                bar = local.bar
                equal = (bar.open, bar.high, bar.low, bar.close, bar.volume) == (
                    row.open,
                    row.high,
                    row.low,
                    row.close,
                    row.volume,
                )
                classification, reason = (
                    ("verified_bar_match", "official OHLCV agrees")
                    if equal
                    else ("provider_source_discrepancy", "official and observed OHLCV differ")
                )
        elif calendar_status in {"SESSION", "SPECIAL_SESSION"} and day in sources:
            classification, reason = (
                "confirmed_session_symbol_absent",
                "official daily file retrieved but no matching symbol/ISIN row",
            )
        else:
            classification, reason = "unresolved", "session/source evidence unavailable"
        if classification == "confirmed_exchange_holiday":
            evidence_classification = "confirmed_exchange_holiday"
        elif classification == "confirmed_non_trading_date":
            evidence_classification = "confirmed_non_trading_date"
        elif classification == "confirmed_session_symbol_absent":
            evidence_classification = "confirmed_trading_session_without_reliance_row"
        elif (
            classification == "provider_source_discrepancy" and calendar_status == "SPECIAL_SESSION"
        ):
            evidence_classification = "confirmed_special_session_with_reliance_row"
        elif classification == "provider_source_discrepancy":
            evidence_classification = "confirmed_trading_session_with_reliance_row"
        elif classification == "verified_bar_match":
            evidence_classification = "verified_official_bar_matches_observed"
        else:
            evidence_classification = "unresolved"
        report.append(
            {
                "session_date": day.isoformat(),
                "calendar_status": calendar_status,
                "calendar_description": calendar_row.get("description", ""),
                "calendar_source": calendar_row.get("source", ""),
                "calendar_source_url": calendar_row.get("source_url", ""),
                "symbol": symbol.upper(),
                "isin": isin,
                "observed_bar": local is not None,
                "official_daily_report_available": day in sources,
                "daily_report_validation_status": (
                    "valid"
                    if day in sources
                    else "not_requested_for_calendar_non_session"
                    if calendar_status in {"HOLIDAY", "WEEKEND", "WEEKEND_HOLIDAY"}
                    else "not_supplied"
                ),
                "classification": classification,
                "evidence_classification": evidence_classification,
                "reason": reason,
                "official_source": source_matches[0].source if source_matches else "",
                "official_isin": source_matches[0].isin if source_matches else "",
                "official_open": str(source_matches[0].open) if source_matches else "",
                "official_high": str(source_matches[0].high) if source_matches else "",
                "official_low": str(source_matches[0].low) if source_matches else "",
                "official_close": str(source_matches[0].close) if source_matches else "",
                "official_volume": source_matches[0].volume if source_matches else "",
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "gap_audit.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=list(report[0]) if report else ["session_date", "classification"]
        )
        writer.writeheader()
        writer.writerows(report)
    summary = {
        "schema_version": "1.0",
        "symbol": symbol.upper(),
        "isin": isin,
        "observed_file": str(observed_path),
        "observed_sha256": _sha(observed_path),
        "calendar_file": str(calendar_path),
        "calendar_sha256": _sha(calendar_path),
        "source_files": fingerprints,
        "classifications": {
            key: sum(row["classification"] == key for row in report)
            for key in sorted({row["classification"] for row in report})
        },
        "rows": len(report),
        "automatic_fills": 0,
    }
    (output_dir / "gap_audit.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "gap_audit.md").write_text(
        "# Historical gap audit\n\n"
        + "\n".join(f"- {key}: {value}" for key, value in summary["classifications"].items())
        + f"\n- Automatic fills: 0\n- Audit rows: {len(report)}\n",
        encoding="utf-8",
    )
    return summary
