from enums import OrderType, Side, EventType, OrderStatus
from ..config import MODIFY_REQUEST_SENTINEL
from ..enums import Tag
from ..event_service import EventService
from ..orders import SpotOrder
from ..order_context import OrderContext
from ..typing import ModifyRequest


class TPSLMixin:
    def _extract_updated_prices(
        self,
        request: ModifyRequest,
        is_limit_order: bool,
        payload: dict,
        sentinel: float = float("inf"),
    ) -> tuple[float, float, float]:
        updated_limit_price = sentinel
        updated_tp_price = sentinel
        updated_sl_price = sentinel

        is_filled = payload["status"] == OrderStatus.FILLED

        if (
            is_limit_order
            and not is_filled
            and request.limit_price not in (MODIFY_REQUEST_SENTINEL, None)
        ):
            updated_limit_price = request.limit_price
        if request.take_profit != MODIFY_REQUEST_SENTINEL:
            updated_tp_price = request.take_profit
        if request.stop_loss != MODIFY_REQUEST_SENTINEL:
            updated_sl_price = request.stop_loss

        return updated_limit_price, updated_tp_price, updated_sl_price

    def _verify_modify_request(
        self,
        request: ModifyRequest,
        is_limit_order: bool,
        payload: dict,
        context: OrderContext,
        sentinel: float = float("inf"),
    ) -> bool:
        entry_order = context.order_manager.get(request.order_id)
        if entry_order is None:
            return False

        is_filled = payload["status"] == OrderStatus.FILLED
        updated_limit_price, updated_tp_price, updated_sl_price = (
            self._extract_updated_prices(request, is_limit_order, payload, sentinel)
        )

        side = payload["side"]

        tmp_entry_price = (
            updated_limit_price
            if is_limit_order and updated_limit_price != sentinel
            else payload.get("limit_price") if is_limit_order else payload.get("price")
        )

        tmp_sl_price = (
            updated_sl_price
            if updated_sl_price != sentinel
            else payload.get("stop_loss")
        )

        tmp_tp_price = (
            updated_tp_price
            if updated_tp_price != sentinel
            else payload.get("take_profit")
        )

        if side == Side.BID:
            tmp_sl_price = tmp_sl_price if tmp_sl_price is not None else float("-inf")
            tmp_tp_price = tmp_tp_price if tmp_tp_price is not None else float("inf")
        elif side == Side.ASK:
            tmp_sl_price = tmp_sl_price if tmp_sl_price is not None else float("inf")
            tmp_tp_price = tmp_tp_price if tmp_tp_price is not None else float("-inf")

        if is_filled:
            if side == Side.BID and not (tmp_sl_price < tmp_tp_price):
                return False
            elif side == Side.ASK and not (tmp_sl_price > tmp_tp_price):
                return False
        else:
            if side == Side.BID and not (tmp_sl_price < tmp_entry_price < tmp_tp_price):
                return False
            elif side == Side.ASK and not (
                tmp_sl_price > tmp_entry_price > tmp_tp_price
            ):
                return False

        return True

    # TODO: Make room for futures
    def _modify_tp_sl(
        self,
        request: ModifyRequest,
        payload: dict,
        context: OrderContext,
        sentinel: float = float("inf"),
    ):
        entry_order = context.order_manager.get(request.order_id)
        if entry_order is None:
            return

        is_limit_order = payload["order_type"] in (OrderType.LIMIT, OrderType.LIMIT_OCO)
        is_filled = payload["status"] == OrderStatus.FILLED
        asset_balance = context.balance_manager.get_balance(payload["user_id"])
        ob = context.orderbook

        updated_limit_price, updated_tp_price, updated_sl_price = (
            self._extract_updated_prices(request, is_limit_order, payload, sentinel)
        )

        if not self._verify_modify_request(
            request, is_limit_order, payload, context, sentinel
        ):
            EventService.log_rejection(payload, asset_balance=asset_balance)
            return

        oco_order = context.oco_manager.get(entry_order.oco_id)
        if oco_order is None:
            return

        opposite_side = Side.ASK if payload["side"] == Side.BID else Side.BID

        # Modify limit order
        if is_limit_order and not is_filled and updated_limit_price != sentinel:
            context.order_manager.remove(payload["order_id"])
            ob.remove(entry_order, entry_order.price)
            new_entry_order = SpotOrder(
                entry_order.id,
                Tag.ENTRY,
                payload["side"],
                payload["quantity"],
                updated_limit_price,
                oco_id=oco_order.id,
            )
            context.order_manager.append(new_entry_order)
            ob.append(new_entry_order, new_entry_order.price)
            oco_order.leg_a = new_entry_order
            payload["limit_price"] = updated_limit_price

        # Modify stop loss
        if updated_sl_price != sentinel:
            sl_order = oco_order.leg_b
            if sl_order:
                ob.remove(sl_order, sl_order.price)
            if updated_sl_price is not None:
                new_sl_order = SpotOrder(
                    entry_order.id,
                    Tag.STOP_LOSS,
                    opposite_side,
                    payload["open_quantity"],
                    updated_sl_price,
                    oco_id=oco_order.id,
                )
                ob.append(new_sl_order, new_sl_order.price)
                oco_order.leg_b = new_sl_order
                payload["stop_loss"] = updated_sl_price

        # Modify take profit
        if updated_tp_price != sentinel:
            tp_order = oco_order.leg_c
            if tp_order:
                ob.remove(tp_order, tp_order.price)
            if updated_tp_price is not None:
                new_tp_order = SpotOrder(
                    entry_order.id,
                    Tag.TAKE_PROFIT,
                    opposite_side,
                    payload["open_quantity"],
                    updated_tp_price,
                    oco_id=oco_order.id,
                )
                ob.append(new_tp_order, new_tp_order.price)
                oco_order.leg_c = new_tp_order
                payload["take_profit"] = updated_tp_price

        EventService.log_order_event(
            EventType.ORDER_MODIFIED,
            payload,
            asset_balance=asset_balance,
            limit_price=payload["limit_price"],
            stop_loss=payload["stop_loss"],
            take_profit=payload["take_profit"],
        )
