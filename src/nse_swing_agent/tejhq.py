"""TejHQ keyless daily NSE OHLCV retrieval for local research.

The endpoint is a data provider only. This module has no broker or order APIs.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import tempfile
import time as time_module
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .historical_data import (
    REQUIRED_COLUMNS,
    SCHEMA_VERSION,
    DataValidationError,
    HistoricalBar,
    load_historical_file,
)

BASE_URL = "https://api.tejhq.dev/v1/ohlcv/nse"
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9\-&]{0,29}$")
_TRANSIENT_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_MAX_RESPONSE_BYTES = 32 * 1024 * 1024
_ROW_FIELDS = {"date", "open", "high", "low", "close", "volume"}


class TejHQError(RuntimeError):
    """Provider transport or response contract failure."""


@dataclass(frozen=True, slots=True)
class FetchSummary:
    symbol: str
    requested_from: date
    requested_to: date
    actual_from: date
    actual_to: date
    row_count: int
    raw_path: Path
    normalized_path: Path
    provenance_path: Path
    raw_sha256: str
    validated_records: tuple[HistoricalBar, ...]


def _date_text(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise TejHQError(f"response {field} must be an ISO YYYY-MM-DD string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise TejHQError(f"response {field} has invalid date {value!r}") from exc
    if parsed.isoformat() != value:
        raise TejHQError(f"response {field} must use YYYY-MM-DD, got {value!r}")
    return parsed


def _decimal(value: object, field: str, row_number: int) -> Decimal:
    if isinstance(value, bool) or value is None or isinstance(value, (dict, list)):
        raise TejHQError(f"row {row_number}: {field} must be a finite number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TejHQError(f"row {row_number}: invalid {field} {value!r}") from exc
    if not result.is_finite():
        raise TejHQError(f"row {row_number}: {field} must be finite")
    return result


class TejHQClient:
    """Small standard-library client with bounded retries and explicit timeouts."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        retries: int = 2,
        opener: Callable[..., object] | None = None,
        sleep: Callable[[float], None] = time_module.sleep,
    ) -> None:
        if (
            not math.isfinite(timeout)
            or timeout <= 0
            or isinstance(retries, bool)
            or not isinstance(retries, int)
            or retries < 0
            or retries > 5
        ):
            raise ValueError("timeout must be positive and retries must be between 0 and 5")
        self.timeout = timeout
        self.retries = retries
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep

    def fetch_bytes(self, symbol: str, start: date, end: date) -> tuple[str, bytes]:
        symbol = symbol.strip().upper()
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError("symbol must match the NSE trading-symbol format")
        if start > end:
            raise ValueError("requested start date must be on or before end date")
        query = urllib.parse.urlencode({"from": start.isoformat(), "to": end.isoformat()})
        endpoint = f"{BASE_URL}/{urllib.parse.quote(symbol, safe='-&')}?{query}"
        request = urllib.request.Request(
            endpoint,
            headers={"Accept": "application/json", "User-Agent": "nse-swing-agent/0.1"},
        )
        for attempt in range(self.retries + 1):
            try:
                response = self._opener(request, timeout=self.timeout)
                with response as result:
                    status = getattr(result, "status", 200)
                    body = result.read(_MAX_RESPONSE_BYTES + 1)
                if status != 200:
                    raise TejHQError(f"TejHQ HTTP {status} for {endpoint}")
                if len(body) > _MAX_RESPONSE_BYTES:
                    raise TejHQError(f"TejHQ response exceeds {_MAX_RESPONSE_BYTES} bytes")
                return endpoint, body
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    raw_error = exc.read(16_384)
                    payload = json.loads(raw_error)
                    if isinstance(payload, dict):
                        detail = str(payload.get("error") or payload.get("message") or "")
                except (OSError, UnicodeError, json.JSONDecodeError):
                    pass
                message = f"TejHQ HTTP {exc.code} for {endpoint}"
                if detail:
                    message += f": {detail}"
                if exc.code not in _TRANSIENT_STATUSES or attempt == self.retries:
                    raise TejHQError(message) from exc
                self._sleep(min(0.25 * (2**attempt), 2.0))
            except (TimeoutError, urllib.error.URLError) as exc:
                if attempt == self.retries:
                    reason = getattr(exc, "reason", exc)
                    raise TejHQError(f"TejHQ request failed for {endpoint}: {reason}") from exc
                self._sleep(min(0.25 * (2**attempt), 2.0))
        raise AssertionError("bounded retry loop ended unexpectedly")


