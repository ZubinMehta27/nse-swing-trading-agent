"""Archive official cost-source response bytes once; never refresh over evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/reference/cost_profiles/source_archive"
SOURCES = (
    ("zerodha_charges", "https://zerodha.com/charges", "Zerodha charges schedule", "html"),
    (
        "zerodha_dp_charges",
        "https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/what-do-dp-charges-mean",
        "What is a Depository Participant charge?",
        "html",
    ),
    (
        "zerodha_gst_sebi",
        "https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/gst-on-sebi-charges",
        "Why is GST levied on SEBI charges?",
        "html",
    ),
    (
        "nse_fa64232_2024",
        "https://nsearchives.nseindia.com/content/circulars/FA64232.pdf",
        "NSE revision in transaction charges, Circular 5/2024",
        "pdf",
    ),
    (
        "sebi_true_to_label_2024",
        "https://www.sebi.gov.in/legal/circulars/jul-2024/charges-levied-by-market-infrastructure-institutions-true-to-label_84506.html",
        "SEBI Charges levied by Market Infrastructure Institutions – True to Label",
        "html",
    ),
    (
        "nse_fa73061_2026",
        "https://nsearchives.nseindia.com/content/circulars/FA73061.pdf",
        "NSE revision in transaction charges, Circular NSE/FA/73061",
        "pdf",
    ),
    (
        "income_tax_section_98_stt",
        "https://www.incometaxindia.gov.in/w/section-98-55",
        "Income Tax Act, Section 98: charge of securities transaction tax",
        "html",
    ),
    (
        "income_tax_schedule_i_stamp",
        "https://wmstatic-prd.incometaxindia.gov.in/documents/20117/42998/Schedule-I_2025-12-26_10-37-34_3887a9_en.pdf/8ff5be63-a345-31c5-e5ac-cf180a791ffd?download=true&t=1774337765807&version=1.0",
        "Indian Stamp Act Schedule I, consolidated text",
        "pdf",
    ),
    (
        "dea_stamp_implementation_2021",
        "https://www.dea.gov.in/files/annual_reports_documents/Annual_Report_2020_2021_English.pdf",
        "Department of Economic Affairs Annual Report 2020-21",
        "pdf",
    ),
)


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError(
            f"source manifest already exists; refusing to refresh: {manifest_path}"
        )
    entries = []
    for source_id, url, title, expected_type in SOURCES:
        entry = {
            "source_id": source_id,
            "url": url,
            "title": title,
            "retrieved_at_utc": datetime.now(UTC).isoformat(),
            "expected_type": expected_type,
            "status": "retrieval_failed",
            "file": None,
            "sha256": None,
            "error": None,
        }
        try:
            request = Request(
                url, headers={"User-Agent": "nse-swing-agent research source archive"}
            )
            with urlopen(request, timeout=25) as response:
                body = response.read(20_000_001)
                if len(body) > 20_000_000:
                    raise ValueError("source exceeded 20 MB archive limit")
                content_type = response.headers.get("Content-Type", "")
                final_url = response.geturl()
            if not body:
                raise ValueError("empty response body")
            if expected_type == "pdf" and not body.startswith(b"%PDF-"):
                raise ValueError(f"expected PDF bytes, received Content-Type {content_type!r}")
            if (
                expected_type == "html"
                and b"<html" not in body[:4096].lower()
                and b"<!doctype" not in body[:4096].lower()
            ):
                raise ValueError(f"expected HTML document, received Content-Type {content_type!r}")
            filename = f"{source_id}.{'pdf' if expected_type == 'pdf' else 'html'}"
            target = OUT / filename
            if target.exists():
                raise FileExistsError(f"refusing to overwrite source bytes: {target}")
            target.write_bytes(body)
            entry.update(
                {
                    "status": "retrieved_bytes_archived",
                    "file": filename,
                    "sha256": sha256(body),
                    "http_status": 200,
                    "content_type": content_type,
                    "final_url": final_url,
                    "byte_count": len(body),
                    "response_container_validated": True,
                    "content_inspection_status": "not_semantically_validated_by_archiver",
                }
            )
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        entries.append(entry)
        print(f"{source_id}: {entry['status']}; sha256={entry['sha256'] or 'n/a'}")
    payload = {
        "schema_version": "1.0",
        "purpose": "Milestone 2J source evidence; not a complete verified historical tariff",
        "sources": entries,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
