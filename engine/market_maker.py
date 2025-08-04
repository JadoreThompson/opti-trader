from numpy import arange

from config import SUPER_USER
from enums import MarketType, OrderStatus, OrderType, Side
from utils.utils import get_datetime
from .enums import Tag
from .managers import BalanceManager
from .orderbook import OrderBook
from .orders import SpotOrder


# TODO
class MarketMaker:
    def __init__(self):
        self._user_id = SUPER_USER

    def seed(
        self,
        instrument: str,
        ob: OrderBook,
        balance_manager: BalanceManager,
        total_quantity: int = 1_000_000,
    ) -> list[dict]:
        cur_price = ob.price
        half = cur_price / 2
        lowest, highest = half, cur_price + half
        balance_manager.increase_balance(self._user_id, total_quantity)

        q = int(total_quantity // cur_price)
        payloads = []

        for p in arange(lowest, highest + 1):
            side = [Side.BID, Side.ASK][int(p) % 2]
            p = float(p)
            payload = {
                "user_id": self._user_id,
                "order_id": f"{p}",
                "closed_at": None,
                "instrument": instrument,
                "side": side.value,
                "market_type": MarketType.SPOT.value,
                "order_type": OrderType.LIMIT.value,
                "price": None,
                "limit_price": p,
                "filled_price": None,
                "closed_price": None,
                "realised_pnl": None,
                "unrealised_pnl": None,
                "status": OrderStatus.PENDING.value,
                "quantity": q,
                "standing_quantity": q,
                "open_quantity": 0,
                "stop_loss": None,
                "take_profit": None,
                "created_at": get_datetime(),
            }
            payloads.append(payload)
            order = SpotOrder(payload["order_id"], Tag.ENTRY, side, q, p)
            ob.append(order, order.price)

        return payloads