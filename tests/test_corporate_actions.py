import json
from datetime import UTC, date, datetime
from decimal import Decimal as D

import pytest
from test_historical_backtest import config, rising_records

from nse_swing_agent.backtest import run_backtest
from nse_swing_agent.corporate_actions import (
    ActionCoverage,
    ActionKind,
    CorporateAction,
    load_action_manifest,
    split_quantity,
)
from nse_swing_agent.historical_data import HistoricalBar
from nse_swing_agent.models import OHLCVBar

HASH = "a" * 64
RETRIEVED = datetime(2026, 10, 23, tzinfo=UTC)


def action(kind, *, ex=date(2025, 1, 5), ratio=None, cash=None, payment=None):
    return CorporateAction(
        symbol="AAA",
        isin="INE000A01000",
        kind=kind,
        ex_date=ex,
        record_date=ex,
        payment_date=payment,
        ratio_new_per_old=ratio,
        cash_per_share=cash,
        currency="INR" if cash is not None else None,
        source="unit test fixture",
        source_fingerprint=HASH,
        retrieved_at=RETRIEVED,
        verification_status="verified",
    )


def coverage(records):
    return ActionCoverage(
        min(row.session_date for row in records),
        max(row.session_date for row in records),
        True,
        True,
        "unit test calendar",
        HASH,
    )


@pytest.mark.parametrize(("ratio", "multiplier"), [(D(2), 2), (D(2), 2)])
def test_bonus_and_two_for_one_split_whole_share_math(ratio, multiplier):
    assert split_quantity(7, ratio) == 7 * multiplier


def test_fractional_entitlements_are_blocked_not_rounded():
    with pytest.raises(ValueError, match="fractional shares"):
        split_quantity(1, D("1.5"))


def test_pending_buy_quantity_and_protective_price_transform_on_event_date():
    records = rising_records(entry_open="6.7")
    result = run_backtest(
        records,
        config(),
        corporate_actions=(action(ActionKind.SPLIT, ex=date(2025, 1, 4), ratio=D(2)),),
        action_coverage=coverage(records),
    )
    transformed = next(row for row in result.corporate_action_ledger if row["status"] == "applied")
    assert transformed["pending_quantity_before"] is not None
    assert transformed["pending_quantity"] == transformed["pending_quantity_before"] * 2
    assert transformed["pending_reference_after"] == transformed["pending_reference_before"] / 2
    assert transformed["pending_stop_after"] == transformed["pending_stop_before"] / 2
    filled = next(row for row in result.ledger if row.status == "filled" and row.side == "BUY")
    assert filled.quantity == transformed["pending_quantity"]


def test_action_date_split_discontinuity_does_not_trigger_old_scale_stop():
    records = rising_records()
    # Model a raw 2:1 split price scale from the effective date onward.
    adjusted = []
    for row in records:
        if row.session_date >= date(2025, 1, 5):
            bar = row.bar
            adjusted.append(
                type(row)(
                    type(bar)(
                        bar.symbol,
                        bar.timestamp,
                        bar.open / 2,
                        bar.high / 2,
                        bar.low / 2,
                        bar.close / 2,
                        bar.volume,
                    ),
                    row.session_date,
                )
            )
        else:
            adjusted.append(row)
    event = action(ActionKind.SPLIT, ratio=D(2))
    result = run_backtest(
        adjusted,
        config(),
        corporate_actions=(event,),
        action_coverage=coverage(adjusted),
    )
    assert all(trade.exit_date != event.ex_date for trade in result.trades)
    assert any(row["type"] == "split" for row in result.corporate_action_ledger)


