from json import dumps

from enums import EventType, LiquidityRole, Side, StrategyType
from .balance_manager import BalanceManager
from .enums import CommandType, MatchOutcome
from .event_logger import EventLogger
from .execution_context import ExecutionContext
from .models import Command, CancelOrderCommand, ModifyOrderCommand, NewOrderCommand
from .orderbook import OrderBook
from .orders import Order
from .protocols import EngineProtocol, StrategyProtocol
from .stores import OrderStore
from .strategies import (
    SingleOrderStrategy,
    OCOStrategy,
    OTOStrategy,
    OTOCOStrategy,
)
from .typing import MatchResult


class SpotEngine(EngineProtocol):
    def __init__(self, instrument_ids: list[str] = None):
        self._strategy_handlers: dict[StrategyType, StrategyProtocol] = {
            StrategyType.SINGLE: SingleOrderStrategy(),
            StrategyType.OCO: OCOStrategy(),
            StrategyType.OTO: OTOStrategy(),
            StrategyType.OTOCO: OTOCOStrategy(),
        }
        self._balance_manager = BalanceManager()
        self._ctxs: dict[str, ExecutionContext] = {}

        if instrument_ids:
            for iid in instrument_ids:
                self._ctxs[iid] = ExecutionContext(
                    engine=self,
                    orderbook=OrderBook(),
                    balance_manager=self._balance_manager,
                    order_store=OrderStore(),
                )

    def process_command(self, command: Command) -> None:
        """Main entry point for processing all incoming commands."""
        handlers = {
            CommandType.NEW_ORDER: self._handle_new_order,
            CommandType.CANCEL_ORDER: self._handle_cancel_order,
            CommandType.MODIFY_ORDER: self._handle_modify_order,
        }
        handler = handlers.get(command.command_type)
        if handler:
            handler(command.data)

    def _handle_new_order(self, details: NewOrderCommand) -> None:
        ctx = self._ctxs.get(details.instrument_id)
        strategy = self._strategy_handlers.get(details.strategy_type)
        if not ctx or not strategy:
            return

        strategy.handle_new(details, ctx)

    def _handle_cancel_order(self, details: CancelOrderCommand) -> None:
        ctx = self._ctxs.get(details.symbol)
        if not ctx:
            return

        order = ctx.order_store.get(details.order_id)
        if not order:
            return

        strategy = self._strategy_handlers.get(order.strategy_type)
        strategy.cancel(order, ctx)

    def _handle_modify_order(self, details: ModifyOrderCommand) -> None:
        ctx = self._ctxs.get(details.symbol)
        if not ctx:
            return

        order = ctx.order_store.get(details.order_id)
        if not order:
            return

        strategy = self._strategy_handlers.get(order.strategy_type)
        strategy.modify(details, order, ctx)

    def match(self, taker_order: Order, ctx: ExecutionContext) -> MatchResult:
        """
        Public method for strategies to submit an order for immediate matching.
        This fulfills the EngineProtocol requirement cleanly.
        """
        return self._match(taker_order, ctx)

    def _match(self, taker_order: Order, ctx: ExecutionContext) -> MatchResult:
        opposite_side = Side.ASK if taker_order.side == Side.BID else Side.BID
        ob = ctx.orderbook
        last_best_price = None

        while taker_order.executed_quantity < taker_order.quantity:
            best_price = ob.best_ask if opposite_side is Side.ASK else ob.best_bid
            if last_best_price == best_price:
                break

            for maker_order in ob.get_orders(best_price, opposite_side):
                if taker_order.executed_quantity >= taker_order.quantity:
                    break

                unfilled_maker_qty = (
                    maker_order.quantity - maker_order.executed_quantity
                )
                trade_qty = min(
                    unfilled_maker_qty,
                    taker_order.quantity - taker_order.executed_quantity,
                )

                self._process_trade(
                    taker_order, maker_order, trade_qty, best_price, ctx
                )

            last_best_price = best_price

        if taker_order.executed_quantity == taker_order.quantity:
            return MatchResult(
                MatchOutcome.SUCCESS, taker_order.quantity, last_best_price
            )
        if taker_order.executed_quantity == 0:
            return MatchResult(MatchOutcome.FAILURE, 0, None)
        return MatchResult(
            MatchOutcome.PARTIAL, taker_order.executed_quantity, last_best_price
        )

    def _process_trade(
        self,
        taker_order: Order,
        maker_order: Order,
        quantity: float,
        price: float,
        ctx: ExecutionContext,
    ) -> None:
        """
        Handles the logic for a single trade event: updating quantities,
        notifying strategies, and removing filled orders.
        """
        taker_order.executed_quantity += quantity
        maker_order.executed_quantity += quantity

        if taker_order.side == Side.BID:
            self._balance_manager.increase_balance(taker_order.user_id, quantity)
        if maker_order.side == Side.BID:
            self._balance_manager.increase_balance(maker_order.user_id, quantity)

        taker_strategy = self._strategy_handlers[taker_order.strategy_type]
        maker_strategy = self._strategy_handlers[maker_order.strategy_type]
        taker_strategy.handle_filled(quantity, price, taker_order, ctx)
        maker_strategy.handle_filled(quantity, price, maker_order, ctx)

        self._log_fill_event(taker_order, price)
        self._log_fill_event(maker_order, price)

        if maker_order.executed_quantity == maker_order.quantity:
            ctx.orderbook.remove(maker_order, price)

        EventLogger.log_event(
            EventType.NEW_TRADE,
            user_id=taker_order.user_id,
            related_id=taker_order.id,
            details=dumps(
                {
                    "quantity": quantity,
                    "price": price,
                    "role": LiquidityRole.TAKER.value,
                }
            ),
        )
        EventLogger.log_event(
            EventType.NEW_TRADE,
            user_id=maker_order.user_id,
            related_id=maker_order.id,
            details=dumps(
                {
                    "quantity": quantity,
                    "price": price,
                    "role": LiquidityRole.MAKER.value,
                }
            ),
        )

    def _log_fill_event(self, order: Order, price: float) -> None:
        ev_details = {
            "executed_quantity": order.executed_quantity,
            "quantity": order.quantity,
            "price": price,
        }
        etype = (
            EventType.ORDER_FILLED
            if order.executed_quantity == order.quantity
            else EventType.ORDER_PARTIALLY_FILLED
        )
        EventLogger.log_event(
            etype, user_id=order.user_id, related_id=order.id, details=dumps(ev_details)
        )
