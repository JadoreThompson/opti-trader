from typing import Protocol

from pydantic import BaseModel

from engine.execution_context import ExecutionContext
from engine.models import ModifyOrderCommand
from engine.orders import Order


class StrategyProtocol(Protocol):
    def handle_new(self, details: BaseModel, ctx: ExecutionContext):
        """Handles the creation of the orders for the strategy"""

    def handle_filled(
        self, quantity: int, price: float, order: Order, ctx: ExecutionContext
    ):
        """Handles the actions necessary when an order is filled."""

    def cancel(self, order: Order, ctx: ExecutionContext):
        """Handles the cancelling of the order"""

    def modify(self, details: ModifyOrderCommand, order: Order, ctx: ExecutionContext):
        """Handles the modification of the order"""