@pytest.mark.parametrize("kind", [ActionKind.BONUS, ActionKind.SPLIT])
def test_split_and_bonus_rebase_position_and_stop_before_exdate_bar(kind):
    original = rising_records()
    records = []
    for row in original:
        if row.session_date == date(2025, 1, 5):
            bar = OHLCVBar(
                row.bar.symbol,
                row.bar.timestamp,
                D("6.5"),
                D("6.75"),
                D("6.25"),
                D("6.5"),
                row.bar.volume,
            )
            records.append(HistoricalBar(bar, row.session_date))
        elif row.session_date > date(2025, 1, 5):
            bar = row.bar
            records.append(
                HistoricalBar(
                    OHLCVBar(
                        bar.symbol,
                        bar.timestamp,
                        bar.open / 2,
                        bar.high / 2,
                        bar.low / 2,
                        bar.close / 2,
                        bar.volume,
                    ),
                    row.session_date,
                )
            )
        else:
            records.append(row)
    ratio = D(2)  # 1:1 bonus => two new shares per old share; 2-for-1 split.
    result = run_backtest(
        records,
        config(),
        corporate_actions=(action(kind, ratio=ratio),),
        action_coverage=coverage(records),
    )
    applied = next(row for row in result.corporate_action_ledger if row["status"] == "applied")
    entry = next(row for row in result.ledger if row.side == "BUY" and row.status == "filled")
    assert applied["quantity_before"] == entry.quantity
    assert applied["quantity"] == entry.quantity * 2
    assert applied["ratio_new_per_old"] == "2"
    assert applied["stop_after"] == applied["stop_before"] / 2
    assert applied["target_after"] == applied["target_before"] / 2
    # Cost basis per share halves while aggregate cost basis stays invariant.
    assert D(applied["quantity"]) * (entry.price / ratio) == D(entry.quantity) * entry.price
    jan4_equity = next(
        point["equity"] for point in result.equity_curve if point["date"] == date(2025, 1, 4)
    )
    jan5_equity = next(
        point["equity"] for point in result.equity_curve if point["date"] == date(2025, 1, 5)
    )
    assert jan4_equity == jan5_equity


def test_dividend_entitlement_uses_prior_close_and_cash_waits_for_payment_date():
    records = rising_records(day5=("13.8", "14.2", "13.5", "13.9"))
    result = run_backtest(
        records,
        config(),
        corporate_actions=(action(ActionKind.DIVIDEND, cash=D("0.25"), payment=date(2025, 1, 6)),),
        action_coverage=coverage(records),
    )
    entitlement = next(
        row for row in result.corporate_action_ledger if row["status"] == "receivable"
    )
    payment = next(row for row in result.corporate_action_ledger if row["status"] == "paid")
    assert entitlement["quantity"] > 0
    assert D(entitlement["gross_amount"]) == D(entitlement["quantity"]) * D("0.25")
    assert payment["session_date"] == date(2025, 1, 6)
    assert payment["amount"] == entitlement["gross_amount"]
    assert result.metrics["gross_dividend_income"] == entitlement["gross_amount"]
    assert result.metrics["gross_pnl"] == "0"
    cash_by_day = {point["date"]: point["cash"] for point in result.equity_curve}
    assert cash_by_day[date(2025, 1, 6)] - cash_by_day[date(2025, 1, 5)] == D(
        entitlement["gross_amount"]
    )
    assert result.manifest["corporate_action_policy"]


def test_dividend_does_not_entitle_position_entered_after_exdate_close():
    records = rising_records()
    result = run_backtest(
        records,
        config(),
        corporate_actions=(
            action(
                ActionKind.DIVIDEND,
                ex=date(2025, 1, 3),
                cash=D("0.25"),
                payment=date(2025, 1, 6),
            ),
        ),
        action_coverage=coverage(records),
    )
    assert result.metrics["gross_dividend_income"] == "0"
    assert not any(row["type"] == "dividend_entitlement" for row in result.corporate_action_ledger)


@pytest.mark.parametrize(
    "kind",
    [
        ActionKind.RIGHTS,
        ActionKind.DEMERGER,
        ActionKind.MERGER,
        ActionKind.BUYBACK,
        ActionKind.DELISTING,
    ],
)
def test_unsupported_actions_block_overlapping_evaluation(kind):
    records = rising_records()
    event = action(kind)
    with pytest.raises(ValueError, match=f"unsupported {kind.value}"):
        run_backtest(
            records, config(), corporate_actions=(event,), action_coverage=coverage(records)
        )


