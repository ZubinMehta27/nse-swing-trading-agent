import csv
import json
from datetime import UTC, date, datetime
from decimal import Decimal as D
from pathlib import Path

import pytest

from nse_swing_agent.backtest import (
    BacktestConfig,
    CostSchedule,
    _metrics,
)
from nse_swing_agent.backtest import (
    run_backtest as _run_backtest,
)
from nse_swing_agent.cli import main
from nse_swing_agent.corporate_actions import ActionCoverage
from nse_swing_agent.historical_data import (
    DataValidationError,
    HistoricalBar,
    _parse_date,
    import_to_cache,
    load_historical_file,
)
from nse_swing_agent.models import OHLCVBar
from nse_swing_agent.risk import RiskConfig
from nse_swing_agent.strategy import StrategyConfig

FIELDS = ["symbol", "session_date", "open", "high", "low", "close", "volume"]


def write_rows(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(FIELDS)
        writer.writerows(rows)
    return path


def rising_records(
    *,
    second_symbol: bool = False,
    day5: tuple[str, str, str, str] | None = None,
    volume: int = 100000,
    entry_open: str = "13.5",
) -> list[HistoricalBar]:
    rows: list[list[str]] = []
    for index, close_value in enumerate(["10", "11", "12", "13", "14", "15"]):
        open_value = str(D(close_value) - D("0.1"))
        high, low = str(D(close_value) + D("0.5")), str(D(close_value) - D("0.5"))
        if index == 3:
            open_value = entry_open
            high = str(max(D(high), D(open_value)))
            low = str(min(D(low), D(open_value)))
        if index == 5 and day5:
            open_value, high, low, close_value = day5
        rows.append(
            [
                "AAA",
                date(2025, 1, 1).fromordinal(date(2025, 1, 1).toordinal() + index).isoformat(),
                open_value,
                high,
                low,
                close_value,
                str(volume),
            ]
        )
    if second_symbol:
        rows = [row[:] for row in rows] + [
            ["BBB", row[1], row[2], row[3], row[4], row[5], row[6]] for row in rows
        ]
    return load_rows_in_memory(rows)


def load_rows_in_memory(rows: list[list[str]]) -> list[HistoricalBar]:
    # Build model records without a filesystem round trip for focused execution tests.
    records = []
    for symbol, day, open_, high, low, close, volume in rows:
        session = date.fromisoformat(day)
        stamp = datetime.fromisoformat(f"{day}T15:30:00+05:30")
        records.append(
            HistoricalBar(
                OHLCVBar(symbol, stamp, D(open_), D(high), D(low), D(close), int(volume)), session
            )
        )
    return sorted(records, key=lambda item: (item.session_date, item.bar.symbol))


def run_backtest(records, config=None, **kwargs):
    # These hand-built unit series are explicit complete toy datasets, not market history.
    kwargs.setdefault(
        "action_coverage",
        ActionCoverage(
            min(item.session_date for item in records),
            max(item.session_date for item in records),
            True,
            True,
            "synthetic unit-test action fixture",
            "0" * 64,
        ),
    )
    return _run_backtest(records, config, **kwargs)


def config(**kwargs: object) -> BacktestConfig:
    values = dict(
        initial_cash=D("100000"),
        max_positions=5,
        max_volume_fraction=D("0.01"),
        slippage_bps=D("10"),
        atr_period=2,
        stop_atr_multiple=D("2"),
        target_r_multiple=D("3"),
        strategy=StrategyConfig(2, 3, 2, D(100), D(100)),
        risk=RiskConfig(D("0.01"), D("0.5")),
    )
    values.update(kwargs)
    return BacktestConfig(**values)


def test_csv_schema_sort_timezone_cache_and_source_preserved(tmp_path: Path) -> None:
    source = tmp_path / "history.csv"
    write_rows(
        source,
        [
            ["BBB", "2025-01-03", "11", "12", "10", "11", "20"],
            ["AAA", "2025-01-02", "10", "11", "9", "10", "30"],
        ],
    )
    before = source.read_bytes()
    records = load_historical_file(source)
    assert [(x.session_date, x.bar.symbol) for x in records] == [
        (date(2025, 1, 2), "AAA"),
        (date(2025, 1, 3), "BBB"),
    ]
    assert records[0].bar.timestamp.isoformat() == "2025-01-02T15:30:00+05:30"
    result = import_to_cache(source, tmp_path / "cache", source="local synthetic test")
    assert source.read_bytes() == before
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["schema_version"] == "1.0"
    assert metadata["row_count"] == 2 and metadata["source"] == "local synthetic test"
    assert result.cache_path.exists()


def test_timezone_aware_parquet_datetime_normalizes_to_ist_session_date() -> None:
    assert _parse_date(datetime(2025, 1, 1, 20, tzinfo=UTC), 1) == date(2025, 1, 2)


@pytest.mark.parametrize(
    "rows, message",
    [
        (
            [
                ["AAA", "2025-01-01", "10", "11", "9", "10", "1"],
                ["AAA", "2025-01-01", "10", "11", "9", "10", "1"],
            ],
            "duplicate",
        ),
        ([["AAA", "2025-01-01", "", "11", "9", "10", "1"]], "missing values"),
        ([["AAA", "not-a-date", "10", "11", "9", "10", "1"]], "invalid session_date"),
        ([["AAA", "2025-01-01", "10", "9", "8", "10", "1"]], "inconsistent"),
        ([["AAA", "2025-01-01", "0", "11", "0", "10", "1"]], "positive"),
        ([["AAA", "2025-01-01", "10", "11", "9", "10", "-1"]], "nonnegative integer"),
        ([["AAA", "2025-01-01", "oops", "11", "9", "10", "1"]], "invalid open"),
    ],
)
def test_csv_rejects_invalid_rows(tmp_path: Path, rows: list[list[str]], message: str) -> None:
    source = write_rows(tmp_path / "bad.csv", rows)
    with pytest.raises(DataValidationError, match=message):
        load_historical_file(source)


def test_csv_rejects_missing_or_unknown_columns(tmp_path: Path) -> None:
    source = tmp_path / "schema.csv"
    source.write_text(
        "symbol,session_date,open,close,volume\nAAA,2025-01-01,1,1,1\n", encoding="utf-8"
    )
    with pytest.raises(DataValidationError, match="missing columns"):
        load_historical_file(source)
    source.write_text(",".join([*FIELDS, "surprise"]) + "\n", encoding="utf-8")
    with pytest.raises(DataValidationError, match="unknown columns"):
        load_historical_file(source)


def test_signal_fills_only_after_signal_session_and_reproducible() -> None:
    records = rising_records()
    result_a = run_backtest(records, config())
    result_b = run_backtest(records, config())
    assert result_a == result_b
    buy = next(
        entry for entry in result_a.ledger if entry.side == "BUY" and entry.status == "filled"
    )
    assert buy.session_date > date(2025, 1, 3)  # first signal is computed after Jan 3 close
    assert buy.session_date == date(2025, 1, 4)
    assert buy.price > D("13.5")  # next session open plus adverse slippage
    assert any(
        item.status == "pending" and item.session_date < buy.session_date
        for item in result_a.ledger
    )


def test_backtest_rejects_shuffled_history() -> None:
    with pytest.raises(ValueError, match="chronologically sorted"):
        run_backtest(list(reversed(rising_records())), config())


def test_future_bars_do_not_change_earlier_entry() -> None:
    a = run_backtest(rising_records(), config())
    modified = rising_records(day5=("15", "15.5", "8", "10"))
    b = run_backtest(modified, config())
    entry_a = next(item for item in a.ledger if item.side == "BUY")
    entry_b = next(item for item in b.ledger if item.side == "BUY")
    assert (entry_a.session_date, entry_a.price, entry_a.quantity) == (
        entry_b.session_date,
        entry_b.price,
        entry_b.quantity,
    )


def test_opening_gap_stop_and_intraday_stop_use_adverse_slippage() -> None:
    gap = run_backtest(rising_records(day5=("9", "10", "8.5", "9.5")), config())
    trade = gap.trades[0]
    assert trade.exit_reason == "stop_gap"
    assert trade.exit_price < D("9")
    touch = run_backtest(rising_records(day5=("12", "13", "8.5", "12")), config())
    assert touch.trades[0].exit_reason == "stop_touch"
    assert touch.trades[0].exit_price < D("10")


def test_ambiguous_stop_and_target_uses_conservative_stop() -> None:
    result = run_backtest(rising_records(day5=("14", "30", "9", "15")), config())
    assert result.trades[0].exit_reason == "stop_touch"
    target_only = run_backtest(rising_records(day5=("14", "30", "12", "15")), config())
    assert target_only.trades[0].exit_reason == "target_touch"


def test_volume_and_cash_rejections_and_multisymbol_position_cap() -> None:
    no_volume = run_backtest(rising_records(volume=10), config())
    assert any(
        item.status == "rejected" and item.reason == "volume cap" for item in no_volume.ledger
    )
    costly_gap = run_backtest(rising_records(entry_open="500"), config())
    assert any(item.status == "rejected" and "cash" in item.reason for item in costly_gap.ledger)
    stopped_gap = run_backtest(rising_records(entry_open="8"), config())
    assert any(item.status == "rejected" and "below" in item.reason for item in stopped_gap.ledger)
    multi = run_backtest(rising_records(second_symbol=True), config(max_positions=1))
    assert max(point["open_positions"] for point in multi.equity_curve) <= 1


def test_cost_components_are_deducted_once_per_fill() -> None:
    costs = CostSchedule(
        version="test",
        effective_from=date(2025, 1, 1),
        brokerage_rate=D("0.001"),
        stt_buy_rate=D("0.002"),
        stt_sell_rate=D("0.003"),
        exchange_rate=D("0.0005"),
        gst_rate=D("0.18"),
        stamp_buy_rate=D("0.001"),
        dp_charge_per_share=D("0.10"),
    )
    result = run_backtest(rising_records(day5=("9", "10", "8", "9")), config(costs=costs))
    trade = result.trades[0]
    fills = [entry for entry in result.ledger if entry.status == "filled"]
    assert trade.costs == sum((entry.cost for entry in fills), D(0))
    assert trade.net_pnl == trade.gross_pnl - trade.costs
    assert result.metrics["transaction_costs"] == str(trade.costs)


def test_metrics_drawdown_no_trades_and_zero_variance_edges() -> None:
    empty_trades = []
    no_trade = _metrics(
        [{"date": date(2025, 1, i), "equity": D(100), "open_positions": 0} for i in (1, 2, 3)],
        empty_trades,
        [],
        D(100),
        0,
        None,
    )
    assert no_trade["max_drawdown"] == 0
    assert no_trade["win_rate"] is None and no_trade["profit_factor"] is None
    assert no_trade["sharpe_annualized"] is None and no_trade["sortino_annualized"] is None
    drawdown = _metrics(
        [
            {"date": date(2025, 1, i), "equity": D(value), "open_positions": 0}
            for i, value in zip((1, 2, 3), (100, 120, 90), strict=True)
        ],
        [],
        [],
        D(100),
        0,
        None,
    )
    assert drawdown["max_drawdown"] == pytest.approx(0.25)


def test_missing_and_corporate_action_limits_are_reported() -> None:
    records = rising_records(second_symbol=True)
    records = [
        item
        for item in records
        if not (item.bar.symbol == "BBB" and item.session_date == date(2025, 1, 3))
    ]
    result = run_backtest(records, config())
    assert any("different/missing session" in warning for warning in result.warnings)
    assert any("corporate-action" in warning for warning in result.warnings)


def test_chronological_evaluation_uses_prior_warmup_and_benchmark_is_report_only() -> None:
    stock = rising_records()
    benchmark = [
        HistoricalBar(
            OHLCVBar(
                "INDEX",
                item.bar.timestamp,
                item.bar.open * D(2),
                item.bar.high * D(2),
                item.bar.low * D(2),
                item.bar.close * D("2"),
                item.bar.volume,
            ),
            item.session_date,
        )
        for item in stock
    ]
    records = sorted(stock + benchmark, key=lambda item: (item.session_date, item.bar.symbol))
    result = run_backtest(
        records,
        config(evaluation_start=date(2025, 1, 4), evaluation_end=date(2025, 1, 6)),
        benchmark_symbol="INDEX",
    )
    assert all(item.symbol != "INDEX" for item in result.ledger)
    assert all(point["date"] >= date(2025, 1, 4) for point in result.equity_curve)
    assert result.metrics["benchmark_return"] == pytest.approx(15 / 13 - 1)


def test_export_cli_and_synthetic_label(tmp_path: Path) -> None:
    source = Path(__file__).parents[1] / "src" / "nse_swing_agent" / "data" / "synthetic_ohlcv.csv"
    cache = tmp_path / "cache"
    assert main(["validate", str(source), "--cache-dir", str(cache)]) == 0
    output = tmp_path / "results"
    code = main(["backtest", str(source), "--output", str(output)])
    assert code == 0
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))["synthetic"] is True
    assert (output / "equity_curve.csv").exists()
    assert (output / "trades.csv").exists()
    assert (output / "corporate_actions.csv").exists()
    assert (output / "metrics.json").exists()


