"""Reproducible daily portfolio simulation with explicit next-session execution rules."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from .corporate_actions import (
    ActionCoverage,
    ActionKind,
    CorporateAction,
    DividendReceivable,
    split_quantity,
    unsupported_action_reason,
    validate_actions,
)
from .cost_profiles import CostProfile, CostTransaction
from .historical_data import HistoricalBar
from .indicators import atr
from .models import OHLCVBar, PortfolioState, Position, ProposedOrder, TradeSignal
from .risk import RiskConfig, size_order
from .strategy import StrategyConfig, generate_signals

D = Decimal


@dataclass(frozen=True, slots=True)
class CostSchedule:
    """Date-scoped user cost profile; defaults are unverified zero-cost assumptions."""

    version: str = "user-supplied-zero-v1"
    effective_from: date = date(1900, 1, 1)
    effective_to: date | None = None
    source: str = ""
    verification_status: str = "unverified"
    rates_explicit: bool = False
    brokerage_rate: Decimal = D("0")
    stt_buy_rate: Decimal = D("0")
    stt_sell_rate: Decimal = D("0")
    exchange_rate: Decimal = D("0")
    gst_rate: Decimal = D("0")
    stamp_buy_rate: Decimal = D("0")
    dp_charge_per_share: Decimal = D("0")

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("cost schedule version is required")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("cost profile effective_to must be on or after effective_from")
        if self.verification_status not in {"unverified", "verified", "synthetic_test_only"}:
            raise ValueError(
                "verification_status must be unverified, verified, or synthetic_test_only"
            )
        if self.verification_status == "verified" and not self.source.strip():
            raise ValueError("verified cost profiles require a source citation")
        for name in (
            "brokerage_rate",
            "stt_buy_rate",
            "stt_sell_rate",
            "exchange_rate",
            "gst_rate",
            "stamp_buy_rate",
            "dp_charge_per_share",
        ):
            value = getattr(self, name)
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        for name in (
            "brokerage_rate",
            "stt_buy_rate",
            "stt_sell_rate",
            "exchange_rate",
            "gst_rate",
            "stamp_buy_rate",
        ):
            if getattr(self, name) > 1:
                raise ValueError(f"{name} must be a fraction no greater than 1")

    def calculate(self, *, side: str, notional: Decimal, quantity: int, session: date) -> Decimal:
        if session < self.effective_from:
            raise ValueError(f"cost schedule {self.version} is not effective for {session}")
        if self.effective_to is not None and session > self.effective_to:
            raise ValueError(f"cost schedule {self.version} expired before {session}")
        brokerage = notional * self.brokerage_rate
        exchange = notional * self.exchange_rate
        stt = notional * (self.stt_buy_rate if side == "BUY" else self.stt_sell_rate)
        stamp = notional * self.stamp_buy_rate if side == "BUY" else D(0)
        dp = self.dp_charge_per_share * quantity if side == "SELL" else D(0)
        gst = (brokerage + exchange) * self.gst_rate
        return brokerage + exchange + stt + stamp + dp + gst


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    initial_cash: Decimal = D("1000000")
    max_positions: int = 5
    max_volume_fraction: Decimal = D("0.01")
    slippage_bps: Decimal = D("5")
    atr_period: int = 14
    stop_atr_multiple: Decimal = D("2")
    target_r_multiple: Decimal = D("3")
    evaluation_start: date | None = None
    evaluation_end: date | None = None
    strategy: StrategyConfig = StrategyConfig()
    risk: RiskConfig = RiskConfig()
    costs: CostSchedule = CostSchedule()
    cost_inclusive_evaluation: bool = False
    cost_profile: CostProfile | None = None
    cost_exchange: str | None = None
    cost_account_category: str | None = None
    cost_dp_holder_category: str | None = None

    def __post_init__(self) -> None:
        if self.initial_cash <= 0 or self.max_positions <= 0:
            raise ValueError("initial_cash and max_positions must be positive")
        if not D(0) < self.max_volume_fraction <= D(1):
            raise ValueError("max_volume_fraction must be in (0, 1]")
        if self.slippage_bps < 0 or self.slippage_bps >= D(10000):
            raise ValueError("slippage_bps must be in [0, 10000)")
        if self.atr_period <= 0 or self.stop_atr_multiple <= 0 or self.target_r_multiple <= 0:
            raise ValueError("slippage must be nonnegative and stop/target multiples positive")
        if (
            self.evaluation_start
            and self.evaluation_end
            and self.evaluation_start > self.evaluation_end
        ):
            raise ValueError("evaluation_start must be on or before evaluation_end")
        if self.cost_profile is not None and not self.cost_inclusive_evaluation:
            raise ValueError("a versioned CostProfile requires cost_inclusive_evaluation=True")
        if self.cost_exchange is not None and self.cost_exchange not in {"NSE", "BSE"}:
            raise ValueError("cost_exchange must be NSE or BSE")


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    order_id: str
    symbol: str
    side: str
    session_date: date
    quantity: int
    price: Decimal
    notional: Decimal
    cost: Decimal
    status: str
    reason: str = ""
    cost_breakdown: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    symbol: str
    entry_date: date
    exit_date: date
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    exit_reason: str


@dataclass(frozen=True, slots=True)
class BacktestResult:
    equity_curve: tuple[dict[str, Any], ...]
    trades: tuple[ClosedTrade, ...]
    ledger: tuple[LedgerEntry, ...]
    metrics: dict[str, Any]
    manifest: dict[str, Any]
    warnings: tuple[str, ...]
    corporate_action_ledger: tuple[dict[str, Any], ...] = ()


@dataclass(slots=True)
class _OpenPosition:
    symbol: str
    quantity: int
    entry_date: date
    entry_price: Decimal
    stop: Decimal
    target: Decimal
    entry_cost: Decimal
    order_id: str


def _slipped(price: Decimal, side: str, bps: Decimal) -> Decimal:
    factor = D(1) + bps / D(10000) if side == "BUY" else D(1) - bps / D(10000)
    result = price * factor
    if result <= 0:
        raise ValueError("slippage parameters produce a nonpositive execution price")
    return result


def _execution_cost(
    config: BacktestConfig,
    *,
    transaction_id: str,
    order_id: str,
    symbol: str,
    side: str,
    session: date,
    notional: Decimal,
    quantity: int,
) -> tuple[Decimal, dict[str, Any] | None]:
    """Resolve a fill cost from the versioned profile, or use toy legacy config."""
    if config.cost_profile is None:
        return (
            config.costs.calculate(
                side=side, notional=notional, quantity=quantity, session=session
            ),
            None,
        )
    if not config.cost_exchange or not config.cost_account_category:
        raise ValueError("versioned cost profile requires explicit exchange and account category")
    breakdown = config.cost_profile.quote(
        [
            CostTransaction(
                transaction_id,
                session,
                symbol,
                side,
                notional,
                quantity,
                order_id=order_id,
                exchange=config.cost_exchange,
                segment="cash_delivery",
                account_category=config.cost_account_category,
                dp_holder_category=config.cost_dp_holder_category,
            )
        ]
    )
    return breakdown.total, breakdown.as_dict()


def _metrics(
    curve: list[dict[str, Any]],
    trades: list[ClosedTrade],
    ledger: list[LedgerEntry],
    initial_cash: Decimal,
    exposure_days: int,
    benchmark_return: Decimal | None,
) -> dict[str, Any]:
    end_equity = curve[-1]["equity"] if curve else initial_cash
    elapsed_days = (curve[-1]["date"] - curve[0]["date"]).days if len(curve) > 1 else 0
    total_return = end_equity / initial_cash - 1
    cagr = (
        float((end_equity / initial_cash) ** (D(365) / D(elapsed_days)) - 1)
        if elapsed_days > 0 and end_equity > 0
        else None
    )
    peak = initial_cash
    max_dd = D(0)
    for point in curve:
        equity = point["equity"]
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    returns = [
        float(curve[i]["equity"] / curve[i - 1]["equity"] - 1)
        for i in range(1, len(curve))
        if curve[i - 1]["equity"] > 0
    ]
    mean = sum(returns) / len(returns) if returns else 0.0
    std = (
        math.sqrt(sum((value - mean) ** 2 for value in returns) / len(returns)) if returns else 0.0
    )
    downside = (
        math.sqrt(sum(min(value, 0.0) ** 2 for value in returns) / len(returns)) if returns else 0.0
    )
    wins = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losses = [trade.net_pnl for trade in trades if trade.net_pnl < 0]
    gross_wins = sum((trade.gross_pnl for trade in trades if trade.gross_pnl > 0), D(0))
    gross_losses = -sum((trade.gross_pnl for trade in trades if trade.gross_pnl < 0), D(0))
    costs = sum((entry.cost for entry in ledger), D(0))
    traded = sum((entry.notional for entry in ledger if entry.status == "filled"), D(0))
    avg_equity = (
        sum((point["equity"] for point in curve), D(0)) / len(curve) if curve else initial_cash
    )
    return {
        "initial_equity": str(initial_cash),
        "ending_equity": str(end_equity),
        "gross_pnl": str(sum((trade.gross_pnl for trade in trades), D(0))),
        "net_pnl": str(sum((trade.net_pnl for trade in trades), D(0))),
        "total_return": float(total_return),
        "cagr": cagr,
        "max_drawdown": float(max_dd),
        "sharpe_annualized": math.sqrt(252) * mean / std if std > 0 else None,
        "sortino_annualized": math.sqrt(252) * mean / downside if downside > 0 else None,
        "profit_factor": float(gross_wins / gross_losses) if gross_losses > 0 else None,
        "win_rate": len(wins) / len(trades) if trades else None,
        "average_win": str(sum(wins, D(0)) / len(wins)) if wins else None,
        "average_loss": str(sum(losses, D(0)) / len(losses)) if losses else None,
        "closed_trades": len(trades),
        "exposure_fraction": exposure_days / len(curve) if curve else 0.0,
        "turnover": str(traded / avg_equity) if avg_equity > 0 else None,
        "transaction_costs": str(costs),
        "benchmark_return": float(benchmark_return) if benchmark_return is not None else None,
        "metric_conventions": (
            "252-session annualization; Sharpe uses zero risk-free rate/population daily stdev; "
            "Sortino target 0; CAGR uses 365 calendar days; profit factor uses gross wins/losses; "
            "exposure is sessions with an open position. Open positions are marked to close, "
            "not liquidated."
        ),
    }


def run_backtest(
    records: list[HistoricalBar],
    config: BacktestConfig | None = None,
    *,
    input_fingerprint: str | None = None,
    benchmark_symbol: str | None = None,
    corporate_actions: tuple[CorporateAction, ...] = (),
    action_coverage: ActionCoverage | None = None,
    synthetic_fixture: bool = False,
) -> BacktestResult:
    """Simulate next eligible same-symbol session; input is never shuffled."""
    config = config or BacktestConfig()
    if not records:
        raise ValueError("backtest needs at least one historical bar")
    ordered = sorted(records, key=lambda item: (item.session_date, item.bar.symbol))
    if ordered != records:
        raise ValueError(
            "historical rows must already be chronologically sorted; shuffle is prohibited"
        )
    keys = [(item.bar.symbol, item.session_date) for item in ordered]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate symbol/session_date rows")
    input_records = ordered
    benchmark_records = [item for item in ordered if item.bar.symbol == benchmark_symbol]
    if benchmark_symbol is not None:
        ordered = [item for item in ordered if item.bar.symbol != benchmark_symbol]
    if not ordered:
        raise ValueError("backtest needs at least one tradable symbol besides the benchmark")
    validate_actions(corporate_actions)
    if not synthetic_fixture:
        if action_coverage is None:
            raise ValueError("complete, verified corporate-action coverage is required")
        data_start = min(item.session_date for item in ordered)
        data_end = max(item.session_date for item in ordered)
        if action_coverage.start > data_start or action_coverage.end < data_end:
            raise ValueError("corporate-action coverage does not span all input history")
    action_by_day: dict[date, list[CorporateAction]] = {}
    first_input_date = min(item.session_date for item in ordered)
    last_input_date = max(item.session_date for item in ordered)
    for action in corporate_actions:
        if action.symbol not in {item.bar.symbol for item in ordered}:
            continue
        if action.ex_date < first_input_date or action.ex_date > last_input_date:
            continue
        reason = unsupported_action_reason(action)
        # These actions can alter the security/cash entitlement and therefore block even if
        # the strategy would otherwise have entered on the same date.
        if reason:
            raise ValueError(
                f"backtest blocked by unsupported {action.kind.value} for {action.symbol} "
                f"on {action.ex_date}: {reason}"
            )
        action_by_day.setdefault(action.ex_date, []).append(action)
    adjustment_policies = {item.adjustment_policy for item in input_records}
    if any(policy != "raw_unadjusted" for policy in adjustment_policies):
        raise ValueError(
            "backtest supports only raw_unadjusted execution data; adjusted-price conversion "
            "for indicators, OHLC execution, and positions is not implemented"
        )
    if not synthetic_fixture and (
        not config.cost_inclusive_evaluation or config.cost_profile is None
    ):
        raise ValueError(
            "real-data backtests require an explicit, complete effective-dated CostProfile"
        )
    if not synthetic_fixture and config.cost_profile is not None:
        if config.cost_profile.status != "complete" or config.cost_profile.synthetic:
            raise ValueError("real-data backtests require a complete non-synthetic CostProfile")
        if not any(
            (rule.basis != "component_sum" and rule.rate is not None and rule.rate > 0)
            or (rule.fixed_amount is not None and rule.fixed_amount > 0)
            for rule in config.cost_profile.rules
        ):
            raise ValueError("real-data cost profile must include non-zero transaction charges")
    if config.cost_profile is not None:
        if not config.cost_inclusive_evaluation:
            raise ValueError("a versioned CostProfile requires cost-inclusive evaluation")
        if not config.cost_exchange or not config.cost_account_category:
            raise ValueError("versioned CostProfile requires explicit exchange/account category")
        evaluated_sessions = sorted(
            {
                item.session_date
                for item in ordered
                if (config.evaluation_start is None or item.session_date >= config.evaluation_start)
                and (config.evaluation_end is None or item.session_date <= config.evaluation_end)
            }
        )
        for session in evaluated_sessions:
            errors = config.cost_profile.coverage_errors(
                session,
                exchange=config.cost_exchange,
                segment="cash_delivery",
                account_category=config.cost_account_category,
                dp_holder_category=config.cost_dp_holder_category,
            )
            if errors:
                raise ValueError(
                    f"cost profile {config.cost_profile.version} incomplete on {session}: "
                    + "; ".join(errors)
                )
    elif config.cost_inclusive_evaluation:
        profile = config.costs
        rates = (
            profile.brokerage_rate,
            profile.stt_buy_rate,
            profile.stt_sell_rate,
            profile.exchange_rate,
            profile.gst_rate,
            profile.stamp_buy_rate,
            profile.dp_charge_per_share,
        )
        if (
            profile.verification_status != "verified"
            or not profile.source.strip()
            or not profile.rates_explicit
            or not any(rates)
        ):
            raise ValueError(
                "cost-inclusive evaluation requires a verified, sourced, non-zero profile "
                "with all rates explicitly supplied"
            )
        evaluated_dates = [
            item.session_date
            for item in ordered
            if (config.evaluation_start is None or item.session_date >= config.evaluation_start)
            and (config.evaluation_end is None or item.session_date <= config.evaluation_end)
        ]
        if evaluated_dates and (
            profile.effective_from > min(evaluated_dates)
            or (profile.effective_to is not None and profile.effective_to < max(evaluated_dates))
        ):
            raise ValueError("verified cost profile effective dates do not cover evaluation data")
    grouped: dict[str, list[HistoricalBar]] = {}
    for item in ordered:
        grouped.setdefault(item.bar.symbol, []).append(item)
    data_by_day: dict[date, dict[str, HistoricalBar]] = {}
    for item in ordered:
        data_by_day.setdefault(item.session_date, {})[item.bar.symbol] = item
    for action_day, day_actions in action_by_day.items():
        for action in day_actions:
            if action_day not in data_by_day or action.symbol not in data_by_day[action_day]:
                raise ValueError(
                    f"corporate action ex-date {action_day} has no observed bar for {action.symbol}"
                )
    histories: dict[str, list[OHLCVBar]] = {symbol: [] for symbol in grouped}
    positions: dict[str, _OpenPosition] = {}
    pending: dict[str, ProposedOrder] = {}
    ledger: list[LedgerEntry] = []
    trades: list[ClosedTrade] = []
    curve: list[dict[str, Any]] = []
    cash = config.initial_cash
    warnings: list[str] = []
    action_ledger: list[dict[str, Any]] = []
    receivables: list[DividendReceivable] = []
    gross_dividend_income = D(0)
    insufficient = [
        symbol
        for symbol, values in grouped.items()
        if len(values) < max(config.strategy.sma_slow_period, config.strategy.rsi_period + 1, 14)
    ]
    if insufficient:
        warnings.append("insufficient warm-up history for: " + ", ".join(sorted(insufficient)))
    eligible_bars = sum(1 for item in ordered if item.bar.completed)
    if eligible_bars != len(ordered):
        warnings.append(f"{len(ordered) - eligible_bars} incomplete bars excluded from signals")
    all_symbols = set(grouped)
    if not corporate_actions:
        warnings.append(
            "no corporate-action event rows supplied; consult the action coverage manifest"
        )
    session_sets = {
        symbol: {item.session_date for item in items} for symbol, items in grouped.items()
    }
    if len(session_sets) > 1 and any(
        sessions != next(iter(session_sets.values())) for sessions in session_sets.values()
    ):
        warnings.append(
            "symbols have different/missing session rows; no missing bars are fabricated "
            "or forward-filled in indicators"
        )

    for session in sorted(data_by_day):
        if config.evaluation_end and session > config.evaluation_end:
            break
        todays = data_by_day[session]
        # Effective-date events are applied before that day's OHLC can trigger ordinary stops.
        for action in action_by_day.get(session, []):
            if action.symbol not in todays:
                raise ValueError(
                    f"corporate action ex-date {session} has no observed bar for {action.symbol}"
                )
            pos = positions.get(action.symbol)
            if action.kind in {ActionKind.SPLIT, ActionKind.BONUS}:
                factor = action.ratio_new_per_old
                assert factor is not None
                quantity_before = pos.quantity if pos is not None else None
                position_stop_before = pos.stop if pos is not None else None
                position_target_before = pos.target if pos is not None else None
                pending_quantity_before = (
                    pending[action.symbol].quantity if action.symbol in pending else None
                )
                pending_reference_before = (
                    pending[action.symbol].reference_price if action.symbol in pending else None
                )
                pending_stop_before = (
                    pending[action.symbol].stop_price if action.symbol in pending else None
                )
                if pos is not None:
                    pos.quantity = split_quantity(pos.quantity, factor)
                    pos.entry_price /= factor
                    pos.stop /= factor
                    pos.target /= factor
                order = pending.get(action.symbol)
                if order is not None:
                    quantity = split_quantity(order.quantity, factor)
                    pending[action.symbol] = ProposedOrder(
                        order.client_order_id,
                        order.symbol,
                        order.side,
                        quantity,
                        order.reference_price / factor,
                        order.stop_price / factor,
                        order.created_at,
                    )
                histories[action.symbol] = []  # raw-price indicators restart after ratio event
                warnings.append(
                    f"{action.symbol} {session}: split/bonus reset raw indicator history; "
                    "signals wait for renewed warm-up"
                )
                action_ledger.append(
                    {
                        "symbol": action.symbol,
                        "type": action.kind.value,
                        "ex_date": session,
                        "quantity_before": quantity_before,
                        "quantity": pos.quantity if pos is not None else None,
                        "stop_before": position_stop_before,
                        "stop_after": pos.stop if pos is not None else None,
                        "target_before": position_target_before,
                        "target_after": pos.target if pos is not None else None,
                        "pending_quantity_before": pending_quantity_before,
                        "pending_quantity": (
                            pending[action.symbol].quantity if action.symbol in pending else None
                        ),
                        "pending_reference_before": pending_reference_before,
                        "pending_reference_after": (
                            pending[action.symbol].reference_price
                            if action.symbol in pending
                            else None
                        ),
                        "pending_stop_before": pending_stop_before,
                        "pending_stop_after": (
                            pending[action.symbol].stop_price if action.symbol in pending else None
                        ),
                        "ratio_new_per_old": str(factor),
                        "status": "applied",
                        "source_fingerprint": action.source_fingerprint,
                    }
                )
            elif action.kind == ActionKind.DIVIDEND:
                if pos is not None:
                    assert action.cash_per_share is not None and action.payment_date is not None
                    amount = action.cash_per_share * pos.quantity
                    # Entitlement is recognized separately; cash is credited only on payment date.
                    receivables.append(
                        DividendReceivable(
                            action.symbol,
                            session,
                            action.payment_date,
                            amount,
                            action.source_fingerprint,
                        )
                    )
                    gross_dividend_income += amount
                    if pos.stop <= action.cash_per_share or pos.target <= action.cash_per_share:
                        raise ValueError(
                            "dividend adjustment would make protective level nonpositive"
                        )
                    pos.stop -= action.cash_per_share
                    pos.target -= action.cash_per_share
                    action_ledger.append(
                        {
                            "symbol": action.symbol,
                            "type": "dividend_entitlement",
                            "ex_date": session,
                            "quantity": pos.quantity,
                            "gross_amount": str(amount),
                            "payment_date": action.payment_date,
                            "status": "receivable",
                            "source_fingerprint": action.source_fingerprint,
                        }
                    )
                # Avoid carrying pre-ex-date raw closes across a known cash-price discontinuity.
                histories[action.symbol] = []
                warnings.append(
                    f"{action.symbol} {session}: dividend reset raw indicator history; "
                    "signals wait for renewed warm-up"
                )
        for receivable in list(receivables):
            if receivable.payment_date <= session:
                cash += receivable.amount
                receivables.remove(receivable)
                action_ledger.append(
                    {
                        "symbol": receivable.symbol,
                        "type": "dividend_payment",
                        "session_date": session,
                        "amount": str(receivable.amount),
                        "status": "paid",
                        "source_fingerprint": receivable.source_fingerprint,
                    }
                )
        # First process existing stops using today's OHLC, then pending orders at today's open.
        for symbol in sorted(todays):
            item = todays[symbol]
            bar = item.bar
            pos = positions.get(symbol)
            if pos is None:
                continue
            stop_touched = bar.low <= pos.stop or bar.open <= pos.stop
            target_touched = bar.high >= pos.target or bar.open >= pos.target
            exit_price: Decimal | None = None
            reason = ""
            if stop_touched:
                exit_price = bar.open if bar.open <= pos.stop else pos.stop
                reason = "stop_gap" if bar.open <= pos.stop else "stop_touch"
            elif target_touched:
                exit_price = bar.open if bar.open >= pos.target else pos.target
                reason = "target_gap" if bar.open >= pos.target else "target_touch"
            if exit_price is not None:
                execution = _slipped(exit_price, "SELL", config.slippage_bps)
                notional = execution * pos.quantity
                cost, cost_detail = _execution_cost(
                    config,
                    transaction_id=pos.order_id + f"-EXIT-{session}",
                    order_id=pos.order_id + "-EXIT",
                    symbol=symbol,
                    side="SELL",
                    session=session,
                    notional=notional,
                    quantity=pos.quantity,
                )
                cash += notional - cost
                gross = (execution - pos.entry_price) * pos.quantity
                total_cost = pos.entry_cost + cost
                trades.append(
                    ClosedTrade(
                        symbol,
                        pos.entry_date,
                        session,
                        pos.quantity,
                        pos.entry_price,
                        execution,
                        gross,
                        total_cost,
                        gross - total_cost,
                        reason,
                    )
                )
                ledger.append(
                    LedgerEntry(
                        pos.order_id + "-EXIT",
                        symbol,
                        "SELL",
                        session,
                        pos.quantity,
                        execution,
                        notional,
                        cost,
                        "filled",
                        reason,
                        cost_detail,
                    )
                )
                del positions[symbol]

        for symbol in sorted(todays):
            item = todays[symbol]
            bar = item.bar
            order = pending.get(symbol)
            if order is None or session <= order.created_at.date():
                continue
            del pending[symbol]
            notional_volume = int(D(bar.volume) * config.max_volume_fraction)
            if order.quantity > notional_volume:
                ledger.append(
                    LedgerEntry(
                        order.client_order_id,
                        symbol,
                        "BUY",
                        session,
                        order.quantity,
                        bar.open,
                        bar.open * order.quantity,
                        D(0),
                        "rejected",
                        "volume cap",
                    )
                )
                continue
            if symbol in positions or len(positions) >= config.max_positions:
                ledger.append(
                    LedgerEntry(
                        order.client_order_id,
                        symbol,
                        "BUY",
                        session,
                        order.quantity,
                        bar.open,
                        bar.open * order.quantity,
                        D(0),
                        "rejected",
                        "position limit",
                    )
                )
                continue
            execution = _slipped(bar.open, "BUY", config.slippage_bps)
            if execution <= order.stop_price:
                ledger.append(
                    LedgerEntry(
                        order.client_order_id,
                        symbol,
                        "BUY",
                        session,
                        order.quantity,
                        execution,
                        execution * order.quantity,
                        D(0),
                        "rejected",
                        "next open is at or below the proposed protective stop",
                    )
                )
                continue
            notional = execution * order.quantity
            cost, cost_detail = _execution_cost(
                config,
                transaction_id=order.client_order_id + f"-BUY-{session}",
                order_id=order.client_order_id,
                symbol=symbol,
                side="BUY",
                session=session,
                notional=notional,
                quantity=order.quantity,
            )
            if notional + cost > cash:
                ledger.append(
                    LedgerEntry(
                        order.client_order_id,
                        symbol,
                        "BUY",
                        session,
                        order.quantity,
                        execution,
                        notional,
                        D(0),
                        "rejected",
                        "insufficient cash including costs",
                    )
                )
                continue
            cash -= notional + cost
            stop = order.stop_price
            distance = order.reference_price - stop
            target = execution + distance * config.target_r_multiple
            position = _OpenPosition(
                symbol,
                order.quantity,
                session,
                execution,
                stop,
                target,
                cost,
                order.client_order_id,
            )
            positions[symbol] = position
            ledger.append(
                LedgerEntry(
                    order.client_order_id,
                    symbol,
                    "BUY",
                    session,
                    order.quantity,
                    execution,
                    notional,
                    cost,
                    "filled",
                    "next_session_open",
                    cost_detail,
                )
            )
            # Daily-bar ambiguity applies immediately after entry too; stop wins if both touched.
            stop_touched = bar.low <= stop or bar.open <= stop
            target_touched = bar.high >= target or bar.open >= target
            if stop_touched or target_touched:
                hit_stop = stop_touched  # conservative rule for stop and target both touched
                raw_exit = (
                    (bar.open if bar.open <= stop else stop)
                    if hit_stop
                    else (bar.open if bar.open >= target else target)
                )
                reason = (
                    ("stop_gap" if bar.open <= stop else "stop_touch")
                    if hit_stop
                    else ("target_gap" if bar.open >= target else "target_touch")
                )
                exit_execution = _slipped(raw_exit, "SELL", config.slippage_bps)
                exit_notional = exit_execution * order.quantity
                exit_cost, exit_cost_detail = _execution_cost(
                    config,
                    transaction_id=order.client_order_id + f"-EXIT-{session}",
                    order_id=order.client_order_id + "-EXIT",
                    symbol=symbol,
                    side="SELL",
                    session=session,
                    notional=exit_notional,
                    quantity=order.quantity,
                )
                cash += exit_notional - exit_cost
                gross = (exit_execution - execution) * order.quantity
                trades.append(
                    ClosedTrade(
                        symbol,
                        session,
                        session,
                        order.quantity,
                        execution,
                        exit_execution,
                        gross,
                        cost + exit_cost,
                        gross - cost - exit_cost,
                        reason,
                    )
                )
                ledger.append(
                    LedgerEntry(
                        order.client_order_id + "-EXIT",
                        symbol,
                        "SELL",
                        session,
                        order.quantity,
                        exit_execution,
                        exit_notional,
                        exit_cost,
                        "filled",
                        reason,
                        exit_cost_detail,
                    )
                )
                del positions[symbol]

        # Record close equity before adding today's post-close signals to the pending book.
        portfolio = PortfolioState(
            cash,
            {
                symbol: Position(symbol, pos.quantity, pos.entry_price)
                for symbol, pos in positions.items()
            },
        )
        marked = portfolio.cash + sum(
            (
                positions[symbol].quantity * todays[symbol].bar.close
                for symbol in positions
                if symbol in todays
            ),
            D(0),
        )
        marked += sum((item.amount for item in receivables), D(0))
        # Carry the last observed close for valuation only; never fabricate an indicator bar.
        for symbol, position in positions.items():
            if symbol not in todays:
                prior = histories[symbol][-1]
                marked += position.quantity * prior.close
        curve.append(
            {"date": session, "equity": marked, "cash": cash, "open_positions": len(positions)}
        )

        for symbol, item in sorted(todays.items()):
            histories[symbol].append(item.bar)
            if not item.bar.completed:
                continue
            if config.evaluation_start and session < config.evaluation_start:
                continue
            if config.evaluation_end and session > config.evaluation_end:
                continue
            if (
                symbol in positions
                or symbol in pending
                or len(positions) + len(pending) >= config.max_positions
            ):
                continue
            history = histories[symbol]
            signals = generate_signals(history, config.strategy)
            if not signals or signals[-1].timestamp != item.bar.timestamp:
                continue
            atr_values = atr(history, config.atr_period)
            current_atr = atr_values[-1]
            if current_atr is None or current_atr <= 0:
                continue
            signal: TradeSignal = signals[-1]
            stop = signal.reference_price - current_atr * config.stop_atr_multiple
            if stop <= 0:
                warnings.append(f"{symbol} {session}: ATR stop is nonpositive; signal skipped")
                continue
            try:
                order = size_order(
                    signal, equity=curve[-1]["equity"], stop_price=stop, config=config.risk
                )
            except ValueError as exc:
                warnings.append(f"{symbol} {session}: order sizing rejected: {exc}")
                continue
            pending[symbol] = order
            ledger.append(
                LedgerEntry(
                    order.client_order_id,
                    symbol,
                    "BUY",
                    session,
                    order.quantity,
                    order.reference_price,
                    D(0),
                    D(0),
                    "pending",
                    "signal after completed close; earliest fill is a later session open",
                )
            )

    # Report only evaluation window points while retaining prior rows for indicator warm-up.
    curve = [
        point
        for point in curve
        if (config.evaluation_start is None or point["date"] >= config.evaluation_start)
        and (config.evaluation_end is None or point["date"] <= config.evaluation_end)
    ]
    exposure_days = sum(point["open_positions"] > 0 for point in curve)
    benchmark_return = None
    if benchmark_symbol:
        benchmark = [
            item
            for item in benchmark_records
            if (config.evaluation_start is None or item.session_date >= config.evaluation_start)
            and (config.evaluation_end is None or item.session_date <= config.evaluation_end)
        ]
        if len(benchmark) >= 2 and benchmark[0].bar.close > 0:
            benchmark_return = benchmark[-1].bar.close / benchmark[0].bar.close - 1
        else:
            warnings.append(f"benchmark {benchmark_symbol} has insufficient history")
    metrics = _metrics(curve, trades, ledger, config.initial_cash, exposure_days, benchmark_return)
    metrics["gross_dividend_income"] = str(gross_dividend_income)
    metrics["unpaid_dividend_receivables"] = str(sum((item.amount for item in receivables), D(0)))
    manifest = {
        "paper_only": True,
        "synthetic": synthetic_fixture,
        "input_fingerprint_sha256": input_fingerprint
        or hashlib.sha256(
            "\n".join(
                f"{x.bar.symbol},{x.session_date},{x.bar.open},{x.bar.high},{x.bar.low},{x.bar.close},{x.bar.volume}"
                for x in input_records
            ).encode()
        ).hexdigest(),
        "symbols": sorted(all_symbols | ({benchmark_symbol} if benchmark_symbol else set())),
        "tradable_symbols": sorted(all_symbols),
        "benchmark_symbol": benchmark_symbol,
        "first_date": ordered[0].session_date.isoformat(),
        "last_date": ordered[-1].session_date.isoformat(),
        "schema_version": "1.0",
        "adjustment_policies": sorted({item.adjustment_policy for item in ordered}),
        "cost_profile": {
            "engine": "versioned_component_cost_profile"
            if config.cost_profile is not None
            else "legacy_cost_schedule",
            "resolver_version": config.cost_profile.version
            if config.cost_profile is not None
            else None,
            "resolver_status": config.cost_profile.status
            if config.cost_profile is not None
            else None,
            "exchange": config.cost_exchange,
            "account_category": config.cost_account_category,
            "dp_holder_category": config.cost_dp_holder_category,
            "source_evidence": [
                {
                    "source_id": source_id,
                    "url": url,
                    "status": status,
                    "sha256": fingerprint,
                }
                for source_id, url, status, fingerprint in (
                    config.cost_profile.source_metadata if config.cost_profile else ()
                )
            ],
            "version": config.costs.version,
            "effective_from": config.costs.effective_from.isoformat(),
            "effective_to": (
                config.costs.effective_to.isoformat() if config.costs.effective_to else None
            ),
            "source": config.costs.source,
            "verification_status": config.costs.verification_status,
            "rates_explicit": config.costs.rates_explicit,
            "cost_inclusive_evaluation": config.cost_inclusive_evaluation,
            "rates": {
                name: str(getattr(config.costs, name))
                for name in (
                    "brokerage_rate",
                    "stt_buy_rate",
                    "stt_sell_rate",
                    "exchange_rate",
                    "gst_rate",
                    "stamp_buy_rate",
                    "dp_charge_per_share",
                )
            },
        },
        "corporate_action_coverage": (
            {
                "source": action_coverage.source,
                "source_fingerprint": action_coverage.source_fingerprint,
                "start": action_coverage.start.isoformat(),
                "end": action_coverage.end.isoformat(),
                "complete": action_coverage.complete,
                "verified": action_coverage.verified,
            }
            if action_coverage
            else {"status": "synthetic_fixture_exception" if synthetic_fixture else "missing"}
        ),
        "corporate_action_policy": (
            "splits/bonuses scale whole-share quantity and inversely scale price/cost basis; "
            "fractional results block; dividends accrue on ex-date for prior-close holdings, "
            "cash is credited on payment date; protective levels shift by the per-share dividend; "
            "raw indicators reset after split/bonus/dividend ex-dates"
        ),
        "config": _config_dict(config),
        "execution_policy": (
            "next eligible symbol session open; adverse slippage; gap stop fills at open; "
            "stop touch at stop; stop wins ambiguous stop-target bars; full-fill volume/cash limits"
        ),
    }
    return BacktestResult(
        tuple(curve),
        tuple(trades),
        tuple(ledger),
        metrics,
        manifest,
        tuple(dict.fromkeys(warnings)),
        tuple(action_ledger),
    )


def _config_dict(config: BacktestConfig) -> dict[str, Any]:
    def convert(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        if hasattr(value, "__dataclass_fields__"):
            return {key: convert(val) for key, val in asdict(value).items()}
        if isinstance(value, dict):
            return {key: convert(val) for key, val in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(val) for val in value]
        return value

    return convert(config)


def export_result(result: BacktestResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    schemas = {
        "equity_curve.csv": ["date", "equity", "cash", "open_positions"],
        "trades.csv": [
            "symbol",
            "entry_date",
            "exit_date",
            "quantity",
            "entry_price",
            "exit_price",
            "gross_pnl",
            "costs",
            "net_pnl",
            "exit_reason",
        ],
        "ledger.csv": [
            "order_id",
            "symbol",
            "side",
            "session_date",
            "quantity",
            "price",
            "notional",
            "cost",
            "status",
            "reason",
            "cost_breakdown",
        ],
        "corporate_actions.csv": [
            "symbol",
            "type",
            "ex_date",
            "session_date",
            "quantity_before",
            "quantity",
            "stop_before",
            "stop_after",
            "target_before",
            "target_after",
            "pending_quantity_before",
            "pending_quantity",
            "pending_reference_before",
            "pending_reference_after",
            "pending_stop_before",
            "pending_stop_after",
            "ratio_new_per_old",
            "gross_amount",
            "payment_date",
            "amount",
            "status",
            "source_fingerprint",
        ],
    }

    def write_rows(name: str, rows: list[dict[str, Any]]) -> None:
        path = output_dir / name
        fields = list(rows[0]) if rows else schemas[name]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    write_rows(
        "equity_curve.csv",
        [{**point, "date": point["date"].isoformat()} for point in result.equity_curve],
    )
    write_rows(
        "trades.csv",
        [
            {
                **asdict(trade),
                "entry_date": trade.entry_date.isoformat(),
                "exit_date": trade.exit_date.isoformat(),
            }
            for trade in result.trades
        ],
    )
    write_rows(
        "ledger.csv",
        [
            {
                **asdict(entry),
                "session_date": entry.session_date.isoformat(),
                "cost_breakdown": (
                    json.dumps(entry.cost_breakdown, sort_keys=True)
                    if entry.cost_breakdown is not None
                    else ""
                ),
            }
            for entry in result.ledger
        ],
    )
    write_rows(
        "corporate_actions.csv",
        [
            {
                **row,
                "ex_date": row.get("ex_date").isoformat() if row.get("ex_date") else "",
                "session_date": row.get("session_date").isoformat()
                if row.get("session_date")
                else "",
                "payment_date": row.get("payment_date").isoformat()
                if row.get("payment_date")
                else "",
            }
            for row in result.corporate_action_ledger
        ],
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(result.metrics, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(result.manifest, indent=2) + "\n", encoding="utf-8"
    )
