from abc import ABC, abstractmethod
from pydantic import BaseModel

from enums import OrderType
from ..orders import Order
from ..order_context import OrderContext
from ..payloads import SpotPayload
from ..protocols import EngineProtocol


class OrderTypeHandler(ABC):
    """Base class for handling specific order types."""

    @staticmethod
    def is_modifiable() -> bool:
        """Return True if orders can be modified (default False)."""
        return False

    @abstractmethod
    def can_handle(self, order_type: OrderType) -> bool:
        """Return True if this handler supports the given order type."""

    @abstractmethod
    def handle_new(self, data: BaseModel, engine: EngineProtocol) -> list[dict]:
        """
        Handles a new incoming order.

        Returns:
            list[dict]: List of db records that were updated.
        """

    @abstractmethod
    def handle_filled(
        self,
        quantity: int,
        price: float,
        order: Order,
        payload: SpotPayload,
        context: OrderContext,
    ) -> list[dict]:
        """Handle resting order being filled."""

    def modify(
        self,
        request: BaseModel,
        payload: SpotPayload,
        order: Order,
        context: OrderContext,
    ) -> list[dict]:
        """Modify an existing order."""

    @abstractmethod
    def cancel(
        self,
        quantity: int,
        payload: SpotPayload,
        order: Order,
        context: OrderContext,
    ) -> list[dict]: ...
