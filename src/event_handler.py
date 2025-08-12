import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select

from db_models import Orders, Trades, Users, Transactions, Events, AssetBalances
from engine.models import Event
from enums import EventType, OrderStatus, Side, TransactionType, OrderType


class EventHandler:
    """
    Processes events emitted by the matching engine, persisting changes to the database
    and handling all bookkeeping and accounting for both cash and assets.
    """

    def __init__(self) -> None:
        self.handlers = {
            EventType.ORDER_PLACED: self._handle_generic_log,
            EventType.ORDER_PARTIALLY_FILLED: self._handle_order_status_update,
            EventType.ORDER_FILLED: self._handle_order_status_update,
            EventType.ORDER_CANCELLED: self._handle_order_cancelled,
            EventType.ORDER_MODIFIED: self._handle_order_modified,
            EventType.ORDER_MODIFY_REJECTED: self._handle_generic_log,
            EventType.NEW_TRADE: self._handle_new_trade,
        }

    def process_event(self, session: Session, event: Event) -> None:
        """
        Process a list of events from the engine. Each event is handled
        within its own atomic transaction.
        """
        handler = self.handlers.get(event.event_type)
        if not handler:
            return

        try:
            db_event = Events(
                event_type=event.event_type.value,
                user_id=event.user_id,
                related_id=event.related_id,
                details=json.dumps(event.details) if event.details else None,
            )
            session.add(db_event)

            handler(session, event)
            session.commit()
        except Exception as e:
            print(
                f"Error processing event {event.event_type.value} ({event.related_id}): {e}"
            )
            session.rollback()

    def _get_asset_balance(
        self, session: Session, user_id: UUID, instrument_id: str
    ) -> AssetBalances:
        """Helper to fetch or create an asset balance record."""
        stmt = select(AssetBalances).where(
            AssetBalances.user_id == user_id,
            AssetBalances.instrument_id == instrument_id,
        )
        asset_balance = session.execute(stmt).scalar_one_or_none()
        # if not asset_balance:
        #     asset_balance = AssetBalance(user_id=user_id, instrument_id=instrument_id)
        #     session.add(asset_balance)
        return asset_balance

    def _handle_order_status_update(self, session: Session, event: Event):
        order = session.get(Orders, event.related_id)
        if not order:
            return

        if event.event_type == EventType.ORDER_FILLED:
            order.status = OrderStatus.FILLED.value
        elif event.event_type == EventType.ORDER_PARTIALLY_FILLED:
            order.status = OrderStatus.PARTIALLY_FILLED.value

        session.add(order)

    def _handle_order_cancelled(self, session: Session, event: Event):
        order = session.get(Orders, event.related_id)
        if not order:
            return

        order.status = OrderStatus.CANCELLED.value
        user = session.get(Users, order.user_id)
        if not user:
            return

        unfilled_qty = Decimal(str(order.quantity)) - Decimal(
            str(order.executed_quantity)
        )

        if unfilled_qty <= 0:
            session.add(order)
            return

        if order.side == Side.BID.value:
            # Refund escrowed CASH for unfilled portion of a BUY order
            entry_price = self._get_entry_price(order)
            print("")
            print("Above")
            refund_amount = Decimal(str(entry_price)) * unfilled_qty
            print("Below")
            user.escrow_balance = float(
                Decimal(str(user.escrow_balance)) - refund_amount
            )

            refund_tx = Transactions(
                user_id=user.user_id,
                amount=float(refund_amount),
                type=TransactionType.ESCROW.value,
                related_id=str(order.order_id),
                balance=user.cash_balance,
            )
            session.add(refund_tx)
            session.add(user)

        elif order.side == Side.ASK.value:
            asset_balance = self._get_asset_balance(
                session, user.user_id, order.instrument_id
            )
            asset_balance.escrow_balance = float(
                Decimal(str(asset_balance.escrow_balance)) - unfilled_qty
            )
            # asset_balance.balance = float(
            #     Decimal(str(asset_balance.balance)) + unfilled_qty
            # )
            session.add(asset_balance)

        session.add(order)
        session.add(user)

    def _handle_order_modified(self, session: Session, event: Event) -> None:
        # A full implementation must also adjust cash/asset escrow.
        order = session.get(Orders, event.related_id)
        if not order:
            return

        new_price = event.details.get("price")
        if new_price is not None:
            if order.order_type == OrderType.LIMIT.value:
                order.limit_price = new_price
            elif order.order_type == OrderType.STOP.value:
                order.stop_price = new_price
            session.add(order)

    def _handle_generic_log(self, session: Session, event: Event) -> None:
        pass

    def _handle_new_trade(self, session: Session, event: Event) -> None:
        details = event.details
        order = session.get(Orders, event.related_id)
        user = session.get(Users, event.user_id)
        if not order or not user:
            raise ValueError("Could not find Order or User for trade.")

        trade_price = Decimal(str(details["price"]))
        trade_quantity = Decimal(str(details["quantity"]))
        trade_value = trade_price * trade_quantity

        new_trade = Trades(
            order_id=order.order_id,
            user_id=user.user_id,
            instrument_id=order.instrument_id,
            price=float(trade_price),
            quantity=float(trade_quantity),
            liquidity=details["role"],
        )
        session.add(new_trade)
        session.flush()

        # Order state
        old_exec_qty = Decimal(str(order.executed_quantity))
        old_avg_price = Decimal(str(order.avg_fill_price or "0.0"))
        new_exec_qty = old_exec_qty + trade_quantity
        order.executed_quantity = float(new_exec_qty)
        order.avg_fill_price = float(
            ((old_avg_price * old_exec_qty) + trade_value) / new_exec_qty
        )

        # Settle balances
        if order.side == Side.BID.value:
            # BUYER: Settle from cash escrow, receive assets.
            entry_price = self._get_entry_price(order)
            trade_escrow = Decimal(str(entry_price)) * trade_quantity
            user.escrow_balance = float(
                Decimal(str(user.escrow_balance)) - trade_escrow
            )
            user.cash_balance = float(Decimal(str(user.cash_balance)) - trade_escrow)

            asset_balance = self._get_asset_balance(
                session, user.user_id, order.instrument_id
            )
            asset_balance.balance = float(
                Decimal(str(asset_balance.balance)) + trade_quantity
            )
            session.add(asset_balance)

            new_transaction = Transactions(
                user_id=user.user_id,
                amount=float(-trade_value),
                type=TransactionType.TRADE.value,
                related_id=str(new_trade.trade_id),
                balance=user.cash_balance,
            )
        else:  # ASK order
            # SELLER: Settle from asset escrow, receive cash.
            asset_balance = self._get_asset_balance(
                session, user.user_id, order.instrument_id
            )
            asset_balance.escrow_balance = float(
                Decimal(str(asset_balance.escrow_balance)) - trade_quantity
            )
            asset_balance.balance = float(
                Decimal(str(asset_balance.balance)) - trade_quantity
            )
            session.add(asset_balance)

            user.cash_balance = float(Decimal(str(user.cash_balance)) + trade_value)

            new_transaction = Transactions(
                user_id=user.user_id,
                amount=float(trade_value),
                type=TransactionType.TRADE.value,
                related_id=str(new_trade.trade_id),
                balance=user.cash_balance,
            )

        session.add(order)
        session.add(user)
        session.add(new_transaction)

    def _get_entry_price(self, order: Orders) -> float:
        if order.order_type == OrderType.MARKET.value:
            return order.price
        elif order.order_type == OrderType.LIMIT.value:
            return order.limit_price
        return order.stop_price