def _validate_response(body: bytes, symbol: str, start: date, end: date) -> list[dict[str, object]]:
    try:
        payload = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TejHQError(f"TejHQ response is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise TejHQError("TejHQ response must be an object containing a data array")
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        raise TejHQError("TejHQ response must contain a meta object")
    if str(meta.get("exchange", "")).upper() != "NSE":
        raise TejHQError("TejHQ response meta.exchange is missing or is not NSE")
    if str(meta.get("symbol", "")).upper() != symbol:
        raise TejHQError("TejHQ response symbol does not match requested symbol")
    if "count" in meta and (
        isinstance(meta["count"], bool) or meta["count"] != len(payload["data"])
    ):
        raise TejHQError("TejHQ response meta.count does not match data row count")
    rows: list[dict[str, object]] = []
    seen: set[date] = set()
    for index, item in enumerate(payload["data"], start=1):
        if not isinstance(item, dict):
            raise TejHQError(f"row {index}: expected an object")
        missing = _ROW_FIELDS - item.keys()
        if missing:
            raise TejHQError(f"row {index}: missing provider fields: {', '.join(sorted(missing))}")
        day = _date_text(item["date"], f"row {index} date")
        if not start <= day <= end:
            raise TejHQError(f"row {index}: date {day} lies outside requested range {start}..{end}")
        if day in seen:
            raise TejHQError(f"duplicate session date in TejHQ response: {day}")
        seen.add(day)
        for field in ("open", "high", "low", "close"):
            _decimal(item[field], field, index)
        volume = item["volume"]
        if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
            raise TejHQError(f"row {index}: volume must be a nonnegative integer")
        rows.append(item)
    if not rows:
        raise TejHQError("TejHQ returned no rows for the requested range")
    return sorted(rows, key=lambda row: _date_text(row["date"], "date"))


def _exclusive_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise TejHQError(f"refusing to overwrite existing output: {path}") from exc


def fetch_history(
    symbol: str,
    start: date,
    end: date,
    *,
    raw_dir: Path = Path("data/raw/nse"),
    processed_dir: Path = Path("data/processed"),
    client: TejHQClient | None = None,
) -> FetchSummary:
    """Fetch one explicit symbol/date range, preserve bytes, normalize and validate."""
    symbol = symbol.strip().upper()
    client = client or TejHQClient()
    endpoint, body = client.fetch_bytes(symbol, start, end)
    retrieved = datetime.now(UTC)
    digest = hashlib.sha256(body).hexdigest()
    stamp = retrieved.strftime("%Y%m%dT%H%M%SZ")
    stem = f"tejhq_{symbol}_{start.isoformat()}_{end.isoformat()}_{stamp}_{digest[:10]}"
    raw_path = raw_dir / f"{stem}.json"
    _exclusive_write(raw_path, body)

    rows = _validate_response(body, symbol, start, end)
    processed_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = processed_dir / f"{stem}.csv"
    normalized_buffer = io.StringIO(newline="")
    writer = csv.writer(normalized_buffer)
    writer.writerow((*REQUIRED_COLUMNS, "adjustment_factor", "adjustment_policy"))
    for row in rows:
        writer.writerow(
            (
                symbol,
                row["date"],
                str(_decimal(row["open"], "open", 0)),
                str(_decimal(row["high"], "high", 0)),
                str(_decimal(row["low"], "low", 0)),
                str(_decimal(row["close"], "close", 0)),
                row["volume"],
                "",
                "raw_unadjusted",
            )
        )
    normalized_bytes = normalized_buffer.getvalue().encode("utf-8")
    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".csv", prefix=".tejhq-validation-", dir=processed_dir, delete=False
    ) as temp_handle:
        temp_path = Path(temp_handle.name)
        temp_handle.write(normalized_bytes)
    try:
        records = load_historical_file(temp_path)
    except (DataValidationError, OSError) as exc:
        raise TejHQError(f"normalized TejHQ response failed canonical validation: {exc}") from exc
    finally:
        temp_path.unlink(missing_ok=True)
    _exclusive_write(normalized_path, normalized_bytes)
    actual_from = min(record.session_date for record in records)
    actual_to = max(record.session_date for record in records)
    provenance_path = processed_dir / f"{stem}.json"
    manifest = {
        "provider_name": "TejHQ keyless OHLCV API",
        "endpoint": endpoint,
        "exchange": "NSE",
        "symbol": symbol,
        "requested_date_range": [start.isoformat(), end.isoformat()],
        "actual_date_range": [actual_from.isoformat(), actual_to.isoformat()],
        "retrieved_at_utc": retrieved.isoformat(),
        "raw_file": str(raw_path),
        "raw_file_sha256": digest,
        "normalized_file": str(normalized_path),
        "schema_version": SCHEMA_VERSION,
        "row_count": len(records),
        "adjustment_status": "raw_unadjusted; endpoint is /v1/ohlcv, not /v1/adjusted",
        "normalization": {
            "field_mapping": {
                "date": "session_date",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            },
            "symbol": "requested NSE path symbol applied to all rows (single-symbol endpoint)",
            "ordering": "ascending session_date",
            "session_timestamp": "15:30 Asia/Kolkata, assigned by canonical loader",
            "adjustment_policy": "raw_unadjusted; no price adjustment applied",
            "provider_extra_fields": "preserved only in unchanged raw JSON",
        },
        "raw_source_preserved": True,
    }
    _exclusive_write(provenance_path, (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    return FetchSummary(
        symbol,
        start,
        end,
        actual_from,
        actual_to,
        len(records),
        raw_path,
        normalized_path,
        provenance_path,
        digest,
        tuple(records),
    )
