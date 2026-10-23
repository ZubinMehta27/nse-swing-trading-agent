"""Compare protected source and earlier evidence hashes with the Milestone 2J baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Recorded before Milestone 2J wrote its new files. This intentionally covers all raw
# NSE files, processed imports, and Milestone 2F–2I report artifacts in the workspace.
BASELINE = dict(
    [
        (
            "data/raw/nse/BhavCopy_NSE_CM_0_0_0_20241101_F_0000.csv.zip",
            "f45f1ee610a8b1f823682e0c19bb2a51286d11175eb4b0f1194318394cde9b7c",
        ),
        (
            "data/raw/nse/BhavCopy_NSE_CM_0_0_0_20260605_F_0000.csv.zip",
            "120156b35ac42eace0520882dd2efb376265f2e26139a7d6f32521074a6db903",
        ),
        (
            "data/raw/nse/BhavCopy_NSE_CM_0_0_0_20260615_F_0000.csv.zip",
            "19be8fb43a2c5d67e5ebb00e136141e1fadded8312394186e9d6096e370572ba",
        ),
        (
            "data/raw/nse/BhavCopy_NSE_CM_0_0_0_20260616_F_0000.csv.zip",
            "2200b17310b6ecdc43ddc7fc1bbb500248b86f214919a590d42e385ff6491f2c",
        ),
        (
            "data/raw/nse/BhavCopy_NSE_CM_0_0_0_20260622_F_0000.csv.zip",
            "ea7428e0e2600e9106a6c3545698e0905c2fe164632eb017188ca4a417b905c7",
        ),
        (
            "data/raw/nse/cm04NOV2021bhav.csv.zip",
            "3c6b0e631b0ff18946537ba98dd78a4307a9fbc60d70c85e8e529e8acd1de1d8",
        ),
        (
            "data/raw/nse/cm07NOV2018bhav.csv.zip",
            "34cb7742d962b69efaf6da9606dbd0386a0361c884bddfc63c3248a4d9c2b939",
        ),
        (
            "data/raw/nse/cm24OCT2022bhav.csv.zip",
            "c8aa044e671cdb4dd8d2f312d3894a30a3201d8bc17287963a88c937fcb8c208",
        ),
        (
            "data/raw/nse/NSE_CMTR36475_2018_holidays.pdf",
            "d80ac64d32806f9ada629bc96ba91c6d85546dfde405f4468bbfcb194fdb22fb",
        ),
        (
            "data/raw/nse/NSE_CMTR46623_2021_holidays.pdf",
            "3c922e234ad2cbe8320cc34507e281477e0ce273ba9ee39d73da2a49d5629add",
        ),
        (
            "data/raw/nse/NSE_CMTR54023_2022_muhurat.pdf",
            "01e579eac8e2dd4a870a9ebc9f08d60bc26fae28d0d35cf58891bf2a2964e0c7",
        ),
        (
            "data/raw/nse/NSE_CMTR64628_2024_muhurat.pdf",
            "dd1b8bc34a4b3c2900002341c41e4b8f165af862a74fd2a5bfb1355b0afec4a8",
        ),
        (
            "data/raw/nse/nse_holiday_master_trading_2018_20261023.json",
            "ed7315abded78e4a64bdb40545613eb08a29ee5c8a5a2d4167d8d93c0abf4eea",
        ),
        (
            "data/raw/nse/nse_holiday_master_trading_2019_20261023.json",
            "df86d24932c3ea1ad5b4d76cf0ebec2aab1f70403296555e15a0d541fed5183c",
        ),
        (
            "data/raw/nse/nse_holiday_master_trading_2020_20261023.json",
            "592f334da08629c3a18d870f644288638d259502b96b8845ae656734de2914cf",
        ),
        (
            "data/raw/nse/nse_holiday_master_trading_2021_20261023.json",
            "1cd27065bf5d8be5b6e8c6efbe2cc6857df569a4394d2779b77b91572f67a03b",
        ),
        (
            "data/raw/nse/nse_holiday_master_trading_2022_20261023.json",
            "911c09514539c033ca8528d33a86733743af1a2ec2e3dab5533ecfcab1bc54e2",
        ),
        (
            "data/raw/nse/nse_holiday_master_trading_2023_20261023.json",
            "78a76bf4ea030e1c294ed9acd6255875d1eae4027bf9ea35ca5b5357e1b73797",
        ),
        (
            "data/raw/nse/nse_holiday_master_trading_2024_20261023.json",
            "362ccb232694b28865d1f0e61af3cc3df04e713ccb1769fc2b3bd19aa6614e20",
        ),
        (
            "data/raw/nse/nse_holiday_master_trading_retrieved_20261023.json",
            "933cf5dc6dd4efe3b8db8ce6ecd6ecb2582929f5e0b4faffdb88e11cf4efdfbe",
        ),
        (
            "data/raw/nse/tejhq_actions_RELIANCE_20261023T103451Z_4b305e0765.json",
            "4b305e0765bd8a1b0e32ee4074d7343c81cefd99e8231e1275a9e793952bf777",
        ),
        (
            "data/raw/nse/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.json",
            "fd48f50f69338ee1f9b705bd889af7e7f0c8767751dfa0ab5126be6c7e502633",
        ),
        (
            "data/raw/nse/tejhq_RELIANCE_2025-01-01_2025-01-10_20261023T102442Z_e6f86fafcf.json",
            "e6f86fafcf0763c3cb91bdf2afe093371f4ec9d14f59930689dfb106b24e0e2d",
        ),
        (
            "data/raw/nse/tejhq_status_20261023T103747Z_566af175d4.json",
            "566af175d4e2e1366311db508f3b8cba8c083be6a65d3797c8005f6714dfd991",
        ),
        (
            "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv",
            "916a10c4b0ad0fe856f3d78aad94374563dbbfb71f123eacf2e4114dfd94a045",
        ),
        (
            "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.json",
            "aca70c5f6ccfceb3ab197677e2cfc2e8334343772649e31e8367b09af45ed825",
        ),
        (
            "data/processed/tejhq_RELIANCE_2025-01-01_2025-01-10_20261023T102442Z_e6f86fafcf.csv",
            "fd8ec8362afb925d98a4d1b956a285b1a7a6e422f4d84d3303c23e721e9a157b",
        ),
        (
            "data/processed/tejhq_RELIANCE_2025-01-01_2025-01-10_20261023T102442Z_e6f86fafcf.json",
            "ff1560b22ec75e167c339d9816a153712d1dfd13aaae36f9db1d4b14286abeff",
        ),
        (
            "reports/milestone_2f/readiness.json",
            "5a96a0f31d8133f0001b96135d8e041fd794975062aa878a1938b72454bd65f9",
        ),
        (
            "reports/milestone_2f/readiness.md",
            "8d514514b1594ba7b771e7b6a91222d0bf81a6c02517f42d6ea8541345e930b0",
        ),
        (
            "reports/milestone_2f/recovery_manifest.json",
            "78bddb6fd7edb1923316e8892eaf9304adc5a5e57e8f6f3c359e0c6768c0661d",
        ),
        (
            "reports/milestone_2f/audit-2018-2024/gap_audit.csv",
            "00d683d2d67d79b757bcf3fc4e7f23227645e3aa24bd1d509fefba401f41f764",
        ),
        (
            "reports/milestone_2f/audit-2018-2024/gap_audit.json",
            "8971852d80b87533b560c3be5eafbf5990f3a18ef2d664dd079f62dbc7a7a062",
        ),
        (
            "reports/milestone_2f/audit-2018-2024/gap_audit.md",
            "6ef6f4749ad651c074e063868bc0bb3730c283b1e1f59553ec93a40d02fe79b5",
        ),
        (
            "reports/milestone_2g_corporate_action_audit.json",
            "9d9c816360416f1e12c911e340010b33c07260069361030cf2d0c9ac3b8475d2",
        ),
        (
            "reports/milestone_2g_readiness.md",
            "bda483c5f0df569a5102bc238935d42ed9c64fbe9cb2cc7fb41047da812152d0",
        ),
        (
            "reports/milestone_2h/bar_reconciliation.csv",
            "460f1555fea3ef3c8de66128e1de76c865202a70c54de35a09321da3b6ef3dfa",
        ),
        (
            "reports/milestone_2h/bar_reconciliation.json",
            "28ef9f8554dbd00a54877bab5571e9bbc665b7533db0c2181a064922a54e2134",
        ),
        (
            "reports/milestone_2h/corporate_action_evidence_registry.json",
            "208eb5dddd8ef2c1161aca0a0d9e29a50eab5ad628c30f800c6463b8397b4592",
        ),
        (
            "reports/milestone_2h/cost_schedule_evidence.json",
            "3d14c934c1bc3f31a2999f503844c8bf0854d3fab4f6c33016102dbaa05ea3d1",
        ),
        (
            "reports/milestone_2h/readiness.json",
            "73996bc13bcd526ef3663bc355eff01c0dbbd6447f43d00a2094514785ec166a",
        ),
        (
            "reports/milestone_2h/readiness.md",
            "7a1ac8a8b31fc861ebb2d4b4f1944f1985d825577841bf01ce0603ea10169544",
        ),
        (
            "reports/milestone_2i/validation_report.json",
            "0eeed26c54e2bcb69a9226f19b9b07ae3fcd48d453d60e2a5ada2d52f87bd54c",
        ),
        (
            "reports/milestone_2i/validation_report.md",
            "9c1bbe9cba61ea8c8aabf5c6117d43ae0ae1589cc9eb55edae479f69e584f92c",
        ),
    ]
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "reports/milestone_2j/evidence_integrity.json"
    )
    args = parser.parse_args()
    results = []
    for relative, expected in BASELINE.items():
        path = ROOT / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        results.append(
            {
                "path": relative,
                "baseline_sha256": expected,
                "current_sha256": actual,
                "unchanged": actual == expected,
            }
        )
    report = {
        "schema_version": "1.0",
        "baseline_scope": "all raw NSE and processed files plus enumerated 2F-2I evidence",
        "checked_file_count": len(results),
        "unchanged_file_count": sum(item["unchanged"] for item in results),
        "all_unchanged": all(item["unchanged"] for item in results),
        "files": results,
    }
    content = (json.dumps(report, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != content:
        raise FileExistsError(f"refusing to overwrite different integrity report: {args.output}")
    if not args.output.exists():
        args.output.write_bytes(content)
    print(
        f"{report['unchanged_file_count']}/{report['checked_file_count']} protected files unchanged"
    )
    return 0 if report["all_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
