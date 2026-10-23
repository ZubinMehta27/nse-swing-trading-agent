"""Build immutable 2J-C tariff evidence and coverage artifacts offline."""

# Evidence prose is kept as concise single JSON/Markdown field values.
# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_B = ROOT / "config/cost_profiles/zerodha_resident_individual_delivery_v2_partial.json"
PROFILE_C = ROOT / "config/cost_profiles/zerodha_resident_individual_delivery_v3_partial.json"
MANIFEST_B = ROOT / "data/reference/cost_profiles/milestone_2j_b/provenance_manifest.json"
MANIFEST_C = ROOT / "data/reference/cost_profiles/milestone_2j_c/provenance_manifest.json"
REPORT_DIR = ROOT / "reports/milestone_2j_c"
INVENTORY = ROOT / "data/reference/cost_profiles/milestone_2j_c/source_inventory.json"


def write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise FileExistsError(f"refusing to overwrite differing evidence: {path}")
        return
    path.write_text(content, encoding="utf-8", newline="\n")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build() -> dict:
    old_manifest = _json(MANIFEST_B)
    sources = []
    for old in old_manifest["sources"]:
        item = dict(old)
        archive_file = item.get("archive_file")
        if archive_file:
            # The 2J-C manifest sits beside 2J-B, so preserve an explicit relative path.
            if archive_file.startswith("../source_archive/"):
                item["archive_file"] = "../" + archive_file.removeprefix("../")
            elif archive_file.startswith("source_archive/"):
                item["archive_file"] = "../milestone_2j_b/" + archive_file
        sources.append(item)

    # Browser-accessible official content was inspected, but direct archival failed.
    # No local hash is claimed for these observations.
    sources.extend(
        [
            {
                "source_id": "income_tax_stt_delivery_2005",
                "title": "Income Tax Department explanatory circular, Finance Act 2005",
                "url": "https://www.incometaxindia.gov.in/documents/20117/14628360/ExplanatoryCircularFinanceAct2005-Compiled-Recast_2_.pdf/96027428-3563-b168-0386-408400394790?t=1767814850389",
                "publication_date": "2005-05-13",
                "effective_date": "2005-06-01",
                "retrieved_at_utc": "2026-10-23T13:18:14.479663Z",
                "status": "content_observed_archive_failed",
                "archive_file": None,
                "sha256": None,
                "error": "Official PDF request returned HTTP 403; document text was available through official-site search/open results.",
                "applicability": "Historical delivery-equity STT; observed circular states 0.1% on purchases and sales from 2005-06-01. Current Section 98 separately corroborates current rate.",
                "content_validation": "partial; no locally archived bytes to independently revalidate",
            },
            {
                "source_id": "india_stamp_act_schedule_56a",
                "title": "India Code Indian Stamp Act, Schedule I, Item 56A",
                "url": "https://www.indiacode.nic.in/bitstream/123456789/15510/5/A1899-2%20.pdf",
                "publication_date": None,
                "effective_date": "2020-07-01",
                "retrieved_at_utc": "2026-10-23T13:18:14.613966Z",
                "status": "content_observed_archive_failed",
                "archive_file": None,
                "sha256": None,
                "error": "Official PDF request timed out after 20 seconds; a separate official India Code search result exposed Schedule I text.",
                "applicability": "Delivery equity stamp duty buyer-side rate 0.015%; official DEA report corroborates central implementation on 2020-07-01.",
                "content_validation": "partial; no locally archived bytes to independently revalidate",
            },
            {
                "source_id": "dea_stamp_duty_implementation_2020",
                "title": "Department of Economic Affairs Annual Report 2020-2021",
                "url": "https://dea.gov.in/files/annual_reports_documents/Annual_Report_2020_2021_English.pdf",
                "publication_date": "2021-03-31",
                "effective_date": "2020-07-01",
                "retrieved_at_utc": "2026-10-23T13:18:34.654808Z",
                "status": "content_observed_archive_failed",
                "archive_file": None,
                "sha256": None,
                "error": "Official PDF TLS connection could not be established.",
                "applicability": "Corroborates implementation date only; not tariff calculation or rounding.",
                "content_validation": "partial; no locally archived bytes to independently revalidate",
            },
        ]
    )
    manifest = {
        "schema_version": "1.0",
        "profile_version": "zerodha-resident-individual-delivery-2026-10-partial-v2",
        "purpose": "2J-C historical evidence reconciliation; partial observations do not qualify a complete cost quote.",
        "sources": sources,
    }

    profile = _json(PROFILE_B)
    profile["version"] = manifest["profile_version"]
    profile["provenance_manifest"] = (
        "../../data/reference/cost_profiles/milestone_2j_c/provenance_manifest.json"
    )
    for rule in profile["rules"]:
        if rule["component"] == "stt":
            rule["effective_from"] = "2018-01-01"
            rule["effective_to"] = "2026-10-23"
            rule["verification_status"] = "partially_verified"
            rule["source_id"] = "income_tax_stt_delivery_2005"
            rule["note"] = (
                "Official 2005 circular content states 0.1% delivery STT from 2005-06-01, with current Section 98 corroboration; local source bytes unavailable and client-side rounding unverified. No quote is permitted."
            )
        elif rule["component"] == "stamp_duty":
            rule["effective_from"] = "2020-07-01"
            rule["effective_to"] = "2026-10-23"
            rule["verification_status"] = "partially_verified"
            rule["source_id"] = "india_stamp_act_schedule_56a"
            rule["note"] = (
                "Official India Code Schedule I search content and DEA annual-report content support 0.015% delivery buyer rate from 2020-07-01; source bytes could not be archived, earlier state-specific periods are not modeled, and rounding is unverified. No quote is permitted."
            )

    blockers = [
        "Brokerage effective-date history, contract-note minimums and rounding remain unsupported.",
        "STT delivery rate is content-corroborated at 0.1% for the covered historical window, but local primary bytes, customer billing precision and rounding are unresolved.",
        "Stamp duty 0.015% buyer-side is content-corroborated from 2020-07-01 only; the pre-central-regime state-specific treatment and billing rounding are unresolved.",
        "NSE exchange charges are evidenced only from 2024-10-01; earlier coverage and charge rounding remain unavailable.",
        "BSE tariff depends on date-specific scrip group/exclusivity and monthly turnover; no validated historical RELIANCE group series or full schedule is configured.",
        "SEBI turnover fee rates are sourced, but billing aggregation/rounding is unresolved.",
        "GST 18% current taxable bases are observed; full historical effective-date, billing precision and component rounding evidence is incomplete.",
        "Zerodha DP effective history and GST billing treatment are incomplete; CDSL evidence is bounded by the 2026-03-31 manual edition.",
        "Corporate-action completeness and independent historical-bar recovery remain separate readiness blockers.",
    ]
    report = {
        "milestone": "2J-C",
        "report_type": "historical_tariff_evidence_reconciliation",
        "readiness": "BLOCKED",
        "backtest_executed": False,
        "profitability_evaluation": False,
        "profile_version": profile["version"],
        "profile_status": "partial",
        "evidence_scope": "Zerodha resident-individual NSE/BSE cash-equity delivery; available archived evidence plus official content observations with failed local retrievals",
        "component_coverage": {
            "brokerage": {
                "coverage": "no historical effective interval",
                "status": "partially_verified",
            },
            "stt": {
                "coverage": "rate content-supported from 2005-06-01; profile window 2018-01-01 through 2026-10-23",
                "status": "partially_verified",
                "rounding": "unverified",
            },
            "stamp_duty": {
                "coverage": "delivery buyer rate content-supported from 2020-07-01; earlier state-specific schedule not modeled",
                "status": "partially_verified",
                "rounding": "unverified",
            },
            "nse_transaction": {
                "coverage": "2024-10-01 through 2026-10-23; two archived circular intervals",
                "status": "verified_rates_unverified_rounding",
            },
            "bse_transaction": {
                "coverage": "no date-complete instrument-specific schedule",
                "status": "partially_verified; group and monthly turnover unresolved",
            },
            "sebi_turnover": {
                "coverage": "2018-01-01 through 2026-10-23 in documented intervals",
                "status": "verified_rates_unverified_client_rounding",
            },
            "gst": {
                "coverage": "current 18% taxable bases observed; historical applicability/rounding incomplete",
                "status": "partially_verified",
            },
            "zerodha_dp": {
                "coverage": "current charge observed; historical effective interval unavailable",
                "status": "partially_verified",
            },
            "cdsl_dp": {
                "coverage": "2024-10-01 through 2026-03-31 source-edition interval",
                "status": "verified_within_source_edition",
            },
        },
        "nse_ipft_reconciliation": "FA73061 represents exchange transaction charges and IPFT as distinct lines; profile keeps them separate and does not add IPFT a second time to the exchange rate.",
        "bse_dependency": "A current headline BSE rate is not applied as a historical daily rate; date-specific scrip-group/exclusivity and monthly turnover basis remain missing.",
        "rounding_policy": "No fee rounding is inferred from displayed examples. Any unverified rule remains unusable by quote resolver.",
        "retrieval_failures": [
            s for s in sources if s.get("status") == "content_observed_archive_failed"
        ],
        "known_blockers": blockers,
        "independent_readiness_blockers": [
            "historical session/bar evidence",
            "corporate-action coverage and accounting evidence",
        ],
    }
    inventory_rows = []
    effective_dates = {
        "nse_fa64232_2024": "2024-10-01",
        "nse_fa73061_2026": "2026-03-01",
        "cdsl_dp_instructions_2026": "2024-10-01",
        "income_tax_stt_delivery_2005": "2005-06-01",
        "india_stamp_act_schedule_56a": "2020-07-01",
    }
    publication_dates = {
        "bse_master_circular_2023": "2023-06-30",
    }
    for source in sources:
        source_id = source["source_id"]
        publication_date = source.get("publication_date") or publication_dates.get(source_id)
        if source_id in {
            "income_tax_stt_delivery_2005",
            "india_stamp_act_schedule_56a",
            "dea_stamp_duty_implementation_2020",
            "cdsl_dp_instructions_2026",
        }:
            # The known dates are effective dates or document-edition labels, not verified
            # formal publication dates. Keep publication_date unknown in the normalized index.
            publication_date = None
        inventory_rows.append(
            {
                "source_id": source_id,
                "title": source["title"],
                "url": source["url"],
                "publication_date": publication_date,
                "publication_date_status": "unknown" if publication_date is None else "identified",
                "effective_date": source.get("effective_date")
                or effective_dates.get(source["source_id"]),
                "retrieval_timestamp_utc": source.get("retrieved_at_utc"),
                "applicability": source.get("applicability", source.get("note")),
                "archive_file": source.get("archive_file"),
                "sha256": source.get("sha256"),
                "status": source.get("status"),
            }
        )
    write_once(MANIFEST_C, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    write_once(
        INVENTORY,
        json.dumps(
            {"schema_version": "1.0", "sources": inventory_rows},
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    write_once(PROFILE_C, json.dumps(profile, indent=2, sort_keys=True) + "\n")
    write_once(REPORT_DIR / "coverage.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
    md = [
        "# Milestone 2J-C Historical Tariff Evidence Reconciliation",
        "",
        "**Readiness: BLOCKED.** No real-data backtest or profitability evaluation was run.",
        "",
        f"Profile: `{profile['version']}` (partial; fail-closed).",
        "",
        "## Component coverage",
        "",
        *[
            f"- **{name}:** {item['coverage']}; {item['status']}."
            for name, item in report["component_coverage"].items()
        ],
        "",
        "## Source retrieval failures",
        "",
        *[
            f"- `{s['source_id']}` at {s['url']}: {s['error']} No local hash is claimed."
            for s in report["retrieval_failures"]
        ],
        "",
        "## Remaining blockers",
        "",
        *[f"- {item}" for item in blockers],
        "",
        "Archived NSE, BSE, SEBI, Zerodha and CDSL sources retain their earlier fingerprints in the versioned provenance manifest. The 2J-B artifacts were not modified.",
        "",
    ]
    write_once(REPORT_DIR / "readiness.md", "\n".join(md))
    return report


def main() -> None:
    report = build()
    print(
        f"readiness={report['readiness']}; profile={report['profile_version']}; backtest_executed=false"
    )


if __name__ == "__main__":
    main()
