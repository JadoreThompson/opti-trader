from abc import ABC, abstractmethod
from enums import OrderType
from ..orders import SpotOrder
from ..order_context import OrderContext
from ..payloads import SpotPayload
from ..typing import ModifyRequest


class OrderTypeHandler(ABC):
    """Base class for handling specific order types."""

    @staticmethod
    def is_modifiable() -> bool:
        """Return True if orders can be modified (default False)."""
        return False

    @staticmethod
    def is_cancellable() -> bool:
        """Return True if handler provides custom cancel logic (default False)."""
        return False

    @abstractmethod
    def can_handle(self, order_type: OrderType) -> bool:
        """Return True if this handler supports the given order type."""

    @abstractmethod
    def handle(
        self, order: SpotOrder, payload: SpotPayload, context: OrderContext
    ) -> None:
        """Process a new order."""

    @abstractmethod
    def handle_filled(
        self,
        quantity: int,
        price: float,
        order: SpotOrder,
        payload: SpotPayload,
        context: OrderContext,
    ) -> None:
        """Handle resting order being filled."""

    def modify(
        self,
        request: ModifyRequest,
        payload: SpotPayload,
        context: OrderContext,
    ) -> None:
        """Modify an existing order."""

    def cancel(
        self,
        quantity: int,
        payload: SpotPayload,
        order: SpotOrder,
        context: OrderContext,
    ) -> None: ...
