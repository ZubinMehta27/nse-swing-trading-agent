"""Build the write-once Milestone 2M evidence and readiness reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/milestone_2m_v2"
ARCHIVE = Path("data/reference/milestone_2m/source_archive")

SUPPLEMENTAL_SOURCES = {
    "ril_2009_2010_annual_report": {
        "file": "ril_2009_2010_annual_report.pdf",
        "retrieved_at_utc": "2026-10-24T05:58:45.817929+00:00",
        "url": "https://www.ril.com/sites/default/files/2022-12/2009-2010.pdf",
        "publication_date": "2010-07 (annual report; exact publication day unavailable)",
        "relevance": (
            "Records the 2009-10 Board recommendation of INR 7 per share on 2010-04-23, "
            "subject to shareholder approval at the AGM. It does not establish the exact "
            "payment date in the inspected passages."
        ),
    },
    "bse_2009_2010_annual_report": {
        "file": "bse_2009_2010_annual_report.pdf",
        "retrieved_at_utc": "2026-10-24T06:01:02.855395+00:00",
        "url": "https://www.bseindia.com/bseplus/AnnualReport/500325/5003250310.pdf",
        "publication_date": "2010 (annual report; exact publication day unavailable)",
        "relevance": (
            "Issuer annual report hosted by BSE: recommends INR 7 per share and states "
            "eligible members as of 2010-05-11. This is an official issuer/exchange copy; "
            "the source does not itself establish the ex-date or actual payment date."
        ),
    },
    "ril_2019_2020_annual_report": {
        "file": "ril_2019_2020_annual_report.pdf",
        "retrieved_at_utc": "2026-10-24T05:58:50.853395+00:00",
        "url": "https://www.ril.com/ar2019-20/pdf/RIL_Integrated-Annual-Report-2019-2020.pdf",
        "publication_date": "2020 (annual report; exact publication day unavailable)",
        "relevance": (
            "Issuer annual report specifies the electronic dividend payment window "
            "2020-07-16 through 2020-07-22. It does not establish which day an individual "
            "account received funds."
        ),
    },
    "ril_2020_2021_annual_report": {
        "file": "ril_2020_2021_annual_report.pdf",
        "retrieved_at_utc": "2026-10-24T05:58:52.119865+00:00",
        "url": "https://www.ril.com/ar2020-21/pdf/reliance-annual-report-21.pdf",
        "publication_date": "2021 (annual report; exact publication day unavailable)",
        "relevance": (
            "Issuer annual report specifies the electronic dividend payment window "
            "2021-06-24 through 2021-06-30. It does not establish which day an individual "
            "account received funds."
        ),
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_once(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing evidence artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def build(output: Path = OUT) -> dict[str, Any]:
    previous_path = ROOT / "reports/milestone_2l_v1/corporate_action_audit.json"
    previous_bytes = previous_path.read_bytes()
    previous = json.loads(previous_bytes)
    sources: dict[str, Any] = {}
    for source_id, source in SUPPLEMENTAL_SOURCES.items():
        local = ROOT / ARCHIVE / source["file"]
        if not local.is_file():
            raise FileNotFoundError(f"required archived source is missing: {local}")
        sources[source_id] = {
            "url": source["url"],
            "publication_date": source["publication_date"],
            "retrieved_at_utc": source["retrieved_at_utc"],
            "retrieval_outcome": "source_bytes_archived_and_content_reviewed",
            "retrieval_time_note": (
                "UTC retrieval timestamp was captured immediately after the HTTP response "
                "was fully read."
            ),
            "archive_path": (ARCHIVE / source["file"]).as_posix(),
            "sha256": sha256(local),
            "bytes": local.stat().st_size,
            "relevance": source["relevance"],
        }

    events = json.loads(json.dumps(previous["events"]))
    event_2010 = next(item for item in events if item["event_group"] == "5061a9fcd61e1c1b")
    event_2010["milestone_2m_supplement"] = {
        "source_resolution": "partially_resolved_same_existing_economic_event",
        "same_group_as_milestone_2l": True,
        "declaration_or_recommendation": {
            "date": "2010-04-23",
            "meaning": "Board recommendation; shareholder approval is a separate event",
            "source_ids": ["ril_2009_2010_annual_report", "bse_2009_2010_annual_report"],
        },
        "record_date": "2010-05-11",
        "record_date_source_ids": ["bse_2009_2010_annual_report"],
        "amount_inr_per_share": "7.00",
        "amount_source_ids": ["ril_2009_2010_annual_report", "bse_2009_2010_annual_report"],
        "unresolved": [
            "primary-source ex-date confirmation",
            "shareholder approval date evidence in the retrieved annual-report copy",
            "exact dividend payment date or documented issuer payment window",
        ],
        "relationship": (
            "This is the existing provider row/group; it is not a twenty-second event. "
            "The absence from the retained 20-row NSE API response remains a source-coverage "
            "limitation, not evidence of non-occurrence."
        ),
    }

    payment_windows = {
        "2020-07-02": {
            "start": "2020-07-16",
            "end": "2020-07-22",
            "source_ids": ["ril_2019_2020_annual_report"],
        },
        "2021-06-11": {
            "start": "2021-06-24",
            "end": "2021-06-30",
            "source_ids": ["ril_2020_2021_annual_report"],
        },
    }
    for event in events:
        if event["event_type"] == "dividend":
            prior_window = event["terms"].get("payment_window")
            observed_window = payment_windows.get(event["provider_terms"].get("ex_date"))
            if observed_window is None and prior_window:
                observed_window = {
                    "description": prior_window,
                    "source_ids": event.get("source_ids", []),
                    "exact_bounds_verified": False,
                    "inherited_from": "milestone_2l_v1/corporate_action_audit.json",
                }
            event.setdefault("milestone_2m_supplement", {})["payment_evidence"] = {
                "exact_payment_date_verified": False,
                "documented_window": observed_window,
                "accounting_effect": (
                    "Existing model requires exact payment_date; window bounds cannot be "
                    "silently substituted. Cash timing remains unsupported for this event."
                ),
            }

    payload = {
        "schema_version": "milestone-2m-corporate-action-audit-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "prior_audit": {
            "path": "reports/milestone_2l_v1/corporate_action_audit.json",
            "sha256": hashlib.sha256(previous_bytes).hexdigest(),
            "preserved_unchanged": True,
        },
        "decision": "BLOCKED",
        "real_data_backtest_run": False,
        "scope": {
            "provider_rows": previous["scope"]["provider_rows"],
            "economic_event_groups": previous["scope"]["economic_event_groups"],
            "candidate_bars_merged": False,
            "complete_action_history_established": False,
        },
        "counts": {
            **previous["counts"],
            "dividend_events_with_exact_payment_date": 0,
            "dividend_events_with_newly_archived_payment_window": 2,
            "provider_action_feed_completeness_proven": False,
        },
        "newly_verified_terms": {
            "event_2010": {
                "board_recommendation_date": "2010-04-23",
                "amount_inr_per_share": "7.00",
                "record_date": "2010-05-11",
                "verified_against": [
                    "RIL annual report 2009-10",
                    "BSE-hosted RIL annual report 2009-10",
                ],
                "limitations": [
                    "AGM approval date not independently extracted from the retrieved report",
                    "ex-date still lacks primary-source confirmation",
                    "actual payment date/window remains unavailable",
                ],
            },
            "payment_windows": payment_windows,
        },
        "accounting_assessment": {
            "supported_and_tested": [
                (
                    "dividend entitlement from prior-close holding; ex-date receivable "
                    "and payment-date cash"
                ),
                "split and bonus quantity and basis scaling, plus stop/target rebasing",
                "fractional share results block without cash-in-lieu terms",
            ],
            "blocked_and_tested": [
                "rights issues",
                "demergers",
                "mergers",
                "buybacks",
                "delistings",
            ],
            "payment_window_policy": (
                "Not supported as a cash-credit schedule. The current model requires an exact "
                "payment date, and the documented windows do not identify the actual posting "
                "date. Do not replace a window with its start or end date."
            ),
            "synthetic_tests_are_coverage_evidence": False,
        },
        "bounded_window_assessment": {
            "eligible_period": None,
            "decision": "NO_WINDOW_PASSES_ALL_GATES",
            "reasons": [
                "issuer action-history completeness is not established for any proposed interval",
                (
                    "dividend exact payment dates remain unavailable and payment "
                    "windows are not modeled"
                ),
                "rights and demerger accounting is unsupported where relevant",
                "historical session/data identity gaps remain unresolved",
                "complete date-effective historical transaction costs remain unverified",
            ],
            "does_not_weaken_global_readiness": True,
        },
        "sources": sources,
        "events": events,
        "next_actions": [
            (
                "Obtain symbol-bound issuer/exchange evidence for missing ex/record dates "
                "and the 2010 ex-date."
            ),
            (
                "Obtain exact payment dates or implement and test a receivable/window "
                "policy that never advances cash before the documented bound."
            ),
            (
                "Establish action-history completeness from primary issuer/exchange "
                "records independently of the provider feed."
            ),
            (
                "Implement verified rights and demerger consideration/basis accounting "
                "or continue blocking affected windows."
            ),
            (
                "Resolve historical bars, instrument identity, calendar, and "
                "date-effective transaction-cost gates before proposing a bounded window."
            ),
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    audit_path = output / "corporate_action_audit.json"
    manifest_path = output / "source_manifest.json"
    readiness_path = output / "readiness.md"
    for path in (audit_path, manifest_path, readiness_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing evidence artifact: {path}")
    manifest = {
        "schema_version": "milestone-2m-source-manifest-v1",
        "previous_milestone_2l_manifest": {
            "path": "reports/milestone_2l_v1/source_manifest.json",
            "sha256": sha256(ROOT / "reports/milestone_2l_v1/source_manifest.json"),
            "preserved_unchanged": True,
        },
        "supplemental_sources": sources,
        "retrieval_failures": [],
        "non_findings": [
            "The original 25-row TejHQ response was not modified.",
            (
                "The NSE symbol-bound response's omission of the 2010 row is not proof "
                "the event did not occur."
            ),
            "No retrieval timestamp was fabricated for Milestone 2L source files.",
        ],
    }
    md = [
        "# Milestone 2M — RELIANCE corporate-action accounting and coverage audit",
        "",
        "**Decision: BLOCKED. No strategy backtest or profitability evaluation was run.**",
        "",
        "## Evidence update",
        "",
        (
            "The 2010 provider dividend is reconciled to its existing event group, not "
            "counted as a new event. Official RIL/BSE-hosted annual-report copies support "
            "a Board recommendation dated 2010-04-23, INR 7.00 per share and a "
            "2010-05-11 record date. The retrieved evidence does not verify the ex-date, "
            "shareholder approval date, or payment date/window. Its absence from the "
            "20-row NSE API response remains a source-coverage limitation."
        ),
        "",
        (
            "The archived RIL annual reports document payment windows for the 2020 and "
            "2021 dividends: 2020-07-16–2020-07-22 and 2021-06-24–2021-06-30. "
            "These are windows, not exact shareholder cash-posting dates. Earlier "
            "Milestone 2L issuer filings also document windows for 2023–2026. No exact "
            "payment date was established for the 17 provider dividend events."
        ),
        "",
        "## Accounting and bounded period",
        "",
        (
            "Existing accounting tests cover ex-date dividend receivables and "
            "payment-date cash; split/bonus quantity, basis and protective-price "
            "adjustments; and blocking fractional entitlements without cash-in-lieu "
            "terms. Rights, demerger, merger, buyback and delisting remain fail-closed. "
            "The dividend model requires an exact payment date and cannot safely use a "
            "payment window as a cash-credit date."
        ),
        "",
        (
            "No bounded historical window passes every data, action-coverage, "
            "accounting, calendar and verified transaction-cost gate. Synthetic tests "
            "do not establish real-event coverage. The eight recovery candidates remain "
            "separate and were not merged."
        ),
        "",
        "## Remaining blockers",
        "",
        *[f"- {item}" for item in payload["next_actions"]],
        "",
        (
            "Source byte hashes, publication-date precision and retrieval timestamp "
            "limitations are recorded in `source_manifest.json`. Milestone 2L and "
            "earlier evidence are unchanged."
        ),
    ]
    write_once(audit_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    write_once(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    write_once(readiness_path, "\n".join(md) + "\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    result = build(args.output)
    print(
        f"decision={result['decision']} "
        f"events={result['scope']['economic_event_groups']} "
        "exact_dividend_payment_dates="
        f"{result['counts']['dividend_events_with_exact_payment_date']} "
        "eligible_window=none"
    )


if __name__ == "__main__":
    main()
