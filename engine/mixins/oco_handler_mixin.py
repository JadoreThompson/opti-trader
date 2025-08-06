from enums import EventType, OrderStatus, OrderType, Side
from ..config import MODIFY_REQUEST_SENTINEL
from ..managers import BalanceManager
from ..enums import MatchOutcome, Tag
from ..event_service import EventService
from ..managers import OCOManager
from ..orderbook import OrderBook
from ..orders import OCOOrder, SpotOrder
from ..order_context import OrderContext


class OCOOrderHandlerMixin:
    @staticmethod
    def _create_order(order: SpotOrder, oco_manager: OCOManager) -> OCOOrder:
        oco_order: OCOOrder = oco_manager.create()
        order.set_oco_id(oco_order.id)
        oco_order.leg_a = order
        return oco_order

    @staticmethod
    def _handle_match_outcome(
        outcome: MatchOutcome, payload: dict, order: OCOOrder, orderbook: OrderBook
    ) -> None:
        if outcome != MatchOutcome.FAILURE:
            opposite_side = Side.ASK if payload["side"] == Side.BID else Side.ASK

            if payload["stop_loss"] is not None:
                sl_order = SpotOrder(
                    payload["order_id"],
                    Tag.STOP_LOSS,
                    opposite_side,
                    payload["open_quantity"],
                    payload["stop_loss"],
                    oco_id=order.id,
                )
                order.leg_b = sl_order
                orderbook.append(sl_order, sl_order.price)

            if payload["take_profit"] is not None:
                tp_order = SpotOrder(
                    payload["order_id"],
                    Tag.STOP_LOSS,
                    opposite_side,
                    payload["open_quantity"],
                    payload["take_profit"],
                    oco_id=order.id,
                )
                order.leg_c = tp_order
                orderbook.append(tp_order, tp_order.price)

    def _cancel_order(
        self,
        quantity: int,
        payload: dict,
        order: SpotOrder,
        context: OrderContext,
    ) -> None:
        """Cancel or reduce an existing order."""
        ob = context.order_book
        bm = context.balance_manager
        oco_order = context.oco_manager.get(order.oco_id)
        is_in_book = order.quantity != order.filled_quantity

        asset_balance = bm.get_balance(payload["user_id"])
        standing_quantity = payload["standing_quantity"]
        remaining_quantity = standing_quantity - quantity
        payload["standing_quantity"] = remaining_quantity
        order.quantity -= quantity

        if remaining_quantity == 0:
            if is_in_book:
                ob.remove(order, order.price)

            if payload["open_quantity"] == 0:
                payload["status"] = OrderStatus.CANCELLED

                # Fail fast
                if payload["stop_loss"] is not None:
                    ob.remove(oco_order.leg_b, oco_order.leg_b.price)
                if payload["take_profit"] is not None:
                    ob.remove(oco_order.leg_c, oco_order.leg_c.price)

                context.oco_manager.remove(order.oco_id)
            else:
                payload["status"] = OrderStatus.FILLED

            if bm.get_balance(payload["user_id"]) == 0:
                bm.remove(payload["user_id"])

        EventService.log_order_event(
            EventType.ORDER_CANCELLED,
            payload,
            asset_balance=asset_balance,
            quantity=quantity,
        )