def test_cost_schedule_effective_date_is_enforced() -> None:
    with pytest.raises(ValueError, match="not effective"):
        CostSchedule(version="later", effective_from=date(2026, 1, 1)).calculate(
            side="BUY", notional=D(100), quantity=1, session=date(2025, 1, 1)
        )


def test_adjusted_series_is_blocked_without_execution_price_conversion():
    records = rising_records()
    adjusted = [
        HistoricalBar(item.bar, item.session_date, adjustment_policy="provider_adjusted_close_only")
        for item in records
    ]
    with pytest.raises(ValueError, match="only raw_unadjusted"):
        run_backtest(adjusted, config())
    adjusted_benchmark = [
        HistoricalBar(
            OHLCVBar(
                "INDEX",
                item.bar.timestamp,
                item.bar.open,
                item.bar.high,
                item.bar.low,
                item.bar.close,
                item.bar.volume,
            ),
            item.session_date,
            adjustment_policy="provider_adjusted_close_only",
        )
        for item in records
    ]
    with pytest.raises(ValueError, match="only raw_unadjusted"):
        combined = sorted(
            records + adjusted_benchmark,
            key=lambda item: (item.session_date, item.bar.symbol),
        )
        run_backtest(combined, config(), benchmark_symbol="INDEX")


def test_cost_inclusive_requires_verified_sourced_nonzero_profile_and_date_coverage():
    records = rising_records()
    with pytest.raises(ValueError, match="verified, sourced, non-zero"):
        run_backtest(records, config(cost_inclusive_evaluation=True))

    verified = CostSchedule(
        version="test-verified-costs",
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 1, 6),
        source="documented synthetic unit-test schedule",
        verification_status="verified",
        rates_explicit=True,
        brokerage_rate=D("0.001"),
    )
    result = run_backtest(records, config(cost_inclusive_evaluation=True, costs=verified))
    assert result.manifest["cost_profile"]["cost_inclusive_evaluation"] is True
    expired = CostSchedule(
        version="too-short",
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 1, 5),
        source="documented synthetic unit-test schedule",
        verification_status="verified",
        rates_explicit=True,
        brokerage_rate=D("0.001"),
    )
    with pytest.raises(ValueError, match="do not cover"):
        run_backtest(records, config(cost_inclusive_evaluation=True, costs=expired))


def test_cli_rejects_verified_cost_profile_missing_explicit_rate_fields(tmp_path: Path, capsys):
    source = Path(__file__).parents[1] / "src" / "nse_swing_agent" / "data" / "synthetic_ohlcv.csv"
    profile = tmp_path / "verified.json"
    profile.write_text(
        json.dumps(
            {
                "version": "incomplete",
                "effective_from": "2020-01-01",
                "effective_to": None,
                "source": "test source",
                "verification_status": "verified",
                "brokerage_rate": "0.001",
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "backtest",
                str(source),
                "--output",
                str(tmp_path / "out"),
                "--costs-json",
                str(profile),
                "--cost-inclusive",
            ]
        )
        == 2
    )
    assert "explicitly record" in capsys.readouterr().err
