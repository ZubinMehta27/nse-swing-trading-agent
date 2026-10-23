from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

NSE_CALENDAR_URL = "https://www.nseindia.com/resources/exchange-communication-holidays"
NSE_WEEK_RULE_URL = "https://www.nseindia.com/resources/exchange-communication-holidays"
SPECIAL = {
    "2018-11-07": (
        "Diwali Laxmi Pujan / Muhurat",
        "https://nsearchives.nseindia.com/content/circulars/CMTR36475.pdf",
        "NSE_CMTR36475_2018_holidays.pdf",
        "cm07NOV2018bhav.csv.zip",
    ),
    "2021-11-04": (
        "Diwali Laxmi Pujan / Muhurat",
        "https://archives.nseindia.com/content/circulars/CMTR46623.pdf",
        "NSE_CMTR46623_2021_holidays.pdf",
        "cm04NOV2021bhav.csv.zip",
    ),
    "2022-10-24": (
        "Diwali Muhurat special trading session",
        "https://nsearchives.nseindia.com/content/circulars/CMTR54023.pdf",
        "NSE_CMTR54023_2022_muhurat.pdf",
        "cm24OCT2022bhav.csv.zip",
    ),
    "2024-11-01": (
        "Diwali Muhurat special live session",
        "https://nsearchives.nseindia.com/content/circulars/CMTR64628.pdf",
        "NSE_CMTR64628_2024_muhurat.pdf",
        "BhavCopy_NSE_CM_0_0_0_20241101_F_0000.csv.zip",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a reproducible NSE CM calendar from archived official responses"
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/nse"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/reference"))
    args = parser.parse_args()
    holidays: dict[date, dict] = {}
    source_meta = []
    for year in range(2018, 2025):
        path = args.raw_dir / f"nse_holiday_master_trading_{year}_20261023.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("CM", []):
            day = datetime.strptime(item["tradingDate"], "%d-%b-%Y").date()
            holidays[day] = item
        source_meta.append(
            {
                "year": year,
                "provider": "NSE India holiday-master API, type=trading",
                "url": f"https://www.nseindia.com/api/holiday-master?type=trading&year={year}",
                "applicable_year": year,
                "retrieved_at_utc_file_mtime": datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ).isoformat(),
                "http_status": 200,
                "file": str(path),
                "sha256": sha256(path),
                "cm_rows": len(payload.get("CM", [])),
            }
        )
    special_dates = {date.fromisoformat(value) for value in SPECIAL}
    start, end = date(2018, 1, 1), date(2024, 12, 31)
    full_rows = []
    current = start
    while current <= end:
        source = "NSE equities weekly trading rule + annual CM holiday API"
        source_url = NSE_WEEK_RULE_URL
        description = ""
        if current in special_dates:
            description, source_url, _, _ = SPECIAL[current.isoformat()]
            status = "SPECIAL_SESSION"
            source = "NSE special-session circular and date-specific bhavcopy"
        elif current in holidays:
            item = holidays[current]
            description = item.get("description", "")
            status = "WEEKEND_HOLIDAY" if current.weekday() >= 5 else "HOLIDAY"
            source = "NSE annual CM trading-holiday API"
            source_url = (
                f"https://www.nseindia.com/api/holiday-master?type=trading&year={current.year}"
            )
        elif current.weekday() >= 5:
            status = "WEEKEND"
            description = "Saturday/Sunday per NSE equities trading rule"
        else:
            status = "SESSION"
            description = "Ordinary weekday per NSE equities trading rule; no declared holiday"
        full_rows.append(
            {
                "session_date": current.isoformat(),
                "status": status,
                "description": description,
                "source": source,
                "source_url": source_url,
            }
        )
        current = date.fromordinal(current.toordinal() + 1)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    full_path = args.output_dir / "nse_cm_calendar_2018_2024.csv"
    with full_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(full_rows[0]))
        writer.writeheader()
        writer.writerows(full_rows)
    readiness = json.loads(Path("reports/milestone_2e_readiness.json").read_text(encoding="utf-8"))
    gaps = readiness["historical_2018_2024"]["dates"]
    gap_rows = [row for row in full_rows if row["session_date"] in set(gaps)]
    targeted_path = args.output_dir / "nse_gap_calendar_2018_2024.csv"
    with targeted_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(gap_rows[0]))
        writer.writeheader()
        writer.writerows(gap_rows)
    for item in source_meta:
        year = item["year"]
        for filename, url in [
            (SPECIAL[x][2], SPECIAL[x][1]) for x in SPECIAL if x.startswith(str(year))
        ]:
            file_path = args.raw_dir / filename
            item.setdefault("special_session_circulars", []).append(
                {
                    "url": url,
                    "file": str(file_path),
                    "sha256": sha256(file_path),
                    "retrieved_at_utc_file_mtime": datetime.fromtimestamp(
                        file_path.stat().st_mtime, UTC
                    ).isoformat(),
                }
            )
        for filename in [SPECIAL[x][3] for x in SPECIAL if x.startswith(str(year))]:
            file_path = args.raw_dir / filename
            item.setdefault("special_session_reports", []).append(
                {
                    "file": str(file_path),
                    "sha256": sha256(file_path),
                    "retrieved_at_utc_file_mtime": datetime.fromtimestamp(
                        file_path.stat().st_mtime, UTC
                    ).isoformat(),
                    "validation": "date and RELIANCE EQ row reviewed",
                }
            )
    manifest = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "range": [start.isoformat(), end.isoformat()],
        "market": "NSE Capital Market cash equities",
        "calendar_rule": (
            "NSE states equities trade all days except Saturdays, Sundays, and holidays "
            "declared in advance; annual CM holiday-master API responses supply declared "
            "holiday exceptions. Explicit Muhurat session circulars override the holiday-table "
            "classification and have date-specific bhavcopy support."
        ),
        "sources": source_meta,
        "weekly_rule_url": NSE_WEEK_RULE_URL,
        "holiday_page_url": NSE_CALENDAR_URL,
        "full_calendar_file": str(full_path),
        "full_calendar_sha256": sha256(full_path),
        "full_calendar_rows": len(full_rows),
        "gap_calendar_file": str(targeted_path),
        "gap_calendar_sha256": sha256(targeted_path),
        "gap_calendar_rows": len(gap_rows),
        "gap_dates_source": (
            "Exact dates copied from reports/milestone_2e_readiness.json; no regenerated "
            "weekday inference."
        ),
        "limitations": [
            "Ordinary weekday sessions are derived from NSE's general equities weekly schedule "
            "minus published holiday dates, not independently verified with an individual "
            "bhavcopy for every session.",
            "Historical extraordinary closures not represented in the API could be missed; "
            "targeted date-specific source checks are available for the 104 gap dates.",
            "Muhurat bars have a short special-session trading period and are not "
            "regular-session daily bars; they remain flagged SPECIAL_SESSION.",
        ],
    }
    manifest_path = args.output_dir / "nse_cm_calendar_2018_2024.provenance.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "full_rows": len(full_rows),
                "gap_rows": len(gap_rows),
                "calendar_sha256": manifest["full_calendar_sha256"],
                "gap_sha256": manifest["gap_calendar_sha256"],
                "manifest": str(manifest_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
