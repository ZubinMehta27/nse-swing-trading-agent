"""Pure indicators. None marks unavailable warm-up or missing observations."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol


def sma(values: Sequence[Decimal | None], period: int) -> list[Decimal | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    result: list[Decimal | None] = []
    for i in range(len(values)):
        window = values[max(0, i - period + 1) : i + 1]
        result.append(
            sum(window) / period
            if len(window) == period and all(v is not None for v in window)
            else None
        )
    return result


def rsi(values: Sequence[Decimal | None], period: int = 14) -> list[Decimal | None]:
    """Wilder RSI; warm-up requires period consecutive price changes."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[Decimal | None] = [None] * len(values)
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    avg_gain: Decimal | None = None
    avg_loss: Decimal | None = None
    previous: Decimal | None = None
    for i, value in enumerate(values):
        if value is None:
            gains.clear()
            losses.clear()
            avg_gain = avg_loss = previous = None
            continue
        if previous is None:
            previous = value
            continue
        change = value - previous
        previous = value
        gain, loss = max(change, Decimal(0)), max(-change, Decimal(0))
        if avg_gain is None:
            gains.append(gain)
            losses.append(loss)
            if len(gains) == period:
                avg_gain = sum(gains) / period
                avg_loss = sum(losses) / period
        else:
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_gain is not None and avg_loss is not None:
            out[i] = (
                Decimal(50)
                if avg_gain == avg_loss == 0
                else Decimal(100)
                if avg_loss == 0
                else Decimal(0)
                if avg_gain == 0
                else 100 - 100 / (1 + avg_gain / avg_loss)
            )
    return out


class _BarLike(Protocol):
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None


def atr(bars: Sequence[_BarLike], period: int = 14) -> list[Decimal | None]:
    """Wilder ATR over objects exposing high, low, close; missing bars reset warm-up."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[Decimal | None] = []
    trs: list[Decimal] = []
    average: Decimal | None = None
    previous_close: Decimal | None = None
    for bar in bars:
        high, low, close = bar.high, bar.low, bar.close
        if high is None or low is None or close is None:
            out.append(None)
            trs.clear()
            average = previous_close = None
            continue
        tr = (
            max(high - low, abs(high - previous_close), abs(low - previous_close))
            if previous_close is not None
            else high - low
        )
        previous_close = close
        if average is None:
            trs.append(tr)
            if len(trs) == period:
                average = sum(trs) / period
        else:
            average = (average * (period - 1) + tr) / period
        out.append(average)
    return out
