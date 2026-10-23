"""Regenerate the local Milestone 2H readiness evidence; performs no backtest."""

from pathlib import Path

from nse_swing_agent.readiness_evidence import build_milestone_2h


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    report = build_milestone_2h(root)
    print(
        f"{report['decision']}: {report['missing_bars']['count']} official bars reconciled; "
        f"{report['corporate_actions']['source_rows']} action source rows; "
        f"real-data evaluation ready={report['real_data_backtest_ready']}"
    )


if __name__ == "__main__":
    main()
