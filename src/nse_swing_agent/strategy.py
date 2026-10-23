"""Starter trend/pullback hypothesis; intentionally not validated for profitability."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from .indicators import rsi, sma
from .models import OHLCVBar, TradeSignal


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    sma_fast_period: int = 50
    sma_slow_period: int = 200
    rsi_period: int = 14
    rsi_pullback_min: Decimal = Decimal("40")
    rsi_pullback_max: Decimal = Decimal("60")

    def __post_init__(self) -> None:
        if min(self.sma_fast_period, self.sma_slow_period, self.rsi_period) <= 0:
            raise ValueError("indicator periods must be positive")
        if self.sma_fast_period >= self.sma_slow_period:
            raise ValueError("fast SMA period must be shorter than slow SMA period")
        if not Decimal(0) <= self.rsi_pullback_min <= self.rsi_pullback_max <= Decimal(100):
            raise ValueError("invalid RSI band")


def generate_signals(
    bars: Sequence[OHLCVBar], config: StrategyConfig | None = None
) -> list[TradeSignal]:
    config = config or StrategyConfig()
    for previous, current in zip(bars, bars[1:], strict=False):
        if current.symbol != previous.symbol or current.timestamp <= previous.timestamp:
            raise ValueError("bars must be for one symbol in strictly increasing timestamp order")
    closes = [bar.close if bar.completed else None for bar in bars]
    fast, slow, strength = (
        sma(closes, config.sma_fast_period),
        sma(closes, config.sma_slow_period),
        rsi(closes, config.rsi_period),
    )
    return [
        TradeSignal(
            bar.symbol,
            bar.timestamp,
            "BUY",
            bar.close,
            "close > SMA fast > SMA slow; RSI in pullback band",
        )
        for i, bar in enumerate(bars)
        if bar.completed
        and fast[i] is not None
        and slow[i] is not None
        and strength[i] is not None
        and bar.close > fast[i] > slow[i]
        and config.rsi_pullback_min <= strength[i] <= config.rsi_pullback_max
    ]
