from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

from nse_swing_agent.cost_profiles import (
    CostCoverageError,
    CostProfile,
    CostRule,
    CostTransaction,
    load_cost_profile,
)


def test_partial_zerodha_profile_preserves_sources_and_fails_closed():
    root = Path(__file__).parents[1]
    profile = load_cost_profile(
        root / "config/cost_profiles/zerodha_resident_individual_delivery_v2_partial.json"
    )
    assert profile.status == "partial"
    assert profile.exchanges == ("NSE", "BSE")
    assert len(profile.source_metadata) >= 10
    assert any(item[0] == "nse_fa64232_2024" and item[3] for item in profile.source_metadata)
    for exchange in ("NSE", "BSE"):
        errors = profile.coverage_errors(
            date(2025, 1, 2),
            exchange=exchange,
            segment="cash_delivery",
            account_category="resident_individual",
            dp_holder_category="male_primary",
        )
        assert errors
    missing_holder = profile.coverage_errors(
        date(2025, 1, 2),
        exchange="NSE",
        segment="cash_delivery",
        account_category="resident_individual",
    )
    assert any("DP holder category is required" in error for error in missing_holder)
    with pytest.raises(CostCoverageError):
        profile.quote(
            [
                CostTransaction(
                    "tx",
                    date(2025, 1, 2),
                    "RELIANCE",
                    "BUY",
                    D("1000"),
                    10,
                    exchange="NSE",
                    segment="cash_delivery",
                    account_category="resident_individual",
                )
            ]
        )


def _synthetic_profile(rules: tuple[CostRule, ...], components: tuple) -> CostProfile:
    return CostProfile(
        version="test-only-v1",
        market="India",
        segment="cash_delivery",
        required_components=components,
        rules=rules,
        status="synthetic_test_only",
        synthetic=True,
        exchanges=("NSE", "BSE"),
        account_category="resident_individual",
    )


def test_exchange_scoped_rules_resolve_independently():
    common = dict(
        component="exchange_fee",
        category="exchange",
        basis="notional",
        aggregation="per_fill",
        sides=("BUY",),
        verification_status="synthetic_test_only",
        rounding="half_up_paise",
        effective_from=date(2020, 1, 1),
        rate=D("0.001"),
        segment="cash_delivery",
        account_category="resident_individual",
    )
    profile = _synthetic_profile(
        (
            CostRule(**common, exchange="NSE"),
            CostRule(**(common | {"rate": D("0.002")}), exchange="BSE"),
        ),
        (("exchange_fee", ("BUY",), ("NSE", "BSE")),),
    )
    transactions = [
        CostTransaction(
            exchange,
            date(2025, 1, 2),
            "AAA",
            "BUY",
            D("1000"),
            1,
            exchange=exchange,
            segment="cash_delivery",
            account_category="resident_individual",
        )
        for exchange in ("NSE", "BSE")
    ]
    costs = profile.quote(transactions)
    assert {line.exchange: line.amount for line in costs.lines} == {
        "NSE": D("1.00"),
        "BSE": D("2.00"),
    }


def test_effective_date_boundaries_and_gaps_are_explicit():
    common = dict(
        component="fee",
        category="statutory",
        basis="notional",
        aggregation="per_fill",
        sides=("BUY",),
        verification_status="synthetic_test_only",
        rounding="half_up_paise",
        rate=D("0.001"),
        exchange="NSE",
    )
    profile = _synthetic_profile(
        (
            CostRule(**common, effective_from=date(2020, 1, 1), effective_to=date(2020, 12, 31)),
            CostRule(**common, effective_from=date(2021, 2, 1)),
        ),
        (("fee", ("BUY",), ("NSE",)),),
    )
    context = {
        "exchange": "NSE",
        "segment": "cash_delivery",
        "account_category": "resident_individual",
    }
    assert not profile.coverage_errors(date(2020, 12, 31), **context)
    assert not profile.coverage_errors(date(2021, 2, 1), **context)
    gap = profile.coverage_errors(date(2021, 1, 15), **context)
    assert any("unsupported interval" in error for error in gap)


def test_dp_fixed_amount_is_exact_and_grouped_once_per_symbol_day():
    profile = _synthetic_profile(
        (
            CostRule(
                component="dp",
                category="depository",
                basis="fixed",
                aggregation="per_day_symbol",
                sides=("SELL",),
                verification_status="synthetic_test_only",
                rounding="exact",
                effective_from=date(2020, 1, 1),
                fixed_amount=D("3.25"),
                exchange="NSE",
                segment="cash_delivery",
                account_category="resident_individual",
                dp_holder_category="female_primary",
            ),
        ),
        (("dp", ("SELL",), ("NSE",)),),
    )
    txs = [
        CostTransaction(
            f"sell-{i}",
            date(2025, 1, 2),
            "AAA",
            "SELL",
            D("500"),
            1,
            exchange="NSE",
            segment="cash_delivery",
            account_category="resident_individual",
            dp_holder_category="female_primary",
        )
        for i in range(2)
    ]
    result = profile.quote(txs)
    assert result.total == D("3.25")
    assert result.lines[0].transaction_ids == ("sell-0", "sell-1")


def test_unverified_rounding_prevents_cost_quote():
    profile = _synthetic_profile(
        (
            CostRule(
                component="fee",
                category="statutory",
                basis="notional",
                aggregation="per_fill",
                sides=("BUY",),
                verification_status="synthetic_test_only",
                rounding="unverified",
                effective_from=date(2020, 1, 1),
                rate=D("0.001"),
            ),
        ),
        (("fee", ("BUY",), ()),),
    )
    tx = CostTransaction(
        "t",
        date(2025, 1, 2),
        "AAA",
        "BUY",
        D("1000"),
        1,
        exchange="NSE",
        segment="cash_delivery",
        account_category="resident_individual",
    )
    with pytest.raises(CostCoverageError, match="rounding"):
        profile.quote([tx])
