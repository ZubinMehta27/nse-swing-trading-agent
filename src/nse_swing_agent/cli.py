"""Command line tools for local data validation and offline portfolio backtests."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from .backtest import BacktestConfig, CostSchedule, export_result, run_backtest
from .corporate_actions import load_action_manifest
from .gap_audit import audit_gaps
from .historical_data import DataValidationError, import_to_cache, load_historical_file
from .risk import RiskConfig
from .strategy import StrategyConfig
from .tejhq import TejHQClient, TejHQError, fetch_history


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nse-swing-agent", description="Local historical data and paper backtest tools"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser(
        "validate", help="validate and cache a canonical OHLCV CSV/Parquet file"
    )
    validate.add_argument("input", type=Path)
    validate.add_argument("--cache-dir", type=Path, default=Path("data/cache"))
    validate.add_argument(
        "--source", help="provenance description (for example: NSE bhavcopy URL/report name)"
    )
    fetch = commands.add_parser(
        "fetch-history", help="fetch one explicit NSE symbol/date range from TejHQ"
    )
    fetch.add_argument("--symbol", required=True, help="one NSE equity trading symbol")
    fetch.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    fetch.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    fetch.add_argument("--raw-dir", type=Path, default=Path("data/raw/nse"))
    fetch.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    fetch.add_argument("--timeout", type=float, default=15.0)
    fetch.add_argument("--retries", type=int, default=2)
    gaps = commands.add_parser(
        "audit-gaps", help="audit local bar gaps against an explicit calendar and NSE files"
    )
    gaps.add_argument("observed", type=Path)
    gaps.add_argument(
        "--calendar", type=Path, required=True, help="CSV: session_date,status,source"
    )
    gaps.add_argument(
        "--source-file",
        type=Path,
        action="append",
        default=[],
        help="official NSE CSV/ZIP; repeat per file",
    )
    gaps.add_argument("--output", type=Path, required=True)
    gaps.add_argument("--symbol", default="RELIANCE")
    gaps.add_argument("--isin", default="INE002A01018")
    backtest = commands.add_parser(
        "backtest", help="run a deterministic local daily-bar portfolio backtest"
    )
    backtest.add_argument("input", type=Path)
    backtest.add_argument("--output", type=Path, required=True)
    backtest.add_argument("--cache-dir", type=Path, default=Path("data/cache"))
    backtest.add_argument("--initial-cash", type=Decimal, default=Decimal("1000000"))
    backtest.add_argument("--max-positions", type=int, default=5)
    backtest.add_argument("--max-volume-fraction", type=Decimal, default=Decimal("0.01"))
    backtest.add_argument("--slippage-bps", type=Decimal, default=Decimal("5"))
    backtest.add_argument("--atr-period", type=int, default=14)
    backtest.add_argument("--stop-atr-multiple", type=Decimal, default=Decimal("2"))
    backtest.add_argument("--target-r-multiple", type=Decimal, default=Decimal("3"))
    backtest.add_argument("--risk-fraction", type=Decimal, default=Decimal("0.005"))
    backtest.add_argument("--position-fraction", type=Decimal, default=Decimal("0.20"))
    backtest.add_argument("--sma-fast", type=int, default=50)
    backtest.add_argument("--sma-slow", type=int, default=200)
    backtest.add_argument("--rsi-period", type=int, default=14)
    backtest.add_argument("--rsi-pullback-min", type=Decimal, default=Decimal("40"))
    backtest.add_argument("--rsi-pullback-max", type=Decimal, default=Decimal("60"))
    backtest.add_argument(
        "--start",
        type=date.fromisoformat,
        help="evaluation start YYYY-MM-DD; earlier rows provide warm-up",
    )
    backtest.add_argument("--end", type=date.fromisoformat, help="evaluation end YYYY-MM-DD")
    backtest.add_argument(
        "--costs-json", type=Path, help="JSON mapping CostSchedule field names to versioned rates"
    )
    backtest.add_argument(
        "--cost-inclusive",
        action="store_true",
        help="label this run cost-inclusive; requires a sourced, verified, non-zero dated profile",
    )
    backtest.add_argument("--benchmark-symbol")
    backtest.add_argument(
        "--actions-manifest",
        type=Path,
        help=(
            "reviewed canonical action JSON with complete verified coverage "
            "(required for real symbols)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            summary = import_to_cache(args.input, args.cache_dir, source=args.source)
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "rows": summary.row_count,
                        "symbols": summary.symbol_count,
                        "date_range": [
                            summary.first_date.isoformat(),
                            summary.last_date.isoformat(),
                        ],
                        "fingerprint_sha256": summary.fingerprint,
                        "cache": str(summary.cache_path),
                        "metadata": str(summary.metadata_path),
                    },
                    indent=2,
                )
            )
            return 0
        if args.command == "fetch-history":
            summary = fetch_history(
                args.symbol,
                args.start,
                args.end,
                raw_dir=args.raw_dir,
                processed_dir=args.processed_dir,
                client=TejHQClient(timeout=args.timeout, retries=args.retries),
            )
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "provider": "TejHQ",
                        "symbol": summary.symbol,
                        "requested_date_range": [
                            summary.requested_from.isoformat(),
                            summary.requested_to.isoformat(),
                        ],
                        "actual_date_range": [
                            summary.actual_from.isoformat(),
                            summary.actual_to.isoformat(),
                        ],
                        "rows": summary.row_count,
                        "raw_sha256": summary.raw_sha256,
                        "raw_file": str(summary.raw_path),
                        "normalized_file": str(summary.normalized_path),
                        "provenance": str(summary.provenance_path),
                        "adjustment_status": "raw_unadjusted",
                    },
                    indent=2,
                )
            )
            return 0
        if args.command == "audit-gaps":
            summary = audit_gaps(
                args.observed,
                args.calendar,
                args.source_file,
                args.output,
                symbol=args.symbol,
                isin=args.isin,
            )
            print(json.dumps(summary, indent=2))
            return 0
        records = load_historical_file(args.input)
        summary = import_to_cache(args.input, args.cache_dir)
        if args.output.resolve() == args.input.resolve() or args.input.resolve().is_relative_to(
            args.output.resolve()
        ):
            raise DataValidationError(
                "output directory must not contain or replace the input source file"
            )
        costs = CostSchedule()
        if args.costs_json:
            payload = json.loads(args.costs_json.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise DataValidationError("cost schedule JSON must be an object")
            if payload.get("verification_status") == "verified":
                required_profile_fields = {
                    "effective_from",
                    "effective_to",
                    "source",
                    "brokerage_rate",
                    "stt_buy_rate",
                    "stt_sell_rate",
                    "exchange_rate",
                    "gst_rate",
                    "stamp_buy_rate",
                    "dp_charge_per_share",
                }
                missing_profile_fields = required_profile_fields - payload.keys()
                if missing_profile_fields:
                    raise DataValidationError(
                        "verified cost profile must explicitly record: "
                        + ", ".join(sorted(missing_profile_fields))
                    )
            if "effective_from" in payload:
                payload["effective_from"] = date.fromisoformat(payload["effective_from"])
            if payload.get("effective_to"):
                payload["effective_to"] = date.fromisoformat(payload["effective_to"])
            for name in (
                "brokerage_rate",
                "stt_buy_rate",
                "stt_sell_rate",
                "exchange_rate",
                "gst_rate",
                "stamp_buy_rate",
                "dp_charge_per_share",
            ):
                if name in payload:
                    payload[name] = Decimal(str(payload[name]))
            payload["rates_explicit"] = all(
                name in payload
                for name in (
                    "brokerage_rate",
                    "stt_buy_rate",
                    "stt_sell_rate",
                    "exchange_rate",
                    "gst_rate",
                    "stamp_buy_rate",
                    "dp_charge_per_share",
                )
            )
            costs = CostSchedule(**payload)
        strategy = StrategyConfig(
            args.sma_fast,
            args.sma_slow,
            args.rsi_period,
            args.rsi_pullback_min,
            args.rsi_pullback_max,
        )
        risk = RiskConfig(args.risk_fraction, args.position_fraction)
        config = BacktestConfig(
            initial_cash=args.initial_cash,
            max_positions=args.max_positions,
            max_volume_fraction=args.max_volume_fraction,
            slippage_bps=args.slippage_bps,
            atr_period=args.atr_period,
            stop_atr_multiple=args.stop_atr_multiple,
            target_r_multiple=args.target_r_multiple,
            evaluation_start=args.start,
            evaluation_end=args.end,
            strategy=strategy,
            risk=risk,
            costs=costs,
            cost_inclusive_evaluation=args.cost_inclusive,
        )
        actions, action_coverage = (
            load_action_manifest(args.actions_manifest) if args.actions_manifest else ((), None)
        )
        result = run_backtest(
            records,
            config,
            input_fingerprint=summary.fingerprint,
            benchmark_symbol=args.benchmark_symbol,
            corporate_actions=actions,
            action_coverage=action_coverage,
            synthetic_fixture=(
                not args.actions_manifest
                and args.input.resolve()
                == (Path(__file__).parent / "data" / "synthetic_ohlcv.csv").resolve()
            ),
        )
        result.manifest["cache_metadata"] = str(summary.metadata_path)
        export_result(result, args.output)
        print(
            json.dumps(
                {
                    "status": "complete",
                    "synthetic": result.manifest["synthetic"],
                    "metrics": result.metrics,
                    "warnings": result.warnings,
                    "output": str(args.output.resolve()),
                },
                indent=2,
            )
        )
        return 0
    except (
        DataValidationError,
        TejHQError,
        ValueError,
        TypeError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
