from enums import Side
from .enums import Tag

class Order:
    def __init__(self, order_data: dict, tag: Tag, side: Side) -> None:
        self._order = order_data
        self._tag = tag
        self._side = side
    
    @property
    def tag(self) -> Tag:
        return self._tag
    
    @property
    def side(self) -> Side:
        return self._side
    
    @property
    def order(self) -> dict:
        return self._order
    
    def __str__(self) -> str:
        return self.__repr__()
        
    def __repr__(self) -> str:
        return f'Order(id={self._order['order_id']}, instrument={self._order['instrument']}, side={self._side}, tag={self._tag})'