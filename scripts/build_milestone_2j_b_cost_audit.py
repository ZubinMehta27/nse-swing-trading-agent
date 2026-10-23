"""Emit a deterministic evidence/coverage audit, not a performance evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from nse_swing_agent.cost_profiles import load_cost_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "config/cost_profiles/zerodha_resident_individual_delivery_v2_partial.json"
OUT = ROOT / "reports/milestone_2j_b"


def write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise FileExistsError(f"refusing to overwrite audit artifact: {path}")
        return
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    profile = load_cost_profile(PROFILE)
    rules = [
        {
            "component": rule.component,
            "exchange": rule.exchange,
            "side": rule.sides,
            "effective_from": rule.effective_from.isoformat() if rule.effective_from else None,
            "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
            "rate": str(rule.rate) if rule.rate is not None else None,
            "fixed_amount": str(rule.fixed_amount) if rule.fixed_amount is not None else None,
            "status": rule.verification_status,
            "rounding": rule.rounding,
            "source_id": rule.source_id,
            "note": rule.note,
        }
        for rule in profile.rules
    ]
    sources = [
        {"source_id": source_id, "url": url, "archive_status": status, "sha256": digest}
        for source_id, url, status, digest in profile.source_metadata
    ]
    report = {
        "milestone": "2J-B",
        "report_type": "tariff_coverage_audit",
        "readiness": "BLOCKED",
        "backtest_executed": False,
        "profitability_evaluation": False,
        "profile_version": profile.version,
        "profile_status": profile.status,
        "market": profile.market,
        "segment": profile.segment,
        "exchanges": list(profile.exchanges),
        "account_category": profile.account_category,
        "rules": rules,
        "sources": sources,
        "known_blockers": [
            "Brokerage current zero rate has no verified historical effective interval and "
            "contract-note minimum is unresolved.",
            "STT source result was observed but direct bytes were not archived; historical "
            "intervals and billing rounding are not resolved.",
            "NSE exchange-charge schedules are dated from 2024-10-01; fractional charge "
            "rounding is unverified, and earlier history is uncovered.",
            "BSE charges vary by historical scrip group/exclusivity and monthly turnover; no "
            "symbol/date lookup or complete tariff model is configured.",
            "SEBI turnover rate dates are sourced, but customer billing/rounding treatment is "
            "not verified.",
            "Stamp-duty official PDF retrieval timed out after 30 seconds; a search extract "
            "was observed, but source bytes and effective-date extraction were not validated.",
            "GST taxable-base coverage and historical dates/rounding remain incomplete.",
            "Zerodha DP base charge lacks historical effective dates; CDSL evidence is limited "
            "to the 2026-03-31 manual edition, and DP GST grouping/rounding is incomplete.",
            "Corporate-action, historical-bar recovery, source-completeness and other real-data "
            "readiness blockers remain independent.",
        ],
        "limitations": [
            "No partial cost total is exposed; the resolver only returns a quote when every "
            "required component is supported.",
            "Account-level AMC and non-trading fees are excluded pending an explicit "
            "allocation policy.",
            "The audit does not run a strategy backtest or calculate performance.",
        ],
    }
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = [
        "# Milestone 2J-B Cost Coverage Audit",
        "",
        "**Readiness: BLOCKED.** This is a tariff evidence audit only; no backtest or "
        "profitability evaluation was run.",
        "",
        f"Profile: `{profile.version}` (`{profile.status}`), India cash delivery, NSE/BSE, "
        "Zerodha resident individual.",
        "",
        "## Remaining cost blockers",
        "",
        *[f"- {item}" for item in report["known_blockers"]],
        "",
        "## Archived and observed sources",
        "",
        "Source hashes and archive statuses are recorded in `coverage.json` and the profile "
        "provenance manifest. Unarchived official-source observations have no fabricated hash.",
        "",
        "## Gate behaviour",
        "",
        "A versioned profile is required for every non-synthetic backtest. This profile is "
        "partial; dated gaps, unverified rules, missing holder parameters, or unverified "
        "rounding raise a coverage error. No partial total is returned.",
        "",
    ]
    write_once(OUT / "coverage.json", json_text)
    write_once(OUT / "readiness.md", "\n".join(markdown))
    print(
        f"readiness={report['readiness']}; rules={len(rules)}; sources={len(sources)}; "
        "backtest_executed=false"
    )


if __name__ == "__main__":
    main()
