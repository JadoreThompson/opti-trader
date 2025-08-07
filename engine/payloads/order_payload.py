from enums import OrderType
from ..mixins import PayloadStateMixin


class OrderPayload(PayloadStateMixin):
    def __init__(self, payload: dict, internal_type: OrderType):
        super().__init__(payload)
        self._internal_type = internal_type
    
    @property
    def internal_type(self) -> OrderType:
        return self._internal_type