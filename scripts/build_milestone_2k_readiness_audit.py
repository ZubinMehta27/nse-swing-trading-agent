"""Build a write-once evidence audit; this command never runs a backtest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from nse_swing_agent.action_coverage import audit_action_coverage
from nse_swing_agent.milestone_2k_audit import classify_bar_presence


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("reports/milestone_2k_v1"))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    output.mkdir(parents=True, exist_ok=True)
    targets = (
        output / "reliance_history_audit.csv",
        output / "audit.json",
        output / "readiness.md",
    )
    if any(path.exists() for path in targets):
        raise FileExistsError(f"refusing to overwrite existing Milestone 2K artefacts in {output}")

    calendar_path = root / "data/reference/nse_cm_calendar_2018_2024.csv"
    provider_path = (
        root / "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv"
    )
    candidate_dir = root / "data/validation/recovery_candidates/milestone_2j_a_v2"
    candidate_path = candidate_dir / "candidate_missing_bars.csv"
    candidate_manifest_path = candidate_dir / "recovery_manifest.json"
    action_registry = root / "reports/milestone_2h/corporate_action_evidence_registry.json"
    action_raw = root / "data/raw/nse/tejhq_actions_RELIANCE_20261023T103451Z_4b305e0765.json"
    readiness_path = root / "reports/milestone_2j_c/readiness.md"

    calendar = {}
    with calendar_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            calendar[row["session_date"]] = row["status"]
    # The retained day-calendar labels Saturdays as weekends. NSE's dated circular
    # explicitly designated 2024-01-20 a live equity session, so preserve that fact
    # as an evidence-backed exception in this audit only.
    special_session_source = (
        root
        / "data/reference/milestone_2k/source_archive/nse_special_session_2024_01_20_MSD59999.pdf"
    )
    if special_session_source.is_file():
        calendar["2024-01-20"] = "SPECIAL_SESSION"
    observed = set()
    with provider_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            observed.add(row["session_date"])
    candidates = {}
    with candidate_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            candidates[row["session_date"]] = row

    audit_rows = []
    counts: Counter[str] = Counter()
    for day, status in sorted(calendar.items()):
        classification = classify_bar_presence(
            status, observed=day in observed, candidate=day in candidates
        )
        counts[classification] += 1
        audit_rows.append(
            {
                "session_date": day,
                "calendar_status": status,
                "provider_bar_present": day in observed,
                "candidate_bar_available": day in candidates,
                "classification": classification,
            }
        )
    with targets[0].open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit_rows[0].keys())
        writer.writeheader()
        writer.writerows(audit_rows)

    candidate_manifest = json.loads(candidate_manifest_path.read_text(encoding="utf-8"))
    action_audit = audit_action_coverage(action_registry, action_raw)
    archive = []
    archive_dir = root / "data/reference/milestone_2k/source_archive"
    source_metadata = {
        "nse_cm_holidays_2025_CMTR65587.pdf": (
            "https://nsearchives.nseindia.com/content/circulars/CMTR65587.pdf",
            "2024-12-13",
            "2026-10-24T05:23:05.5270186Z",
            "NSE 2025 CM holidays and Muhurat date; contents inspected",
        ),
        "nse_cm_holidays_2026_CMTR71775.pdf": (
            "https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf",
            "2025-12-12",
            "2026-10-24T05:23:05.6807469Z",
            "NSE 2026 CM holidays; contents inspected",
        ),
        "reliance_2024_bonus_board_filing.pdf": (
            "https://nsearchives.nseindia.com/corporate/RELIANCE_16102024200409_SE_16102024.pdf",
            "2024-10-16",
            "2026-10-24T05:23:05.8219057Z",
            "Issuer filing states 1:1 bonus and 2024-10-28 record date; contents inspected",
        ),
        "reliance_annual_report_2023_24.pdf": (
            "https://nsearchives.nseindia.com/annual_reports/AR_24850_RELIANCE_2023_2024_07082024143222.pdf",
            "2024-08-07",
            "2026-10-24T05:23:08.5083283Z",
            "Issuer report inspected for demerger and 2024 dividend terms",
        ),
        "reliance_2020_rights_offer_letter.pdf": (
            "https://nsearchives.nseindia.com/corporate/RELIANCE_07062020161501_Reg30IntimationAdvertisements07062020Ltr.pdf",
            "2020-06-07",
            "2026-10-24T05:23:10.8400925Z",
            "Archived bytes; extracted terms not relied upon",
        ),
        "reliance_annual_report_2025_26.pdf": (
            "https://nsearchives.nseindia.com/annual_reports/AR_29285_RELIANCE_2025_2026_A_11007429_28052026133947.pdf",
            "2026-05-28",
            "2026-10-24T05:23:12.8916589Z",
            "Issuer report states FY26 final dividend and record date; exact payment date absent",
        ),
        "nse_reliance_rights_adjustment_FAOP44356.pdf": (
            "https://nsearchives.nseindia.com/content/circulars/FAOP44356.pdf",
            "2020-05-12",
            "2026-10-24T05:25:43.3807392Z",
            "NSE circular states 1:15 rights adjustment, ex-date, record date and issue price; "
            "accounting unsupported",
        ),
        "nse_reliance_bonus_allotment_CML64862.pdf": (
            "https://nsearchives.nseindia.com/content/circulars/CML64862.pdf",
            None,
            "2026-10-24T05:25:43.6129605Z",
            "NSE listing circular identifies RELIANCE EQ and bonus allotment 2024-10-29",
        ),
        "reliance_annual_report_2024_25.pdf": (
            "https://nsearchives.nseindia.com/corporate/kavinavora_07082025114934_SE_NoticeIAR.pdf",
            "2025-08-07",
            "2026-10-24T05:25:45.0920861Z",
            "Issuer report and current NSE page conflict on dividend record date; unresolved",
        ),
        "nse_special_session_2024_01_20_MSD59999.pdf": (
            "https://nsearchives.nseindia.com/content/circulars/MSD59999.pdf",
            "2023-12-28",
            "2026-10-24T05:31:57.2895046Z",
            "NSE circular designates 2024-01-20 special live equity trading session",
        ),
    }
    for path in sorted(archive_dir.iterdir()):
        if path.is_file():
            url, published, retrieved, note = source_metadata.get(
                path.name, (None, None, None, "No source metadata recorded")
            )
            archive.append(
                {
                    "path": str(path.relative_to(root)).replace("\\", "/"),
                    "url": url,
                    "publication_date": published,
                    "retrieved_at_utc": retrieved,
                    "sha256": sha(path),
                    "bytes": path.stat().st_size,
                    "content_review": note,
                }
            )

    evidence = {
        "schema_version": "milestone-2k-audit-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "decision": "BLOCKED",
        "performance_evaluation_run": False,
        "scope": {
            "instrument": "RELIANCE",
            "exchange": "NSE",
            "period": "2018-01-01 through 2026-10-22 provider bars; sourced day-by-day calendar "
            "audit 2018-01-01 through 2024-12-31",
            "universe_complete": False,
        },
        "inputs": {
            "calendar": {
                "path": str(calendar_path.relative_to(root)).replace("\\", "/"),
                "sha256": sha(calendar_path),
            },
            "provider": {
                "path": str(provider_path.relative_to(root)).replace("\\", "/"),
                "sha256": sha(provider_path),
                "rows": len(observed),
                "adjustment": "raw_unadjusted",
            },
            "candidate": {
                "path": str(candidate_path.relative_to(root)).replace("\\", "/"),
                "sha256": sha(candidate_path),
                "manifest": candidate_manifest_path.relative_to(root).as_posix(),
                "rows": len(candidates),
                "merged": False,
            },
            "action_registry": {
                "path": action_registry.relative_to(root).as_posix(),
                "sha256": sha(action_registry),
            },
            "action_raw": {
                "path": action_raw.relative_to(root).as_posix(),
                "sha256": sha(action_raw),
            },
        },
        "calendar_audit_classifications": dict(sorted(counts.items())),
        "candidate_dates": sorted(candidates),
        "candidate_manifest_status": candidate_manifest.get("candidate_status"),
        "candidate_reconciliation": {
            "instrument": candidate_manifest.get("instrument"),
            "canonical_schema_validation": candidate_manifest.get("canonical_schema_validation"),
            "source_reconciliation": candidate_manifest.get("source_reconciliation"),
            "bars": candidate_manifest.get("bars", []),
            "candidate_remains_unmerged": True,
        },
        "corporate_action_coverage": action_audit,
        "official_source_archive": archive,
        "readiness_source": {
            "path": readiness_path.relative_to(root).as_posix(),
            "sha256": sha(readiness_path),
            "decision": "BLOCKED",
        },
        "blockers": [
            "The eight exchange-sourced RELIANCE bars remain separate candidates and are not "
            "merged.",
            "The calendar-backed day-by-day audit covers RELIANCE only and calendar data "
            "through 2024; later circulars are selected evidence, not a full daily calendar.",
            "The TejHQ action feed is discovery evidence and does not establish complete "
            "historical corporate-action coverage.",
            "Rights and demerger accounting are unsupported; event terms and dates remain "
            "incomplete for other actions.",
            "Historical transaction costs remain incomplete and unverified, including BSE "
            "dependencies, brokerage, tax bases, DP charges and rounding.",
            "Historical instrument identity/universe and survivorship coverage are incomplete.",
        ],
    }
    targets[1].write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    missing = [row["session_date"] for row in audit_rows if "unresolved" in row["classification"]]
    md = [
        "# Milestone 2K historical readiness audit",
        "",
        "**Decision: BLOCKED.** No strategy backtest or profitability evaluation was run.",
        "",
        "## Scope",
        "",
        f"RELIANCE only. Provider bars span 2018-01-01 to 2026-10-22 ({len(observed)} rows), "
        "raw/unadjusted. Day-by-day calendar comparison covers 2018–2024 "
        f"({len(audit_rows)} dates); selected 2025/2026 exchange circulars do not constitute "
        "full daily-calendar coverage.",
        "",
        "## Calendar comparison",
        "",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ]
    md += [f"| {key} | {value} |" for key, value in sorted(counts.items())]
    md += [
        "",
        "## Recovery candidates",
        "",
        f"{len(candidates)} NSE RELIANCE EQ candidate bars are schema/source reconciled in a "
        "separate dataset. They remain unmerged. Four are special Muhurat sessions "
        "(2018-11-07, 2021-11-04, 2022-10-24, 2024-11-01); four are June 2026 sessions "
        "(2026-06-05, 2026-06-15, 2026-06-16, 2026-06-22). Older source timestamps are "
        "local file-mtime proxies, not verified retrieval times.",
        "",
        "## Corporate actions",
        "",
        "The raw provider response fingerprint matches the evidence registry "
        f"({action_audit.get('summary', {}).get('event_count', 'unknown')} event rows). "
        "Provider discovery is not evidence of complete coverage. The machine-readable "
        "event-by-event findings are in `audit.json`.",
        "",
        "Selected archived issuer/exchange documents are fingerprinted in `audit.json`. "
        "The 2025 dividend record-date sources conflict; the 2026 dividend payment date "
        "is not established. Rights and JFSL demerger terms are partially corroborated, "
        "but required accounting is unsupported. No absence from the provider feed is "
        "treated as proof no event occurred.",
        "",
        "## Priority blockers and remediation",
        "",
        "| Priority | Affected scope | Gap and risk | Best evidence / "
        "next action | Acceptance test |",
        "|---:|---|---|---|---|",
        "| 1 | RELIANCE, 2018–2026 | Eight bars are outside canonical series; "
        "silent merge could alter raw history. | "
        "Review candidate manifest and authorize separately versioned migration after event-"
        "continuity review. | Independent source hashes and canonical equality; new immutable "
        "dataset fingerprint; original bytes unchanged. |",
        "| 2 | RELIANCE, full provider period | Action-feed completeness and terms are unresolved; "
        "unsupported rights/demerger accounting can misstate holdings/cash. | Obtain issuer "
        "filings, exchange notices, depository/event records; reconcile event universe and "
        "terms. | Every in-scope event has verified identity, dates, terms and tested "
        "accounting or blocks period. |",
        "| 3 | NSE/BSE historical cost schedule | Missing historical tax, BSE group/turnover, "
        "brokerage, DP and rounding inputs. | Obtain dated government, exchange, SEBI, "
        "depository and broker evidence for chosen account category. | Complete verified "
        "date-effective profiles pass boundary and arithmetic tests. |",
        "| 4 | All instruments | RELIANCE-only sample and incomplete point-in-time "
        "universe/ISIN evidence do not establish broad coverage. | Define universe and acquire "
        "sourced identity/calendar/bar data. | Coverage manifest proves each instrument/session "
        "and no unresolved expected gaps. |",
        "",
        "## Evidence limitations",
        "",
        f"Unresolved calendar-audit dates within 2018–2024: {', '.join(missing) or 'none'}.",
        "The calendar labels ordinary weekdays by the sourced holiday calendar and "
        "exchange-week rule; it does not independently verify every day with a bhavcopy. "
        "The eight candidate source files and selected official PDFs are listed with "
        "SHA-256 in `audit.json`. No candidate rows were merged. Cost profile and prior "
        "evidence were not edited.",
        "",
    ]
    targets[2].write_text("\n".join(md), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "decision": "BLOCKED",
                "calendar_rows": len(audit_rows),
                "candidate_rows": len(candidates),
                "unresolved_calendar_dates": len(missing),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
