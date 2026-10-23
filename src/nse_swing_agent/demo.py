"""Offline example using the bundled synthetic fixture; does not submit orders."""

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .models import OHLCVBar
from .risk import RiskConfig, size_order
from .strategy import StrategyConfig, generate_signals


def load_synthetic_fixture() -> list[OHLCVBar]:
    path = Path(__file__).resolve().parent / "data" / "synthetic_ohlcv.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            OHLCVBar(
                row["symbol"],
                datetime.fromisoformat(row["session_date"] + "T15:30:00+05:30"),
                Decimal(row["open"]),
                Decimal(row["high"]),
                Decimal(row["low"]),
                Decimal(row["close"]),
                int(row["volume"]),
            )
            for row in csv.DictReader(handle)
        ]


def main() -> None:
    bars = load_synthetic_fixture()
    signals = generate_signals(bars, StrategyConfig())
    print(f"Synthetic offline fixture: {len(bars)} bars; not live market data.")
    if not signals:
        print("No qualifying signals.")
    for signal in signals:
        stop = signal.reference_price * Decimal("0.97")
        order = size_order(signal, equity=Decimal("1000000"), stop_price=stop, config=RiskConfig())
        print(
            f"{signal.timestamp.date()} {signal.symbol} {signal.side} @ {signal.reference_price}: "
            f"risk-approved proposal qty={order.quantity}, stop={order.stop_price}"
        )
        print(f"  client order ID: {order.client_order_id}")


if __name__ == "__main__":
    main()
