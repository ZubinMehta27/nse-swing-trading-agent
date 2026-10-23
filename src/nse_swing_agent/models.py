"""Validated domain types; money and prices use Decimal throughout."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class OHLCVBar:
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    completed: bool = True

    def __post_init__(self) -> None:
        _aware(self.timestamp)
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("OHLC values are inconsistent")
        if self.high < self.low or self.volume < 0:
            raise ValueError("high must be >= low and volume nonnegative")


@dataclass(frozen=True, slots=True)
class TradeSignal:
    symbol: str
    timestamp: datetime
    side: str
    reference_price: Decimal
    reason: str

    def __post_init__(self) -> None:
        _aware(self.timestamp)
        if self.side != "BUY" or self.reference_price <= 0:
            raise ValueError("only positive-price BUY signals are supported")


@dataclass(frozen=True, slots=True)
class ProposedOrder:
    client_order_id: str
    symbol: str
    side: str
    quantity: int
    reference_price: Decimal
    stop_price: Decimal
    created_at: datetime

    def __post_init__(self) -> None:
        _aware(self.created_at)
        if not self.client_order_id or not self.symbol.strip():
            raise ValueError("client order ID and symbol are required")
        if self.side != "BUY" or self.quantity <= 0:
            raise ValueError("paper orders must have positive quantity and BUY side")
        if (
            self.reference_price <= 0
            or self.stop_price <= 0
            or self.stop_price >= self.reference_price
        ):
            raise ValueError("order prices must be positive and stop below reference")


class OrderStatus(StrEnum):
    ACCEPTED = "accepted"
    FILLED = "filled"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class Fill:
    client_order_id: str
    symbol: str
    quantity: int
    price: Decimal
    timestamp: datetime

    def __post_init__(self) -> None:
        _aware(self.timestamp)
        if self.quantity <= 0 or self.price <= 0:
            raise ValueError("fill quantity and price must be positive")


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    quantity: int
    average_price: Decimal

    def __post_init__(self) -> None:
        if self.quantity <= 0 or self.average_price <= 0:
            raise ValueError("position quantity and average price must be positive")


@dataclass(frozen=True, slots=True)
class PortfolioState:
    cash: Decimal
    positions: dict[str, Position] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.cash < 0:
            raise ValueError("cash cannot be negative")
