from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from nse_swing_agent.broker import PaperBroker
from nse_swing_agent.indicators import atr, rsi, sma
from nse_swing_agent.models import OHLCVBar, OrderStatus, TradeSignal
from nse_swing_agent.risk import RiskConfig, size_order
from nse_swing_agent.strategy import StrategyConfig, generate_signals


def bar(day: int, close: str, *, complete: bool = True, symbol: str = "TEST") -> OHLCVBar:
    value = D(close)
    return OHLCVBar(
        symbol,
        datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=day),
        value,
        value + 1,
        value - 1,
        value,
        100000,
        complete,
    )


def test_sma_warmup_and_missing_values() -> None:
    assert sma([D(1), D(2), D(3), D(4)], 3) == [None, None, D(2), D(3)]
    assert sma([D(1), None, D(3), D(4)], 2) == [None, None, None, D("3.5")]


def test_rsi_known_gain_and_flat_series() -> None:
    assert rsi([D(x) for x in range(15)], 14)[14] == D(100)
    assert rsi([D(5)] * 15, 14)[14] == D(50)
    assert rsi([D(5), None] + [D(6)] * 14, 14)[-1] is None


def test_atr_known_range_and_warmup() -> None:
    bars = [bar(0, "10"), bar(1, "11"), bar(2, "12")]
    assert atr(bars, 2) == [None, D("2"), D("2")]
    missing = SimpleNamespace(high=None, low=None, close=None)
    assert atr([bars[0], missing, bars[2]], 2) == [None, None, None]


def test_strategy_requires_full_warmup_and_completed_bar() -> None:
    config = StrategyConfig(2, 3, 2, D(40), D(100))
    bars = [bar(0, "10"), bar(1, "11"), bar(2, "12"), bar(3, "13", complete=False)]
    assert all(signal.timestamp != bars[-1].timestamp for signal in generate_signals(bars, config))
    assert generate_signals(bars[:-1] + [bar(3, "13")], config)


def test_risk_sizing_caps_exposure_and_rejects_bad_inputs() -> None:
    signal = TradeSignal("TEST", datetime.now(UTC), "BUY", D(100), "test")
    order = size_order(
        signal, equity=D(10000), stop_price=D(90), config=RiskConfig(D(".01"), D(".2"))
    )
    assert order.quantity == 10
    with pytest.raises(ValueError):
        size_order(signal, equity=D(0), stop_price=D(90))
    with pytest.raises(ValueError):
        size_order(signal, equity=D(10000), stop_price=D(100))


def test_paper_broker_duplicate_and_later_open_fill_only() -> None:
    signal = TradeSignal("TEST", datetime(2025, 1, 1, tzinfo=UTC), "BUY", D(100), "test")
    order = size_order(signal, equity=D(10000), stop_price=D(90))
    broker = PaperBroker()
    accepted = broker.submit(order)
    assert broker.submit(order) is accepted
    assert broker.on_bar(bar(0, "101")) == []
    filled = broker.on_bar(bar(1, "102"))[0]
    assert filled.status is OrderStatus.FILLED
    assert filled.fill is not None and filled.fill.price == D("102")
    assert broker.live_execution_enabled is False


def test_volume_reject_and_no_live_adapter() -> None:
    signal = TradeSignal("TEST", datetime(2025, 1, 1, tzinfo=UTC), "BUY", D(100), "test")
    order = size_order(
        signal, equity=D(1000000), stop_price=D(99), config=RiskConfig(D(".01"), D(".2"))
    )
    broker = PaperBroker()
    broker.submit(order)
    result = broker.on_bar(bar(1, "100"))[0]
    assert result.status is OrderStatus.REJECTED
    assert not hasattr(broker, "place_live_order")
