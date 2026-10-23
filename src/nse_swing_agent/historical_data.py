"""Strict local historical OHLCV ingestion and provenance-aware cache utilities."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import OHLCVBar

SCHEMA_VERSION = "1.0"
REQUIRED_COLUMNS = ("symbol", "session_date", "open", "high", "low", "close", "volume")
OPTIONAL_COLUMNS = ("adjustment_factor", "adjustment_policy")
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


class DataValidationError(ValueError):
    """Local source data does not meet the canonical schema or data rules."""


@dataclass(frozen=True, slots=True)
class HistoricalBar:
    bar: OHLCVBar
    session_date: date
    adjustment_factor: Decimal | None = None
    adjustment_policy: str = "raw_unadjusted"


@dataclass(frozen=True, slots=True)
class ImportSummary:
    source: str
    row_count: int
    symbol_count: int
    first_date: date
    last_date: date
    fingerprint: str
    cache_path: Path | None = None
    metadata_path: Path | None = None


class HistoricalDataProvider:
    """Interface for future local or authorized providers; no network implementation."""

    def load(self, path: Path) -> list[HistoricalBar]:
        raise NotImplementedError


class LocalFileProvider(HistoricalDataProvider):
    def load(self, path: Path) -> list[HistoricalBar]:
        return load_historical_file(path)


def _parse_date(raw: str | date, row_number: int) -> date:
    if isinstance(raw, datetime):
        if raw.tzinfo is not None and raw.utcoffset() is not None:
            return raw.astimezone(IST).date()
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise DataValidationError(
            f"row {row_number}: invalid session_date {raw!r}; expected YYYY-MM-DD"
        ) from exc
    if parsed.isoformat() != raw:
        raise DataValidationError(f"row {row_number}: session_date must use YYYY-MM-DD")
    return parsed


def _parse_decimal(raw: object, field: str, row_number: int) -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise DataValidationError(f"row {row_number}: invalid {field} {raw!r}") from exc
    if not value.is_finite():
        raise DataValidationError(f"row {row_number}: {field} must be finite")
    return value


def _to_record(row: dict[str, str | None], row_number: int) -> HistoricalBar:
    absent = [name for name in REQUIRED_COLUMNS if name not in row]
    if absent:
        raise DataValidationError(f"row {row_number}: missing required columns {', '.join(absent)}")
    missing = [
        name for name in REQUIRED_COLUMNS if row.get(name) is None or not str(row[name]).strip()
    ]
    if missing:
        raise DataValidationError(f"row {row_number}: missing values for {', '.join(missing)}")
    symbol = str(row["symbol"] or "").strip().upper()
    if not symbol:
        raise DataValidationError(f"row {row_number}: symbol cannot be empty")
    session_day = _parse_date(row["session_date"] or "", row_number)
    prices = {
        name: _parse_decimal(row[name] or "", name, row_number)
        for name in ("open", "high", "low", "close")
    }
    try:
        volume_text = str(row["volume"] or "").strip()
        volume = int(volume_text)
    except ValueError as exc:
        raise DataValidationError(
            f"row {row_number}: volume must be a nonnegative integer"
        ) from exc
    if str(volume) != volume_text or volume < 0:
        raise DataValidationError(f"row {row_number}: volume must be a nonnegative integer")
    factor_raw = row.get("adjustment_factor")
    factor = _parse_decimal(factor_raw, "adjustment_factor", row_number) if factor_raw else None
    if factor is not None and factor <= 0:
        raise DataValidationError(f"row {row_number}: adjustment_factor must be positive")
    policy = str(row.get("adjustment_policy") or "raw_unadjusted").strip()
    if not policy:
        raise DataValidationError(f"row {row_number}: adjustment_policy cannot be empty")
    timestamp = datetime.combine(session_day, time(15, 30), tzinfo=IST)
    try:
        bar = OHLCVBar(
            symbol,
            timestamp,
            prices["open"],
            prices["high"],
            prices["low"],
            prices["close"],
            volume,
        )
    except ValueError as exc:
        raise DataValidationError(f"row {row_number} ({symbol} {session_day}): {exc}") from exc
    return HistoricalBar(bar, session_day, factor, policy)


def load_historical_file(path: Path) -> list[HistoricalBar]:
    """Load canonical CSV or optional pyarrow Parquet; reject any malformed row."""
    if not path.is_file():
        raise DataValidationError(f"input file does not exist: {path}")
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise DataValidationError("CSV is empty or missing a header")
                missing = set(REQUIRED_COLUMNS) - set(reader.fieldnames)
                unknown = set(reader.fieldnames) - set(REQUIRED_COLUMNS) - set(OPTIONAL_COLUMNS)
                if missing or unknown:
                    parts = []
                    if missing:
                        parts.append(f"missing columns: {', '.join(sorted(missing))}")
                    if unknown:
                        parts.append(f"unknown columns: {', '.join(sorted(unknown))}")
                    raise DataValidationError("invalid CSV schema: " + "; ".join(parts))
                rows = []
                for i, row in enumerate(reader, start=2):
                    if None in row:
                        raise DataValidationError(
                            f"row {i}: extra values beyond declared CSV columns"
                        )
                    rows.append(_to_record(row, i))
        elif suffix in {".parquet", ".pq"}:
            try:
                import pyarrow.parquet as pq
            except ImportError as exc:
                raise DataValidationError(
                    "Parquet input requires optional dependency: pip install '.[data]'"
                ) from exc
            try:
                table = pq.read_table(path)
            except Exception as exc:
                raise DataValidationError(f"cannot read Parquet file {path}: {exc}") from exc
            names = table.column_names
            missing = set(REQUIRED_COLUMNS) - set(names)
            unknown = set(names) - set(REQUIRED_COLUMNS) - set(OPTIONAL_COLUMNS)
            if missing or unknown:
                raise DataValidationError(
                    f"invalid Parquet schema; missing={sorted(missing)}, unknown={sorted(unknown)}"
                )
            rows = [_to_record(row, i) for i, row in enumerate(table.to_pylist(), start=1)]
        else:
            raise DataValidationError("supported input formats are .csv, .parquet and .pq")
    except (OSError, csv.Error, UnicodeError) as exc:
        raise DataValidationError(f"cannot read {path}: {exc}") from exc
    if not rows:
        raise DataValidationError("input contains no data rows")
    seen: set[tuple[str, date]] = set()
    for record in rows:
        key = (record.bar.symbol, record.session_date)
        if key in seen:
            raise DataValidationError(f"duplicate symbol/session_date row: {key[0]} {key[1]}")
        seen.add(key)
    return sorted(rows, key=lambda item: (item.session_date, item.bar.symbol))


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_to_cache(path: Path, cache_dir: Path, *, source: str | None = None) -> ImportSummary:
    records = load_historical_file(path)
    fingerprint = _fingerprint(path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    basename = f"{path.stem}-{fingerprint[:12]}"
    cache_path = cache_dir / f"{basename}.csv"
    metadata_path = cache_dir / f"{basename}.json"
    with cache_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow((*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS))
        for item in records:
            bar = item.bar
            writer.writerow(
                (
                    bar.symbol,
                    item.session_date.isoformat(),
                    str(bar.open),
                    str(bar.high),
                    str(bar.low),
                    str(bar.close),
                    bar.volume,
                    "" if item.adjustment_factor is None else str(item.adjustment_factor),
                    item.adjustment_policy,
                )
            )
    payload = {
        "source": source or str(path),
        "input_fingerprint_sha256": fingerprint,
        "row_count": len(records),
        "symbols": sorted({item.bar.symbol for item in records}),
        "date_range": [records[0].session_date.isoformat(), records[-1].session_date.isoformat()],
        "imported_at_utc": datetime.now(UTC).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "adjustment_policies": sorted({item.adjustment_policy for item in records}),
        "raw_source_preserved": True,
    }
    metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return ImportSummary(
        str(path),
        len(records),
        len(payload["symbols"]),
        records[0].session_date,
        records[-1].session_date,
        fingerprint,
        cache_path,
        metadata_path,
    )
