"""Write the deterministic Milestone 2J readiness report from evidence manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != content:
        raise FileExistsError(f"refusing to overwrite different Milestone 2J evidence: {path}")
    if not path.exists():
        path.write_bytes(content)


def readiness(
    candidate: dict[str, Any], profile_path: Path, milestone: str = "2J"
) -> dict[str, Any]:
    current = candidate["overall_evaluation_readiness"]
    return {
        "milestone": milestone,
        "paper_only": True,
        "profitability_evaluation_run": False,
        "real_data_backtest_ready": False,
        "decision": "BLOCKED",
        "candidate_recovery": {
            "status": candidate["candidate_status"],
            "rows": candidate["candidate_rows"],
            "dates": candidate["requested_dates"],
            "standalone": candidate["candidate_is_standalone"],
            "merged": candidate["automatic_merge_performed"],
            "path": candidate["candidate_dataset_path"],
            "sha256": candidate["candidate_dataset_sha256"],
        },
        "dataset_identity": current["identity"],
        "adjustment_compatibility": candidate["adjustment_policy"],
        "corporate_action_readiness": current["corporate_actions"],
        "cost_profile": {
            "path": profile_path.relative_to(ROOT).as_posix(),
            "sha256": sha256(profile_path),
            "provenance_manifest": "data/reference/cost_profiles/source_archive/manifest.json",
            "provenance_manifest_sha256": sha256(
                ROOT / "data/reference/cost_profiles/source_archive/manifest.json"
            ),
            "version": current["cost_coverage"]["profile_version"],
            "status": current["cost_coverage"]["profile_status"],
            "all_history_dates_covered": current["cost_coverage"][
                "uncovered_provider_session_count"
            ]
            == 0,
            "candidate_dates_covered": current["cost_coverage"]["uncovered_candidate_session_count"]
            == 0,
            "provider_uncovered_sessions": current["cost_coverage"][
                "uncovered_provider_session_count"
            ],
            "candidate_uncovered_sessions": current["cost_coverage"][
                "uncovered_candidate_session_count"
            ],
        },
        "blockers": [
            "Full-history TejHQ identity has no ISIN; eight verified candidate rows "
            "do not establish the identity of all provider rows.",
            "The provider action feed is discovery-only and not completeness-verified; dividend "
            "dates/currency remain absent in 20 records.",
            "Rights, demerger, merger, buyback and delisting accounting remain unsupported "
            "or unverified.",
            "Eight NSE bars are available only in a separate candidate dataset and are not merged.",
            "No complete date-effective, verified cost profile covers all historical sessions; "
            "the hypothetical profile fails closed.",
            "The existing Milestone 2H historical action-coverage and point-in-time-universe "
            "blockers remain.",
        ],
        "source_failures": candidate["source_failures"],
        "prior_readiness_artifacts_modified": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    candidate = report["candidate_recovery"]
    costs = report["cost_profile"]
    action = report["corporate_action_readiness"]
    blockers = [line for item in report["blockers"] for line in _wrap(item)]
    dates = ", ".join(candidate["dates"])
    unsupported = ", ".join(action["unsupported_event_types"])
    lines = [
        f"# Milestone {report['milestone']} Readiness",
        "",
        "**Decision: BLOCKED.** No real-data backtest or profitability evaluation was run.",
        "",
        "## Bounded recovery candidate",
        "",
        f"- Candidate validation: **{candidate['status']}**, {candidate['rows']} NSE bars.",
        f"- Dates: {dates}.",
        f"- Candidate SHA-256: `{candidate['sha256']}`.",
        f"- Candidate data: `{candidate['path']}`. It is standalone and was not merged into TejHQ.",
        "  It was not added to any prior dataset.",
        "- Source rows match source hashes, date, RELIANCE symbol, ISIN INE002A01018, NSE EQ,",
        "  and the Milestone 2H reconciled OHLCV. The four June 2026 reports retain recorded",
        "  retrieval times; the older four have file-mtime proxies, not verified retrieval times.",
        "- Both source sets are treated as raw/unadjusted. This does not clear action continuity.",
        "  The candidate builder makes no adjustment and prohibits merge pending review.",
        "",
        "## Existing-history identity, actions and costs",
        "",
        "- Full-history symbol/ISIN identity remains incomplete; only candidate rows have it.",
        f"- Corporate-action registry has {action['provider_action_rows']} provider rows, but is",
        "  not completeness-verified.",
        f"  {action['missing_dividend_terms']} dividends lack payment-date or currency terms.",
        f"  Unsupported event types: {unsupported}.",
        f"- Hypothetical profile `{costs['version']}` is `{costs['status']}`.",
        f"  It leaves {costs['provider_uncovered_sessions']} of 2166 provider sessions and",
        f"  {costs['candidate_uncovered_sessions']} of 8 candidate sessions uncovered.",
        "  No tariff was inferred to complete it.",
        "",
        "## Blockers",
        "",
        *blockers,
        "",
        "## Decision",
        "",
        "The eight-row candidate validates only its source records. It does not establish history",
        "completeness, corporate-action coverage, date-effective transaction costs, or real-data",
        "evaluation readiness. Keep raw inputs and previous evidence immutable.",
        "The next human input is confirmation of the account/holder category and intended broker",
        "tariff evidence, followed by source-backed review of historical statutory fee intervals",
        "and unresolved corporate-action coverage. Do not backtest until the readiness gate",
        "is independently rebuilt and passes.",
    ]
    return "\n".join(lines) + "\n"


def _wrap(text: str, width: int = 92) -> list[str]:
    words = text.split()
    output: list[str] = []
    current = "-"
    for word in words:
        if len(current) > 1 and len(current) + len(word) + 1 > width:
            output.append(current)
            current = "  "
        current += (" " if current.strip() else "") + word
    if current.strip():
        output.append(current)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        type=Path,
        default=ROOT / "data/validation/recovery_candidates/milestone_2j_v2/recovery_manifest.json",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/milestone_2j_v2")
    parser.add_argument("--milestone", default="2J", choices=("2J", "2J-A"))
    args = parser.parse_args()
    candidate_path = args.candidate.resolve()
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    profile_path = (
        ROOT / "config/cost_profiles/zerodha_resident_individual_nse_delivery_hypothetical.json"
    )
    report = readiness(candidate, profile_path, args.milestone)
    dataset_path = candidate_path.parent / candidate["candidate_dataset_path"]
    try:
        report["candidate_recovery"]["path"] = dataset_path.relative_to(ROOT).as_posix()
    except ValueError:
        report["candidate_recovery"]["path"] = str(dataset_path)
    out = args.output_dir.resolve()
    write_once(out / "readiness.json", (json.dumps(report, indent=2) + "\n").encode())
    write_once(out / "readiness.md", render_markdown(report).encode())
    print(f"BLOCKED; standalone candidate {candidate['candidate_rows']} rows; reports in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
