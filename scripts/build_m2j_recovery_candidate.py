"""Build an isolated, auditable eight-bar recovery candidate; never merge it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nse_swing_agent.bar_recovery import build_recovery_candidate
from nse_swing_agent.cost_profiles import load_cost_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/validation/recovery_candidates/milestone_2j_v2"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    profile = load_cost_profile(
        root / "config/cost_profiles/zerodha_resident_individual_nse_delivery_hypothetical.json"
    )
    manifest = build_recovery_candidate(
        root=root,
        reconciliation_path=root / "reports/milestone_2h/bar_reconciliation.json",
        provider_path=root
        / "data/processed/tejhq_RELIANCE_2018-01-01_2026-10-23_20261023T103334Z_fd48f50f69.csv",
        readiness_path=root / "reports/milestone_2h/readiness.json",
        action_registry_path=root / "reports/milestone_2h/corporate_action_evidence_registry.json",
        cost_profile=profile,
        output_dir=output,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if manifest["candidate_status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
