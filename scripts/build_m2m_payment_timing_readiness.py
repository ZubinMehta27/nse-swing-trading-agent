"""Create a write-once dividend payment-timing readiness addendum."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT = Path("reports/milestone_2m_v4/corporate_action_audit.json")
OUT = Path("reports/milestone_2m_v5")
DATE_RANGE = re.compile(r"(\d{4}-\d{2}-\d{2}) through (\d{4}-\d{2}-\d{2})")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output_dir: Path = OUT) -> dict[str, Any]:
    audit_path = ROOT / AUDIT
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    classifications = []
    for event in audit["events"]:
        if event["event_type"] != "dividend":
            continue
        evidence = event.get("milestone_2m_supplement", {}).get("payment_evidence", {})
        window = evidence.get("documented_window")
        if evidence.get("exact_payment_date_verified") is True:
            status = "EXACT_DATE"
            earliest = latest = None
        elif isinstance(window, dict) and window.get("start") and window.get("end"):
            status = "DOCUMENTED_WINDOW"
            earliest, latest = window["start"], window["end"]
        elif isinstance(window, dict) and isinstance(window.get("description"), str):
            match = DATE_RANGE.search(window["description"])
            if match:
                status = "DOCUMENTED_WINDOW"
                earliest, latest = match.groups()
            else:
                status = "UNKNOWN"
                earliest = latest = None
        else:
            status = "UNKNOWN"
            earliest = latest = None
        classifications.append(
            {
                "event_group": event["event_group"],
                "symbol": event["instrument"]["symbol"],
                "isin": event["instrument"].get("isin"),
                "ex_date": event["provider_terms"].get("ex_date"),
                "status": status,
                "exact_date": None,
                "earliest_date": earliest,
                "latest_date": latest,
                "evidence_reference": (
                    window.get("source_ids") if isinstance(window, dict) else None
                ),
                "evidence_description": (
                    window.get("description") if isinstance(window, dict) else None
                ),
                "accounting_supported": status == "EXACT_DATE",
                "accounting_policy": (
                    "Exact-date receivable and cash transition supported"
                    if status == "EXACT_DATE"
                    else (
                        "Fail closed when a dividend entitlement is held; "
                        "no portfolio path returned"
                    )
                ),
            }
        )

    counts = {
        status: sum(row["status"] == status for row in classifications)
        for status in (
            "EXACT_DATE",
            "DOCUMENTED_WINDOW",
            "UNKNOWN",
        )
    }
    if sum(counts.values()) != 17:
        raise ValueError(f"expected 17 provider dividend events, found {sum(counts.values())}")
    report = {
        "schema_version": "milestone-2m-payment-timing-readiness-v1",
        "input_audit": {"path": AUDIT.as_posix(), "sha256": _sha(audit_path)},
        "payment_timing_counts": counts,
        "descriptive_unbounded_window_notes": sum(
            bool(row["evidence_description"]) and row["status"] == "UNKNOWN"
            for row in classifications
        ),
        "accounting_support": {
            "EXACT_DATE": "supported and covered by regression tests",
            "DOCUMENTED_WINDOW": "unsupported for portfolio simulation; affected runs fail closed",
            "UNKNOWN": "unsupported for portfolio simulation; affected runs fail closed",
        },
        "cash_safety": {
            "credit_at_earliest_window_date": False,
            "credit_at_latest_window_date_as_exact": False,
            "portfolio_path_returned_for_held_window_or_unknown_dividend": False,
        },
        "overall_readiness": "BLOCKED",
        "eligible_historical_window": None,
        "independent_blockers_remain": [
            "corporate-action history completeness not established",
            "rights and demerger accounting unsupported",
            "historical costs remain incomplete or unverified",
            "historical bar, instrument-identity and session coverage gates remain unresolved",
        ],
        "real_data_backtest_run": False,
        "events": classifications,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "payment_timing_readiness.json"
    md_path = output_dir / "readiness.md"
    for path in (json_path, md_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite write-once artifact: {path}")
    lines = [
        "# Milestone 2M — Dividend payment-timing readiness addendum",
        "",
        "**Readiness: BLOCKED. No real-data backtest was run.**",
        "",
        f"- Exact payment dates verified: {counts['EXACT_DATE']}",
        f"- Bounded documented payment windows: {counts['DOCUMENTED_WINDOW']}",
        f"- Unknown actionable timing: {counts['UNKNOWN']}",
        (
            "- Descriptive but unbounded window notes within UNKNOWN: "
            f"{report['descriptive_unbounded_window_notes']}"
        ),
        "",
        "Exact-date dividends retain ex-date receivable recognition and payment-date cash credit. "
        "For a documented window or unknown timing, a held entitlement raises a structured "
        "blocking error containing the amount, timing bounds or unknown state, evidence reference "
        "and source fingerprint. No portfolio path is returned, so the engine cannot credit cash "
        "at either window boundary or invent an exact posting date.",
        "",
        "Window and unknown timing are representable in the action model, but they are not "
        "supported for portfolio-path accounting. Existing action-coverage, unsupported-event, "
        "data/session and historical-cost gates remain in force.",
        "",
        "No bounded window is eligible. This addendum does not alter the Milestone 2M base audit "
        "or global readiness defaults.",
        "",
        f"Input audit SHA-256: `{report['input_audit']['sha256']}`.",
    ]
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    report = build(args.output_dir)
    print(
        f"readiness={report['overall_readiness']} "
        f"exact={report['payment_timing_counts']['EXACT_DATE']} "
        f"windows={report['payment_timing_counts']['DOCUMENTED_WINDOW']} "
        f"unknown={report['payment_timing_counts']['UNKNOWN']}"
    )


if __name__ == "__main__":
    main()
