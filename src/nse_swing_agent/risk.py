"""Deterministic long-only risk sizing; stop distance is not a loss guarantee."""

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from hashlib import sha256

from .models import ProposedOrder, TradeSignal


@dataclass(frozen=True, slots=True)
class RiskConfig:
    risk_fraction: Decimal = Decimal("0.005")
    max_position_fraction: Decimal = Decimal("0.20")

    def __post_init__(self) -> None:
        if not Decimal(0) < self.risk_fraction <= Decimal(1):
            raise ValueError("risk_fraction must be in (0, 1]")
        if not Decimal(0) < self.max_position_fraction <= Decimal(1):
            raise ValueError("max_position_fraction must be in (0, 1]")


def size_order(
    signal: TradeSignal,
    *,
    equity: Decimal,
    stop_price: Decimal,
    config: RiskConfig | None = None,
) -> ProposedOrder:
    config = config or RiskConfig()
    if equity <= 0 or signal.reference_price <= 0:
        raise ValueError("equity and price must be positive")
    if stop_price <= 0 or stop_price >= signal.reference_price:
        raise ValueError("long stop must be positive and below entry reference")
    risk_budget = equity * config.risk_fraction
    exposure_cap = equity * config.max_position_fraction
    per_unit_risk = signal.reference_price - stop_price
    by_risk = (risk_budget / per_unit_risk).to_integral_value(rounding=ROUND_DOWN)
    by_exposure = (exposure_cap / signal.reference_price).to_integral_value(rounding=ROUND_DOWN)
    quantity = int(min(by_risk, by_exposure))
    if quantity < 1:
        raise ValueError("risk limits permit no whole shares")
    key = (
        f"{signal.symbol}|{signal.timestamp.isoformat()}|BUY|{quantity}|"
        f"{signal.reference_price}|{stop_price}"
    )
    order_id = sha256(key.encode()).hexdigest()[:24]
    return ProposedOrder(
        order_id,
        signal.symbol,
        "BUY",
        quantity,
        signal.reference_price,
        stop_price,
        signal.timestamp,
    )
