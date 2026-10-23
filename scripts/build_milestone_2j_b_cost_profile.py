"""Build the immutable, evidence-linked partial Zerodha delivery profile for Milestone 2J-B."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "config" / "cost_profiles"
EVIDENCE = ROOT / "data" / "reference" / "cost_profiles" / "milestone_2j_b"


def write_once(path: Path, value: dict) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise FileExistsError(f"refusing to overwrite existing evidence artifact: {path}")
        return
    path.write_text(payload, encoding="utf-8", newline="\n")


def main() -> None:
    archive_root = ROOT / "data" / "reference" / "cost_profiles"
    source_specs = [
        (
            "zerodha_charges",
            "source_archive/zerodha_charges.html",
            "https://zerodha.com/charges",
            "Zerodha charges schedule",
            "2026-10-23T17:34:55.325230+05:30",
        ),
        (
            "zerodha_dp_charges",
            "source_archive/zerodha_dp_charges.html",
            "https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/what-do-dp-charges-mean",
            "Zerodha DP charges",
            "2026-10-23T17:34:55.550979+05:30",
        ),
        (
            "zerodha_gst_sebi",
            "source_archive/zerodha_gst_sebi.html",
            "https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/gst-on-sebi-charges",
            "Zerodha GST and SEBI charges",
            "2026-10-23T17:34:55.656595+05:30",
        ),
        (
            "nse_fa64232_2024",
            "source_archive/nse_fa64232_2024.pdf",
            "https://nsearchives.nseindia.com/content/circulars/FA64232.pdf",
            "NSE circular FA64232",
            "2026-10-23T17:34:55.740536+05:30",
        ),
        (
            "nse_fa73061_2026",
            "source_archive/nse_fa73061_2026.pdf",
            "https://nsearchives.nseindia.com/content/circulars/FA73061.pdf",
            "NSE circular FA73061",
            "2026-10-23T17:34:56.594251+05:30",
        ),
        (
            "sebi_true_to_label_2024",
            "source_archive/sebi_true_to_label_2024.html",
            "https://www.sebi.gov.in/legal/circulars/jul-2024/charges-levied-by-market-infrastructure-institutions-true-to-label_84506.html",
            "SEBI true-to-label circular",
            "2026-10-23T17:34:56.460997+05:30",
        ),
        (
            "sebi_broker_regulations_2025",
            "milestone_2j_b/source_archive/sebi_stock_brokers_regulations_2025-03-10.pdf",
            "https://www.sebi.gov.in/sebi_data/attachdocs/mar-2025/1741147425621.pdf",
            "SEBI Stock Brokers Regulations consolidated 2025-03-10",
            None,
        ),
        (
            "bse_master_circular_2023",
            "milestone_2j_b/source_archive/bse_equity_segment_master_circular_2023-06-30.pdf",
            "https://www.bseindia.com/markets/MarketInfo/DownloadAttach.aspx?attachedId=cb125690-a0f8-452a-ba6b-86cab98004bc&id=20230630-19",
            "BSE equity segment master circular 2023-06-30",
            "2026-10-23T13:03:10.727Z",
        ),
        (
            "cdsl_dp_instructions_2026",
            "milestone_2j_b/source_archive/cdsl_dp_operating_instructions_2026-03-31.pdf",
            "https://www.cdslindia.com/DP/OperatingInstructions.html",
            "CDSL DP Operating Instructions 2026-03-31",
            "2026-10-23T13:03:06.848Z",
        ),
        (
            "income_tax_section_98",
            "",
            "https://www.incometaxindia.gov.in/w/section-98-55",
            "Income Tax Act Section 98",
            "2026-10-23T17:34:56.912892+05:30",
        ),
        (
            "indian_stamp_act_schedule_i",
            "",
            "https://www.indiacode.nic.in/bitstream/123456789/15510/1/a1899-2%20.pdf",
            "India Code Indian Stamp Act Schedule I",
            None,
        ),
    ]
    sources = []
    for source_id, relative, url, title, retrieved in source_specs:
        if relative:
            path = archive_root / relative
            raw = path.read_bytes()
            status, digest = "retrieved_bytes_archived", hashlib.sha256(raw).hexdigest()
            archive_file = (
                relative.removeprefix("milestone_2j_b/")
                if relative.startswith("milestone_2j_b/source_archive/")
                else "../" + relative
            )
            note = "Archived source bytes; source content inspected for the cited component."
            if retrieved is None:
                note += " Retrieval timestamp was not retained."
        else:
            digest, archive_file = None, None
            if source_id == "income_tax_section_98":
                status = "retrieval_failed"
                note = (
                    "Direct archive attempt returned HTTP 403; official page result was "
                    "observed separately; no source bytes or hash."
                )
            elif source_id == "indian_stamp_act_schedule_i":
                status = "retrieval_failed"
                retrieved = "2026-10-23T13:12:36.278764Z"
                note = (
                    "Direct official PDF GET timed out after 30 seconds; search result was "
                    "observed separately; no source bytes or hash."
                )
            else:
                status = "partially_observed_not_archived"
                note = (
                    "Official page content observed in web result; direct source bytes could "
                    "not be archived and validated. Retrieval timestamp was not retained."
                )
        sources.append(
            {
                "source_id": source_id,
                "url": url,
                "title": title,
                "retrieved_at_utc": retrieved,
                "status": status,
                "archive_file": archive_file,
                "sha256": digest,
                "note": note,
            }
        )

    provenance = {
        "schema_version": "1.0",
        "profile_version": "zerodha-resident-individual-delivery-2026-10-partial-v1",
        "purpose": (
            "Evidence registry for a deliberately partial, fail-closed delivery cost model; "
            "not a complete historical tariff."
        ),
        "sources": sources,
    }
    write_once(EVIDENCE / "provenance_manifest.json", provenance)

    rules = []

    def add(
        component,
        category,
        basis,
        sides,
        source,
        *,
        exchange,
        start=None,
        end=None,
        rate=None,
        amount=None,
        aggregation="per_fill",
        status="verified",
        rounding="unverified",
        taxable="unresolved",
        note="",
        holder=None,
        taxable_components=None,
    ):
        rule = {
            "component": component,
            "category": category,
            "basis": basis,
            "aggregation": aggregation,
            "sides": sides,
            "verification_status": status,
            "rounding": rounding,
            "effective_from": start,
            "effective_to": end,
            "source_id": source,
            "minimum_amount": None,
            "cap_amount": None,
            "gst_treatment": taxable,
            "exchange": exchange,
            "segment": "cash_delivery",
            "account_category": "resident_individual",
        }
        if rate is not None:
            rule["rate"] = rate
        if amount is not None:
            rule["fixed_amount"] = amount
        if holder:
            rule["dp_holder_category"] = holder
        if taxable_components:
            rule["taxable_components"] = taxable_components
        if note:
            rule["note"] = note
        rules.append(rule)

    both = ["BUY", "SELL"]
    for exchange in ("NSE", "BSE"):
        add(
            "brokerage",
            "broker",
            "notional",
            both,
            "zerodha_charges",
            exchange=exchange,
            rate="0",
            status="partially_verified",
            note=(
                "Current delivery brokerage is reported as zero; no historical effective "
                "interval and contract-note minimum requires reconciliation."
            ),
        )
        add(
            "stt",
            "statutory",
            "notional",
            both,
            "income_tax_section_98",
            exchange=exchange,
            rate="0.001",
            status="partially_verified",
            note=(
                "Official current Section 98 rate observed; source bytes not archived and "
                "historic schedule/rounding not independently established in this profile."
            ),
        )
        add(
            "sebi_turnover",
            "statutory",
            "notional",
            both,
            "sebi_broker_regulations_2025",
            exchange=exchange,
            start="2018-01-01",
            end="2019-03-31",
            rate="0.0000015",
            note="Cash-segment rate before 2019 substitution; client billing/rounding unresolved.",
        )
        add(
            "sebi_turnover",
            "statutory",
            "notional",
            both,
            "sebi_broker_regulations_2025",
            exchange=exchange,
            start="2019-04-01",
            end="2020-05-31",
            rate="0.000001",
            note="Cash-segment schedule; client billing/rounding unresolved.",
        )
        add(
            "sebi_turnover",
            "statutory",
            "notional",
            both,
            "sebi_broker_regulations_2025",
            exchange=exchange,
            start="2020-06-01",
            end="2021-03-31",
            rate="0.0000005",
            note="Temporary 50% cash-segment fee relief; client billing/rounding unresolved.",
        )
        add(
            "sebi_turnover",
            "statutory",
            "notional",
            both,
            "sebi_broker_regulations_2025",
            exchange=exchange,
            start="2021-04-01",
            end="2026-10-23",
            rate="0.000001",
            note=(
                "Current consolidated schedule through source edition date; client "
                "billing/rounding unresolved."
            ),
        )
        add(
            "stamp_duty",
            "statutory",
            "notional",
            ["BUY"],
            "indian_stamp_act_schedule_i",
            exchange=exchange,
            rate="0.00015",
            status="partially_verified",
            note=(
                "Current delivery rate observed in official consolidated Schedule I search "
                "extract; direct source bytes and effective rule extraction were not "
                "validated for this profile."
            ),
        )
        add(
            "gst_services",
            "tax",
            "component_sum",
            both,
            "zerodha_charges",
            exchange=exchange,
            rate="0.18",
            status="partially_verified",
            taxable="separately_modelled",
            taxable_components=["brokerage", "exchange_transaction", "sebi_turnover", "ipft"],
            note=(
                "Current 18% base reported by Zerodha; historical GST effective dates and "
                "per-component rounding unverified."
            ),
        )
        add(
            "dp_zerodha",
            "depository",
            "fixed",
            ["SELL"],
            "zerodha_dp_charges",
            exchange=exchange,
            amount="9.50",
            aggregation="per_day_symbol",
            status="partially_verified",
            rounding="exact",
            taxable="separately_modelled",
            note="Current Zerodha component reported; no historical effective interval.",
        )
        for holder, amount in (("male_primary", "3.50"), ("female_primary", "3.25")):
            add(
                "dp_cdsl",
                "depository",
                "fixed",
                ["SELL"],
                "cdsl_dp_instructions_2026",
                exchange=exchange,
                start="2024-10-01",
                end="2026-03-31",
                amount=amount,
                aggregation="per_day_symbol",
                rounding="exact",
                taxable="separately_modelled",
                holder=holder,
                note=(
                    "CDSL flat debit charge effective 2024-10-01; female first-holder discount "
                    "applies. Source edition ends 2026-03-31."
                ),
            )
        add(
            "gst_dp",
            "tax",
            "component_sum",
            ["SELL"],
            "zerodha_charges",
            exchange=exchange,
            rate="0.18",
            aggregation="per_day_symbol",
            status="partially_verified",
            rounding="unverified",
            taxable="separately_modelled",
            taxable_components=["dp_zerodha", "dp_cdsl"],
            note=(
                "Current DP GST shown by Zerodha; date coverage and grouped billing rounding "
                "are incomplete."
            ),
        )
    add(
        "exchange_transaction",
        "exchange",
        "notional",
        both,
        "nse_fa64232_2024",
        exchange="NSE",
        start="2024-10-01",
        end="2026-02-28",
        rate="0.0000297",
        note=(
            "NSE cash-market charge, fractional rate from circular; fee rounding basis "
            "not established."
        ),
    )
    add(
        "exchange_transaction",
        "exchange",
        "notional",
        both,
        "nse_fa73061_2026",
        exchange="NSE",
        start="2026-03-01",
        end="2026-10-23",
        rate="0.000030699",
        note="NSE cash-market transaction charge from circular; rounding not established.",
    )
    add(
        "ipft",
        "exchange",
        "notional",
        both,
        "nse_fa73061_2026",
        exchange="NSE",
        start="2026-03-01",
        end="2026-10-23",
        rate="0.000000001",
        note="NSE IPFT charge; rounding not established.",
    )
    add(
        "exchange_transaction",
        "exchange",
        "notional",
        both,
        "zerodha_charges",
        exchange="BSE",
        rate="0.0000375",
        status="partially_verified",
        note=(
            "Current Zerodha snapshot rate only; BSE charges vary with scrip "
            "group/exclusivity and monthly turnover, so a single daily rate is not "
            "sufficient."
        ),
    )
    requirements = []
    component_sides = [
        ("brokerage", both),
        ("stt", both),
        ("exchange_transaction", both),
        ("sebi_turnover", both),
        ("ipft", both),
        ("stamp_duty", ["BUY"]),
        ("gst_services", both),
        ("dp_zerodha", ["SELL"]),
        ("dp_cdsl", ["SELL"]),
        ("gst_dp", ["SELL"]),
    ]
    for name, sides in component_sides:
        exchanges = ["NSE"] if name == "ipft" else ["NSE", "BSE"]
        requirements.append({"component": name, "sides": sides, "exchanges": exchanges})
    profile = {
        "schema_version": "2.0",
        "version": "zerodha-resident-individual-delivery-2026-10-partial-v1",
        "market": "India",
        "segment": "cash_delivery",
        "exchanges": ["NSE", "BSE"],
        "account_category": "resident_individual",
        "status": "partial",
        "synthetic": False,
        "required_components": requirements,
        "rules": rules,
        "assumptions": [
            "This profile is intentionally incomplete and must not produce a total cost quote.",
            "No current rate is extrapolated outside its evidenced interval.",
            "BSE calculation additionally requires historical scrip group/exclusivity and "
            "monthly turnover tariff inputs, not modeled here.",
            "Account-level AMC and optional account fees are excluded; they require an "
            "explicit allocation policy.",
            "Rates do not imply current or historical client billing rounding unless "
            "explicitly verified.",
            "Exact rounding is used only for fixed CDSL tariff amounts; it is not a general "
            "currency rounding claim.",
        ],
        "provenance_manifest": (
            "../../data/reference/cost_profiles/milestone_2j_b/provenance_manifest.json"
        ),
    }
    write_once(OUT / "zerodha_resident_individual_delivery_v2_partial.json", profile)
    print(f"wrote/verified {OUT / 'zerodha_resident_individual_delivery_v2_partial.json'}")


if __name__ == "__main__":
    main()
