"""Build an immutable six-session validation sample from cached TejHQ history.

The sample is provider-sourced and locally schema-validated. It is not NSE-bhavcopy
verified and has no independently verified ISIN. The only exchange-verified fact in
the accompanying calendar excerpt is the 2024-10-02 holiday entry.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from nse_swing_agent.historical_data import load_historical_file

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "validation" / "milestone_2i"
PROCESSED = (
    ROOT / "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv"
)
PROVENANCE = PROCESSED.with_suffix(".json")
CALENDAR = ROOT / "data/reference/nse_cm_calendar_2018_2024.csv"
CALENDAR_PROVENANCE = ROOT / "data/reference/nse_cm_calendar_2018_2024.provenance.json"
DATES = {"2024-10-01", "2024-10-03", "2024-10-04", "2024-10-07", "2024-10-08", "2024-10-09"}
CALENDAR_DATES = DATES | {"2024-10-02", "2024-10-10"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(f"refusing to overwrite different validation evidence: {path}")
        return
    path.write_bytes(payload)


def main() -> None:
    source_meta = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    raw_path = ROOT / source_meta["raw_file"].replace("\\", "/")
    if sha256(raw_path) != source_meta["raw_file_sha256"] or sha256(PROCESSED) != source_meta.get(
        "normalized_file_sha256", sha256(PROCESSED)
    ):
        raise ValueError("source fingerprint does not match the existing provider manifest")
    records = load_historical_file(PROCESSED)
    selected = [item for item in records if item.session_date.isoformat() in DATES]
    if {item.session_date.isoformat() for item in selected} != DATES:
        raise ValueError("source history does not contain all six requested fixture sessions")

    rows = [["symbol", "session_date", "open", "high", "low", "close", "volume"]]
    for item in selected:
        bar = item.bar
        rows.append(
            [
                bar.symbol,
                item.session_date.isoformat(),
                str(bar.open),
                str(bar.high),
                str(bar.low),
                str(bar.close),
                str(bar.volume),
            ]
        )
    import io

    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerows(rows)
    fixture_bytes = stream.getvalue().encode("utf-8")
    fixture_path = DATA / "reliance_provider_sample.csv"
    write_exclusive(fixture_path, fixture_bytes)

    with CALENDAR.open(encoding="utf-8-sig", newline="") as handle:
        calendar_rows = [
            row for row in csv.DictReader(handle) if row["session_date"] in CALENDAR_DATES
        ]
    if {row["session_date"] for row in calendar_rows} != CALENDAR_DATES:
        raise ValueError("sourced exchange calendar excerpt is incomplete")
    calendar_stream = io.StringIO(newline="")
    calendar_writer = csv.DictWriter(
        calendar_stream, fieldnames=calendar_rows[0].keys(), lineterminator="\n"
    )
    calendar_writer.writeheader()
    calendar_writer.writerows(calendar_rows)
    calendar_path = DATA / "exchange_calendar_excerpt.csv"
    calendar_bytes = calendar_stream.getvalue().encode("utf-8")
    write_exclusive(calendar_path, calendar_bytes)

    calendar_meta = json.loads(CALENDAR_PROVENANCE.read_text(encoding="utf-8"))
    manifest = {
        "milestone": "2I",
        "fixture_type": "bounded_provider_history_validation; not market-performance evidence",
        "schema_version": "1.0",
        "symbol": "RELIANCE",
        "isin": None,
        "identity_status": (
            "symbol comes from single-symbol TejHQ NSE endpoint; ISIN unavailable and not "
            "independently verified"
        ),
        "provider": source_meta["provider_name"],
        "endpoint": source_meta["endpoint"],
        "selected_dates": sorted(DATES),
        "actual_date_range": [min(DATES), max(DATES)],
        "adjustment_policy": (
            "raw_unadjusted; no adjustment applied; provider action completeness is not established"
        ),
        "source_files": [
            {
                "path": source_meta["raw_file"],
                "sha256": source_meta["raw_file_sha256"],
                "role": "unchanged original provider response",
            },
            {
                "path": source_meta["normalized_file"],
                "sha256": sha256(PROCESSED),
                "role": "existing canonical provider dataset",
            },
            {
                "path": "data/reference/nse_cm_calendar_2018_2024.csv",
                "sha256": sha256(CALENDAR),
                "role": "existing derived exchange calendar",
            },
            {
                "path": "data/reference/nse_cm_calendar_2018_2024.provenance.json",
                "sha256": sha256(CALENDAR_PROVENANCE),
                "role": "calendar source registry",
            },
        ],
        "calendar_excerpt_source": calendar_meta["sources"],
        "calendar_limitations": calendar_meta["limitations"],
        "normalization": (
            "Selected unchanged canonical values by explicit session dates; no fills, repairs, "
            "rounding or adjustment. Dates sorted ascending."
        ),
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "calendar_excerpt_sha256": hashlib.sha256(calendar_bytes).hexdigest(),
        "exchange_verification": (
            "OHLCV rows are TejHQ-provider sourced only, not independently compared with "
            "official bhavcopy; 2024-10-02 holiday is sourced from the existing NSE annual "
            "holiday-master record."
        ),
        "corporate_actions": (
            "No event is asserted for this fixture; accounting behaviors use separate labeled "
            "synthetic unit fixtures."
        ),
        "created_by": "scripts/build_m2i_fixture.py",
        "created_at_utc": datetime(2026, 10, 23, tzinfo=UTC).isoformat(),
    }
    manifest_path = DATA / "provenance.json"
    write_exclusive(
        manifest_path, (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    )
    load_historical_file(fixture_path)
    print(f"Wrote/confirmed {fixture_path.relative_to(ROOT)} ({len(selected)} rows)")


if __name__ == "__main__":
    main()