def test_non_synthetic_run_requires_verified_complete_action_coverage():
    records = rising_records()
    with pytest.raises(ValueError, match="coverage is required"):
        run_backtest(records, config())


def test_symbol_named_synth_does_not_bypass_action_coverage_gate():
    records = rising_records()
    renamed = [
        HistoricalBar(
            OHLCVBar(
                "SYNTH",
                row.bar.timestamp,
                row.bar.open,
                row.bar.high,
                row.bar.low,
                row.bar.close,
                row.bar.volume,
            ),
            row.session_date,
        )
        for row in records
    ]
    with pytest.raises(ValueError, match="coverage is required"):
        run_backtest(renamed, config())


def test_missing_dividend_terms_and_unverified_events_rejected():
    with pytest.raises(ValueError, match="payment_date"):
        action(ActionKind.DIVIDEND, cash=D(1))
    with pytest.raises(ValueError, match="ambiguous or unverified"):
        CorporateAction(
            symbol="AAA",
            kind=ActionKind.BONUS,
            ex_date=date(2025, 1, 5),
            source="test",
            source_fingerprint=HASH,
            retrieved_at=RETRIEVED,
            verification_status="ambiguous",
            ratio_new_per_old=D(2),
        )


def test_future_action_does_not_apply_to_earlier_signal_session():
    records = rising_records()
    later = action(ActionKind.BONUS, ex=date(2025, 1, 6), ratio=D(2))
    result = run_backtest(
        records, config(), corporate_actions=(later,), action_coverage=coverage(records)
    )
    pending = next(row for row in result.ledger if row.status == "pending")
    assert pending.session_date < later.ex_date
    assert all(row["ex_date"] != pending.session_date for row in result.corporate_action_ledger)


def test_duplicate_actions_rejected():
    records = rising_records()
    event = action(ActionKind.BONUS, ratio=D(2))
    with pytest.raises(ValueError, match="duplicate corporate action"):
        run_backtest(
            records, config(), corporate_actions=(event, event), action_coverage=coverage(records)
        )


def test_canonical_manifest_validates_and_rejects_conflicting_duplicate(tmp_path):
    manifest = {
        "schema_version": "1.0",
        "source": "reviewed local fixture",
        "source_fingerprint": HASH,
        "retrieved_at": "2026-10-23T00:00:00+00:00",
        "coverage": {
            "from": "2025-01-01",
            "to": "2025-01-06",
            "complete": True,
            "verified": True,
        },
        "events": [
            {
                "symbol": "AAA",
                "isin": "INE000A01000",
                "type": "bonus",
                "ex_date": "2025-01-05",
                "record_date": "2025-01-05",
                "ratio_new_per_old": "2",
                "verification_status": "verified",
            }
        ],
    }
    path = tmp_path / "actions.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    events, loaded_coverage = load_action_manifest(path)
    assert events[0].ratio_new_per_old == D(2)
    assert loaded_coverage.verified is True
    manifest["events"].append({**manifest["events"][0], "ratio_new_per_old": "3"})
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting duplicate"):
        load_action_manifest(path)


def test_canonical_dividend_requires_payment_date_and_currency(tmp_path):
    manifest = {
        "schema_version": "1.0",
        "source": "reviewed local fixture",
        "source_fingerprint": HASH,
        "retrieved_at": "2026-10-23T00:00:00+00:00",
        "coverage": {
            "from": "2025-01-01",
            "to": "2025-01-06",
            "complete": True,
            "verified": True,
        },
        "events": [
            {
                "symbol": "AAA",
                "type": "dividend",
                "ex_date": "2025-01-05",
                "cash_per_share": "1",
                "verification_status": "verified",
            }
        ],
    }
    path = tmp_path / "dividend.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="payment_date"):
        load_action_manifest(path)
