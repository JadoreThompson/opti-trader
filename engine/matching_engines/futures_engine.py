from asyncio import AbstractEventLoop
from json import loads
from logging import getLogger

from config import (
    FUTURES_QUEUE_CHANNEL,
    REDIS_CLIENT,
)
from enums import (
    EventType,
    MarketType,
    OrderStatus,
    OrderType,
    Side,
)
from utils.utils import get_exc_line
from .engine import Engine
from ..config import MODIFY_REQUEST_SENTINEL
from ..enums import MatchOutcome, Tag
from ..orderbook import OrderBook
from ..orders import Order
from ..position import Position
from ..tasks import log_event
from ..typing import (
    CloseRequest,
    MatchResult,
    ModifyRequest,
    Event,
    EnginePayload,
    EnginePayloadTopic,
    SupportsAppend,
)

logger = getLogger(__name__)


class FuturesEngine(Engine[Order]):
    def __init__(
        self,
        loop: AbstractEventLoop | None = None,
        queue: SupportsAppend | None = None,
        orderbooks: dict[str, OrderBook[Order]] | None = None,
    ) -> None:
        super().__init__(loop, queue)
        self._positions: dict[str, Position] = {}
        self._orderbooks: dict[str, OrderBook[Order]] = orderbooks or {}

    async def run(self) -> None:
        async with REDIS_CLIENT.pubsub() as ps:
            await ps.subscribe(FUTURES_QUEUE_CHANNEL)
            async for m in ps.listen():
                if m["type"] == "subscribe":
                    continue

                try:
                    payload = EnginePayload(**loads(m["data"]))

                    if payload.topic == EnginePayloadTopic.CREATE:
                        self.place_order(payload.data)
                    elif payload.topic == EnginePayloadTopic.CANCEL:
                        self.cancel_order(CloseRequest(**payload.data))
                    elif payload.topic == EnginePayloadTopic.MODIFY:
                        self.modify_order(ModifyRequest(**payload.data))
                    elif payload.topic == EnginePayloadTopic.CLOSE:
                        self.close_order(CloseRequest(**payload.data))

                except Exception as e:
                    logger.error(
                        f"Error: {type(e)} - {str(e)} - line: {get_exc_line()} \n{e}"
                    )

    def place_order(self, payload: dict) -> float | None:
        """
        Places a new order in the futures engine.

        Creates an entry order and attempts to match it against the order book.
        If not immediately filled, the order is added to the book. Handles
        take-profit and stop-loss setup.

        Args:
            payload (dict): Order details including instrument, side, quantity,
                type, and limit price.

        Returns:
            float | None: Price matched or partially matched at.
        """
        ob = self._orderbooks.setdefault(payload["instrument"], OrderBook())
        if payload["order_id"] in self._positions:
            raise ValueError(
                f"Position with order_id {payload['order_id']} already exists."
            )

        pos = self._positions.setdefault(payload["order_id"], Position(payload))
        order = Order(pos.id, Tag.ENTRY, payload["side"], payload["quantity"])

        entry_price = payload["limit_price"] or payload["price"]

        if payload["order_type"] == OrderType.LIMIT and not (
            (  # Checking if not crossable
                order.side == Side.BID
                and ob.best_ask is not None
                and entry_price >= ob.best_ask
            )
            or (
                order.side == Side.ASK
                and ob.best_bid is not None
                and entry_price <= ob.best_bid
            )
        ):
            order.price = entry_price
            ob.append(order, order.price)
            pos.entry_order = order
            self._push_order_payload(payload)
            log_event.delay(
                Event(
                    event_type=EventType.ORDER_PLACED,
                    user_id=payload["user_id"],
                    order_id=order.id,
                    quantity=order.quantity,
                    price=order.price,
                    asset_balance=payload["open_quantity"],
                ).model_dump()
            )
            return

        result: MatchResult = self._match(order, ob)
        order.filled_quantity = result.quantity

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)
            self._place_tp_sl(pos, ob)
            pos.apply_entry_fill(result.quantity, result.price)

            log_event.delay(
                Event(
                    event_type=(
                        EventType.ORDER_FILLED
                        if result.outcome == MatchOutcome.SUCCESS
                        else EventType.ORDER_PARTIALLY_FILLED
                    ),
                    user_id=payload["user_id"],
                    order_id=payload["order_id"],
                    quantity=result.quantity,
                    price=result.price,
                    asset_balance=payload["open_quantity"],
                    metadata={"market_type": MarketType.FUTURES},
                ).model_dump()
            )

            if result.outcome == MatchOutcome.SUCCESS:
                return self._push_order_payload(payload)

        price = entry_price or result.price or ob.price  # TODO: Check ob fallback
        order.price = price
        ob.append(order, price)
        pos.entry_order = order

        log_event.delay(
            Event(
                event_type=EventType.ORDER_PLACED,
                user_id=payload["user_id"],
                order_id=order.id,
                quantity=order.quantity - order.filled_quantity,
                price=order.price,
                asset_balance=payload["open_quantity"],
            ).model_dump()
        )
        self._push_order_payload(payload)

    def close_order(self, request: CloseRequest) -> None:
        """
        Closes an existing position based on the provided request.

        Attempts to match the opposing side of the order to close it, updating
        the position and cleaning up TP/SL orders if fully closed.

        Args:
            request (CloseRequest): Request specifying the order ID and quantity
                to close.
        """
        pos = self._positions.get(request.order_id)

        if pos is None:
            msg = f"Position not found for order ID: {request.order_id}"
            logger.warning(msg)
            return

        ob = self._orderbooks[pos.instrument]

        if pos.status == OrderStatus.PENDING:
            return log_event.delay(
                Event(
                    event_type=EventType.ORDER_REJECTED,
                    order_id=pos.id,
                    user_id=pos.payload["user_id"],
                    asset_balance=pos.payload["open_quantity"],
                ).model_dump()
            )

        requested_qty = self._validate_close_req_quantity(
            request.quantity, pos.open_quantity
        )

        dummy = Order(
            pos.id,
            Tag.ENTRY,
            Side.BID if pos.payload["side"] == Side.ASK else Side.ASK,
            requested_qty,
        )

        result: MatchResult = self._match(dummy, ob)

        if result.outcome in (MatchOutcome.PARTIAL, MatchOutcome.SUCCESS):
            ob.set_price(result.price)
            pos.apply_close(result.quantity, result.price)

            if pos.open_quantity == 0:
                self._remove_tp_sl(pos, ob)

                if pos.standing_quantity == 0:
                    event_type = EventType.ORDER_CLOSED
                    self._positions.pop(pos.id)
                else:
                    event_type = EventType.ORDER_PARTIALLY_CLOSED
            else:
                self._mutate_tp_sl_quantity(pos)
                event_type = EventType.ORDER_PARTIALLY_CLOSED

            log_event.delay(
                Event(
                    event_type=event_type,
                    order_id=pos.id,
                    user_id=pos.payload["user_id"],
                    quantity=result.quantity,
                    price=result.price,
                    asset_balance=pos.open_quantity,
                    metadata={"market_type": MarketType.FUTURES},
                ).model_dump()
            )
            self._push_order_payload(pos.payload)

    def cancel_order(self, request: CloseRequest) -> None:
        """
        Cancels the standing quantity of an existing order.
        If 'ALL' is passed as the quantity and the open_quantity is 0
        then the order and it's relating position if removed. Else
        the order is partially cancelled.

        Args:
            request (CloseRequest): Request with order ID and quantity to cancel.
        """
        pos = self._positions.get(request.order_id)
        if pos is None:
            logger.warning(f"Position not found for order ID: {request.order_id}")
            return

        if pos.status not in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED):
            return log_event.delay(
                Event(
                    event_type=EventType.ORDER_REJECTED,
                    order_id=pos.id,
                    user_id=pos.payload["user_id"],
                    asset_balance=pos.payload["open_quantity"],
                ).model_dump()
            )

        ob = self._orderbooks[pos.instrument]
        requested_quantity = self._validate_close_req_quantity(
            request.quantity, pos.standing_quantity
        )
        pos.apply_cancel(requested_quantity)

        if pos.status == OrderStatus.CANCELLED:
            ob.remove(pos.entry_order, pos.entry_order.price)
            self._positions.pop(pos.id)
        elif pos.status == OrderStatus.FILLED:
            ob.remove(pos.entry_order, pos.entry_order.price)

        log_event.delay(
            Event(
                event_type=EventType.ORDER_CANCELLED,
                order_id=pos.id,
                user_id=pos.payload["user_id"],
                quantity=requested_quantity,
                asset_balance=pos.payload["open_quantity"],
            ).model_dump()
        )
        self._push_order_payload(pos.payload)

    def modify_order(self, request: ModifyRequest) -> None:
        """
        Modifies the properties of an order. If necessary
        alters the postiion of it's TP, SL and/or entry order
        if order was a LIMIT order.

        Args:
            request (ModifyRequest): ModifyRequest containing the details.
        """

        def reject_request(payload: dict, asset_balance: int) -> None:
            log_event.delay(
                Event(
                    event_type=EventType.ORDER_REJECTED,
                    order_id=payload["order_id"],
                    user_id=payload["user_id"],
                    asset_balance=asset_balance,
                ).model_dump()
            )

        pos = self._positions.get(request.order_id)
        if pos is None:
            logger.warning(f"Position not found for order ID: {request.order_id}")
            return

        payload = pos.payload

        is_limit_order = payload["order_type"] == OrderType.LIMIT
        is_filled = payload["status"] in (
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
        )

        sentinel = float("inf")
        updated_limit_price = sentinel
        updated_tp_price = sentinel
        from ..config import MODIFY_REQUEST_SENTINEL
        updated_sl_price = sentinel

        if (
            from ..config import MODIFY_REQUEST_SENTINEL
            is_limit_order
            and not is_filled
            from ..config import MODIFY_REQUEST_SENTINEL
        , None
        ):
            updated_limit_price = request.limit_price
    
            updated_tp_price = request.take_profit
    
            updated_sl_price = request.stop_loss

        ob = self._orderbooks[payload["instrument"]]
        asset_balance = pos.open_quantity
        ob_price: float = ob.price

        # Setting temporary prices based on the request
        tmp_sl_price = float("-inf") if payload["side"] == Side.BID else float("inf")
        if updated_sl_price != sentinel:
            if updated_sl_price is not None:
                tmp_sl_price = updated_sl_price
        elif payload["stop_loss"] is not None:
            tmp_sl_price = payload["stop_loss"]

        tmp_tp_price = float("inf") if payload["side"] == Side.BID else float("-inf")
        if updated_tp_price != sentinel:
            if updated_tp_price is not None:
                tmp_tp_price = updated_tp_price
        elif payload["take_profit"] is not None:
            tmp_tp_price = payload["take_profit"]

        tmp_limit_price = sentinel
        if is_limit_order:
            if updated_limit_price != sentinel:
                tmp_limit_price = updated_limit_price
            else:
                tmp_limit_price = payload["limit_price"]

        # Validating
        if is_limit_order:
            if (
                is_filled
                and payload["side"] == Side.BID
                and not (tmp_sl_price < tmp_tp_price)
            ):
                return reject_request(payload, asset_balance)

            if (
                is_filled
                and payload["side"] == Side.ASK
                and not (tmp_sl_price > tmp_tp_price)
            ):
                return reject_request(payload, asset_balance)

            if (
                not is_filled
                and payload["side"] == Side.BID
                and not (tmp_sl_price < tmp_limit_price <= ob_price < tmp_tp_price)
            ):
                return reject_request(payload, asset_balance)

            if (
                not is_filled
                and payload["side"] == Side.ASK
                and not (tmp_sl_price > tmp_limit_price >= ob_price > tmp_tp_price)
            ):
                return reject_request(payload, asset_balance)

        if (
            is_filled
            and payload["side"] == Side.BID
            and not (tmp_sl_price < tmp_tp_price)
        ):
            return reject_request(payload, asset_balance)

        if (
            is_filled
            and payload["side"] == Side.ASK
            and not (tmp_sl_price > tmp_tp_price)
        ):
            return reject_request(payload, asset_balance)

        if (
            not is_filled
            and payload["side"] == Side.BID
            and not (tmp_sl_price < ob_price < tmp_tp_price)
        ):
            return reject_request(payload, asset_balance)

        if (
            not is_filled
            and payload["side"] == Side.ASK
            and not (tmp_sl_price > ob_price > tmp_tp_price)
        ):
            return reject_request(payload, asset_balance)

        # Cancel and Replace
        if is_limit_order and not is_filled:
            order = pos.entry_order
            ob.remove(order, order.price)
            new_order = Order(
                order.id,
                Tag.ENTRY,
                payload["side"],
                payload["quantity"],
                tmp_limit_price,
            )
            new_order.filled_quantity = order.filled_quantity
            pos.entry_order = new_order
            ob.append(new_order, new_order.price)

        if is_filled and updated_sl_price != sentinel:
            if pos.stop_loss_order is not None:
                ob.remove(pos.stop_loss_order, pos.stop_loss_order.price)
                pos.stop_loss_order = None

            if updated_sl_price is not None:
                new_order = Order(
                    payload["order_id"],
                    Tag.STOP_LOSS,
                    Side.ASK if payload["side"] == Side.BID else Side.BID,
                    payload["open_quantity"],
                    updated_sl_price,
                )
                pos.stop_loss_order = new_order
                ob.append(new_order, new_order.price)

        if is_filled and updated_tp_price != sentinel:
            if pos.take_profit_order is not None:
                ob.remove(pos.take_profit_order, pos.take_profit_order.price)
                pos.take_profit_order = None

            if updated_tp_price is not None:
                new_order = Order(
                    payload["order_id"],
                    Tag.TAKE_PROFIT,
                    Side.ASK if payload["side"] == Side.BID else Side.BID,
                    payload["open_quantity"],
                    updated_tp_price,
                )
                pos.take_profit_order = new_order
                ob.append(new_order, new_order.price)

        if is_limit_order and not is_filled and updated_limit_price != sentinel:
            payload["limit_price"] = updated_limit_price

        payload["stop_loss"] = (
            updated_sl_price if updated_sl_price != sentinel else payload["stop_loss"]
        )
        payload["take_profit"] = (
            updated_tp_price if updated_tp_price != sentinel else payload["take_profit"]
        )

        log_event.delay(
            Event(
                event_type=EventType.ORDER_MODIFIED,
                user_id=payload["user_id"],
                order_id=payload["order_id"],
                asset_balance=asset_balance,
                limit_price=payload["limit_price"],
                stop_loss=payload["stop_loss"],
                take_profit=payload["take_profit"],
            ).model_dump()
        )

        self._push_order_payload(payload)

    def _handle_fill(
        self,
        order: Order,
        filled_quantity: int,
        price: float,
        ob: OrderBook,
    ) -> None:
        """
        Applies fill effects to positions, removes orders from the book, and
        finalizes positions if closed.

        Args:
            order (Order): Touched order.
            touched_quantity (int): Touched quantity.
            price (float): Execution price.
            ob (OrderBook): Relevant order book.
        """
        pos = self._positions.get(order.id)
        if pos is None:
            logger.warning(f"Position not found for order ID: {order.id}")
            return

        event_type = EventType.ORDER_FILLED
        if order.tag == Tag.ENTRY:
            pos.apply_entry_fill(filled_quantity, price)
            ob.remove(order, order.price)

            if pos.take_profit_order is not None or pos.stop_loss_order is not None:
                self._mutate_tp_sl_quantity(pos)
            else:
                self._place_tp_sl(pos, ob)
        else:
            pos.apply_close(filled_quantity, price)
            self._remove_tp_sl(pos, ob)

            if pos.status == OrderStatus.CLOSED:
                self._positions.pop(pos.id)
                event_type = EventType.ORDER_CLOSED

        log_event.delay(
            Event(
                event_type=event_type,
                order_id=pos.id,
                user_id=pos.payload["user_id"],
                quantity=filled_quantity,
                price=price,
                asset_balance=pos.open_quantity,
                metadata={"market_type": MarketType.FUTURES},
            ).model_dump()
        )
        self._push_order_payload(pos.payload)

    def _handle_touched_order(
        self,
        order: Order,
        touched_quantity: int,
        price: float,
        ob: OrderBook,
    ) -> None:
        """
        Updates positions with touched quantities and adjusts TP/SL accordingly.

        Args:
            order (Order): Touched order.
            touched_quantity (int): Touched quantity.
            price (float): Execution price.
            ob (OrderBook): Relevant order book.
        """
        pos = self._positions.get(order.id)
        if pos is None:
            logger.warning(f"Position not found for order ID: {order.id}")
            return

        if order.tag == Tag.ENTRY:
            pos.apply_entry_fill(touched_quantity, price)

            if pos.take_profit_order is not None or pos.stop_loss_order is not None:
                self._mutate_tp_sl_quantity(pos)
            else:
                self._place_tp_sl(pos, ob)
        else:
            pos.apply_close(touched_quantity, price)
            self._mutate_tp_sl_quantity(pos)

        log_event.delay(
            Event(
                event_type=(
                    EventType.ORDER_PARTIALLY_FILLED
                    if pos.standing_quantity > 0
                    else EventType.ORDER_PARTIALLY_CLOSED
                ),
                order_id=pos.id,
                user_id=pos.payload["user_id"],
                quantity=touched_quantity,
                price=price,
                asset_balance=pos.open_quantity,
                metadata={"market_type": MarketType.FUTURES},
            ).model_dump()
        )
        self._push_order_payload(pos.payload)

    def _place_tp_sl(self, pos: Position, ob: OrderBook) -> None:
        """
        Places take-profit and stop-loss orders for a position if specified.

        Args:
            pos (Position): The position to attach exit orders to.
            ob (OrderBook): Order book for the position's instrument.
        """
        payload = pos.payload
        exit_side = Side.BID if payload["side"] == Side.ASK else Side.ASK

        if payload["take_profit"] is not None:
            new_order = Order(
                pos.id,
                Tag.TAKE_PROFIT,
                exit_side,
                pos.open_quantity,
                payload["take_profit"],
            )
            pos.take_profit_order = new_order
            ob.append(new_order, new_order.price)

        if payload["stop_loss"] is not None:
            new_order = Order(
                pos.id,
                Tag.STOP_LOSS,
                exit_side,
                pos.open_quantity,
                payload["stop_loss"],
            )
            pos.stop_loss_order = new_order
            ob.append(new_order, new_order.price)

    def _mutate_tp_sl_quantity(self, pos: Position) -> None:
        """
        Adjusts TP/SL order quantities to match current open position quantity.

        Args:
            pos (Position): Position whose TP/SL orders should be updated.
        """
        if pos.take_profit_order is not None:
            pos.take_profit_order.quantity = pos.open_quantity
            pos.take_profit_order.filled_quantity = 0
        if pos.stop_loss_order is not None:
            pos.stop_loss_order.quantity = pos.open_quantity
            pos.stop_loss_order.filled_quantity = 0

    def _remove_tp_sl(self, pos: Position, ob: OrderBook[Order]) -> None:
        """
        Removes take-profit and stop-loss orders associated with a position.

        Args:
            pos (Position): The position whose TP/SL orders should be removed.
            ob (OrderBook): Order book from which to remove the orders.
        """
        if pos.take_profit_order is not None:
            ob.remove(pos.take_profit_order, pos.take_profit_order.price)
            pos.take_profit_order = None
        if pos.stop_loss_order is not None:
            ob.remove(pos.stop_loss_order, pos.stop_loss_order.price)
            pos.stop_loss_order = None
