from enums import EventType, OrderStatus, OrderType
from .order_type_handler import OrderTypeHandler
from ..config import MODIFY_REQUEST_SENTINEL
from ..event_service import EventService
from ..enums import Tag
from ..mixins import LimitOrderHandlerMixin, StopOrderHandlerMixin
from ..orderbook import OrderBook
from ..order_context import OrderContext
from ..orders import Order, OTOOrder
from ..protocols import EngineProtocol, PayloadProtocol
from ..typing import (
    LegModification,
    OTOEnginePayloadData,
    OTOModifyRequest,
)
from ..utils import get_price_key


# class OTOCOOrderHandler(
#     LimitOrderHandlerMixin, StopOrderHandlerMixin, OrderTypeHandler
# ): ...
