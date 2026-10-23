"""Local paper broker. No network or live adapter; fills execute at a later bar open only."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .models import Fill, OHLCVBar, OrderStatus, ProposedOrder


class PaperBrokerInterface(Protocol):
    def submit(self, order: ProposedOrder) -> "PaperOrder": ...


@dataclass(frozen=True, slots=True)
class PaperOrder:
    proposed: ProposedOrder
    status: OrderStatus
    fill: Fill | None = None
    reason: str | None = None


class PaperBroker:
    """Only policy: fill full order at first same-symbol bar open strictly after creation.

    Reject if quantity exceeds 1% of that bar's volume. Open is known at the simulated
    execution timestamp. Orders are never filled from their signal bar or at its close.
    """

    def __init__(self, *, max_volume_fraction: Decimal = Decimal("0.01")) -> None:
        if not Decimal(0) < max_volume_fraction <= Decimal(1):
            raise ValueError("volume fraction must be in (0, 1]")
        self.max_volume_fraction = max_volume_fraction
        self._orders: dict[str, PaperOrder] = {}

    @property
    def live_execution_enabled(self) -> bool:
        return False

    def submit(self, order: ProposedOrder) -> PaperOrder:
        prior = self._orders.get(order.client_order_id)
        if prior is not None:
            if prior.proposed != order:
                raise ValueError("client order ID reused for a different order")
            return prior
        paper_order = PaperOrder(order, OrderStatus.ACCEPTED)
        self._orders[order.client_order_id] = paper_order
        return paper_order

    def on_bar(self, bar: OHLCVBar) -> list[PaperOrder]:
        updated: list[PaperOrder] = []
        for order_id, state in list(self._orders.items()):
            order = state.proposed
            if (
                state.status is not OrderStatus.ACCEPTED
                or order.symbol != bar.symbol
                or bar.timestamp <= order.created_at
            ):
                continue
            if order.quantity > int(Decimal(bar.volume) * self.max_volume_fraction):
                state = PaperOrder(
                    order, OrderStatus.REJECTED, reason="exceeds simulated volume participation cap"
                )
            else:
                fill = Fill(order_id, bar.symbol, order.quantity, bar.open, bar.timestamp)
                state = PaperOrder(order, OrderStatus.FILLED, fill=fill)
            self._orders[order_id] = state
            updated.append(state)
        return updated

    def get_order(self, client_order_id: str) -> PaperOrder | None:
        return self._orders.get(client_order_id)

    def orders(self) -> tuple[PaperOrder, ...]:
        return tuple(self._orders.values())
