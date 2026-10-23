"""Historical tariff reconciliation remains explicitly partial and reproducible."""

import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from nse_swing_agent.cost_profiles import CostCoverageError, CostTransaction, load_cost_profile

ROOT = Path(__file__).parents[1]
PROFILE_PATH = ROOT / "config/cost_profiles/zerodha_resident_individual_delivery_v3_partial.json"


def test_2jc_profile_dates_nse_boundaries_and_keeps_gaps_blocked():
    profile = load_cost_profile(PROFILE_PATH)
    assert profile.status == "partial"

    def rule(component: str, exchange: str, day: date):
        return next(
            r
            for r in profile.rules
            if r.component == component
            and r.exchange == exchange
            and r.effective_from is not None
            and r.effective_from <= day
            and (r.effective_to is None or day <= r.effective_to)
        )

    assert rule("stt", "NSE", date(2018, 1, 2)).effective_from == date(2018, 1, 1)
    assert rule("stamp_duty", "BSE", date(2020, 7, 1)).effective_from == date(2020, 7, 1)
    assert rule("exchange_transaction", "NSE", date(2024, 10, 1)).rate == Decimal("0.0000297")
    assert rule("exchange_transaction", "NSE", date(2026, 3, 1)).rate == Decimal("0.000030699")
    assert not any(
        r.component == "exchange_transaction" and r.exchange == "BSE" and r.effective_from
        for r in profile.rules
    )
    ctx = dict(exchange="NSE", segment="cash_delivery", account_category="resident_individual")
    assert any("unsupported before" in e for e in profile.coverage_errors(date(2020, 6, 30), **ctx))
    assert any(
        "unverified" in e or "partially_verified" in e
        for e in profile.coverage_errors(date(2025, 1, 2), **ctx, dp_holder_category="male_primary")
    )


def test_stt_stamp_schedule_observations_do_not_allow_quote():
    profile = load_cost_profile(PROFILE_PATH)
    with pytest.raises(CostCoverageError):
        profile.quote(
            [
                CostTransaction(
                    "not-a-real-evaluation",
                    date(2025, 1, 2),
                    "SYNTHETIC",
                    "BUY",
                    Decimal("1000"),
                    1,
                    exchange="NSE",
                    segment="cash_delivery",
                    account_category="resident_individual",
                    dp_holder_category="male_primary",
                )
            ]
        )


def test_2jc_provenance_has_no_fabricated_hash_and_existing_hashes_validate():
    manifest_path = ROOT / "data/reference/cost_profiles/milestone_2j_c/provenance_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_id = {item["source_id"]: item for item in manifest["sources"]}
    for identifier in (
        "income_tax_stt_delivery_2005",
        "india_stamp_act_schedule_56a",
        "dea_stamp_duty_implementation_2020",
    ):
        assert by_id[identifier]["archive_file"] is None
        assert by_id[identifier]["sha256"] is None
        assert "failed" in by_id[identifier]["status"]
    for source in manifest["sources"]:
        if source.get("archive_file"):
            path = (manifest_path.parent / source["archive_file"]).resolve()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
    inventory = json.loads(
        (ROOT / "data/reference/cost_profiles/milestone_2j_c/source_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    inventory_by_id = {item["source_id"]: item for item in inventory["sources"]}
    assert inventory_by_id["income_tax_stt_delivery_2005"]["publication_date"] is None
    assert inventory_by_id["income_tax_stt_delivery_2005"]["effective_date"] == "2005-06-01"
    assert inventory_by_id["nse_fa73061_2026"]["effective_date"] == "2026-03-01"
    assert inventory_by_id["nse_fa73061_2026"]["sha256"]


def test_2jc_artifacts_are_deterministic_and_readiness_stays_blocked():
    from scripts.build_milestone_2j_c_cost_reconciliation import build

    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            PROFILE_PATH,
            ROOT / "data/reference/cost_profiles/milestone_2j_c/provenance_manifest.json",
            ROOT / "reports/milestone_2j_c/coverage.json",
            ROOT / "reports/milestone_2j_c/readiness.md",
        )
    }
    report = build()
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}
    assert before == after
    assert report["readiness"] == "BLOCKED"
    assert report["backtest_executed"] is False
    assert report["profitability_evaluation"] is False
    assert report["component_coverage"]["bse_transaction"]["status"].startswith("partially")
