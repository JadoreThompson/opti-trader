from json import dumps

from enums import EventType, LiquidityRole, OrderType, Side, StrategyType
from .balance_manager import BalanceManager
from .enums import CommandType, MatchOutcome
from .event_logger import EventLogger
from .execution_context import ExecutionContext
from .models import (
    Command,
    CancelOrderCommand,
    ModifyOrderCommand,
    NewInstrument,
    NewOrderCommand,
)
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
                    order_store=OrderStore(),
                    instrument_id=iid,
                )

    def process_command(self, command: Command) -> None:
        """Main entry point for processing all incoming commands."""
        handlers = {
            CommandType.NEW_ORDER: self._handle_new_order,
            CommandType.CANCEL_ORDER: self._handle_cancel_order,
            CommandType.MODIFY_ORDER: self._handle_modify_order,
            CommandType.NEW_INSTRUMENT: self._handle_new_instrument,
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

    def _handle_new_instrument(self, details: NewInstrument):
        self._ctxs[details.instrument_id] = ExecutionContext(
            engine=self,
            orderbook=OrderBook(),
            order_store=OrderStore(),
            instrument_id=details.instrument_id,
        )

    def match(self, taker_order: Order, ctx: ExecutionContext) -> MatchResult:
        """
        Public method for strategies to submit an order for immediate matching.
        This fulfills the EngineProtocol requirement cleanly.
        """
        if not self._check_sufficient_balance(
            taker_order, taker_order.quantity, taker_order.price, ctx.instrument_id
        ):
            handler = self._strategy_handlers[taker_order.strategy_type]
            handler.cancel(taker_order, ctx)
            return MatchResult(
                outcome=MatchOutcome.UNAUTHORISED, quantity=0, price=None
            )

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

                if not self._check_sufficient_balance(
                    maker_order, trade_qty, best_price, ctx.instrument_id
                ):
                    handler = self._strategy_handlers[maker_order.strategy_type]
                    handler.cancel(maker_order, ctx)
                    continue

                if maker_order.executed_quantity == 0:
                    if maker_order.side == Side.BID:
                        BalanceManager.increase_cash_escrow(
                            maker_order.user_id,
                            maker_order.quantity * maker_order.price,
                        )
                    else:
                        BalanceManager.increase_asset_escrow(
                            maker_order.user_id, ctx.instrument_id, maker_order.quantity
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

    def _check_sufficient_balance(
        self, order: Order, quantity: float, price: float, instrument_id: str
    ) -> bool:
        """
        Checks if the user has sufficient balance to execute this trade.

        Args:
            order (Order): Order being used in the trade.
            quantity (float): Quantity being matched
            price (float): _description_

        Returns:
            bool:
                - True: Sufficient balance.
                - False: Insufficient balance.
        """
        if order.order_type == OrderType.MARKET:
            # In a more complex system, balance checks would be made.
            # For now we're assuming the amount for the trade was already
            # escrowed at the HTTP API layer.
            return True

        if order.side == Side.ASK:
            return quantity <= BalanceManager.get_available_asset_balance(
                order.user_id, instrument_id
            )

        trade_value = quantity * price
        return trade_value <= BalanceManager.get_available_cash_balance(order.user_id)

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
            BalanceManager.settle_bid(
                taker_order.user_id, ctx.instrument_id, quantity, price
            )
            BalanceManager.settle_ask(
                maker_order.user_id, ctx.instrument_id, quantity, price
            )
        else:
            BalanceManager.settle_ask(
                taker_order.user_id, ctx.instrument_id, quantity, price
            )
            BalanceManager.settle_bid(
                maker_order.user_id, ctx.instrument_id, quantity, price
            )

        taker_strategy = self._strategy_handlers[taker_order.strategy_type]
        maker_strategy = self._strategy_handlers[maker_order.strategy_type]
        taker_strategy.handle_filled(quantity, price, taker_order, ctx)
        maker_strategy.handle_filled(quantity, price, maker_order, ctx)

        self._log_fill_event(taker_order, price, ctx.instrument_id)
        self._log_fill_event(maker_order, price, ctx.instrument_id)

        if maker_order.executed_quantity == maker_order.quantity:
            ctx.orderbook.remove(maker_order, price)

        EventLogger.log_event(
            EventType.NEW_TRADE,
            user_id=taker_order.user_id,
            related_id=taker_order.id,
            instrument_id=ctx.instrument_id,
            details={
                "quantity": quantity,
                "price": price,
                "role": LiquidityRole.TAKER.value,
            },
        )
        EventLogger.log_event(
            EventType.NEW_TRADE,
            user_id=maker_order.user_id,
            related_id=maker_order.id,
            instrument_id=ctx.instrument_id,
            details={
                "quantity": quantity,
                "price": price,
                "role": LiquidityRole.MAKER.value,
            },
        )

    def _log_fill_event(self, order: Order, price: float, instrument_id: str) -> None:
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
            etype,
            user_id=order.user_id,
            related_id=order.id,
            instrument_id=instrument_id,
            details=ev_details,
        )
