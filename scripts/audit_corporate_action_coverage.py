"""Build a read-only, fingerprinted audit of retained action-feed coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nse_swing_agent.action_coverage import audit_action_coverage, render_markdown


def write_once(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f"refusing to overwrite existing evidence: {path}")
    else:
        path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("reports/milestone_2j_a_v4"))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    registry = root / "reports/milestone_2h/corporate_action_evidence_registry.json"
    registry_data = json.loads(registry.read_text(encoding="utf-8"))
    source_path = root / registry_data["source_response"]["path"]
    if not source_path.resolve().is_relative_to((root / "data/raw/nse").resolve()):
        raise ValueError("action response path in registry must remain under data/raw/nse")
    report = audit_action_coverage(registry, source_path)
    output.mkdir(parents=True, exist_ok=True)
    write_once(
        output / "corporate_action_coverage.json", (json.dumps(report, indent=2) + "\n").encode()
    )
    write_once(output / "corporate_action_coverage.md", render_markdown(report).encode())
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
