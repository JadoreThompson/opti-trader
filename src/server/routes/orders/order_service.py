from enum import Enum
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import CASH_ESCROW_HKEY, REDIS_CLIENT_ASYNC, COMMAND_QUEUE
from db_models import AssetBalances, Instruments, Orders, Trades, Users
from enums import OrderStatus, OrderType, Side, StrategyType
from engine.models import (
    Command,
    CommandType,
    NewOCOOrder,
    NewOTOCOOrder,
    NewOTOOrder,
    NewSingleOrder,
)
from utils.utils import get_instrument_escrows_hkey
from .models import OCOOrderCreate, OTOCOOrderCreate, OTOOrderCreate, OrderCreate


class OrderService:

    @classmethod
    async def fetch_balance(cls, user_id: str | UUID, db_sess: AsyncSession) -> dict:
        res = await db_sess.execute(
            select(Users.cash_balance - Users.escrow_balance).where(
                Users.user_id == user_id
            )
        )
        available_balance = res.scalar()

        return {"available_balance": available_balance}

    @classmethod
    async def handle_escrow(
        cls, user_id, db_sess, instrument_id, quantity, price, side: Side
    ):
        if side == Side.BID:
            total_value = quantity * price
            res = await db_sess.execute(
                select(Users.cash_balance - Users.escrow_balance).where(
                    Users.user_id == user_id
                )
            )
            remaining_balance = res.scalar()

            if remaining_balance < total_value:
                raise ValueError("Invalid cash balance.")

            await db_sess.execute(
                update(Users)
                .where(Users.user_id == user_id)
                .values(escrow_balance=Users.escrow_balance + total_value)
            )

            await REDIS_CLIENT_ASYNC.hincrbyfloat(
                CASH_ESCROW_HKEY, user_id, total_value
            )
            return

        res = await db_sess.execute(
            select(AssetBalances.balance - AssetBalances.escrow_balance).where(
                AssetBalances.user_id == user_id,
                AssetBalances.instrument_id == instrument_id,
            )
        )
        remaining_balance = res.scalar()
        if remaining_balance is None or remaining_balance < quantity:
            raise ValueError("Invalid asset balance.")

        await db_sess.execute(
            update(AssetBalances)
            .where(
                AssetBalances.user_id == user_id,
                AssetBalances.instrument_id == instrument_id,
            )
            .values(escrow_balance=AssetBalances.escrow_balance + quantity)
        )
        await db_sess.flush()

        await REDIS_CLIENT_ASYNC.hincrbyfloat(
            get_instrument_escrows_hkey(instrument_id), user_id, quantity
        )

    @classmethod
    async def fetch_last_trade_price(cls, db_sess, instrument_id: str) -> float | None:
        res = await db_sess.execute(
            select(Trades.price)
            .where(Trades.instrument_id == instrument_id)
            .order_by(Trades.executed_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    @classmethod
    async def _create_order(
        cls, user_id: str, db_sess: AsyncSession, details: OrderCreate
    ) -> list[str]:
        order_data = details.model_dump()

        if details.order_type == OrderType.MARKET:
            res = await db_sess.execute(
                select(Trades.price)
                .where(Trades.instrument_id == details.instrument_id)
                .order_by(Trades.executed_at.desc())
                .limit(1)
            )
            price = res.scalar_one_or_none()

            if price is None:
                res = await db_sess.execute(
                    select(Instruments.starting_price)
                    .where(Instruments.instrument_id == details.instrument_id)
                )
                price = res.scalar_one()

            order_data["price"] = price
            await cls.handle_escrow(
                user_id,
                db_sess,
                details.instrument_id,
                details.quantity,
                order_data["price"],
                details.side,
            )


        res = await db_sess.execute(
            insert(Orders)
            .values(
                user_id=user_id,
                **{
                    k: (v.value if isinstance(v, Enum) else v)
                    for k, v in order_data.items()
                },
            )
            .returning(Orders)
        )
        order = res.scalar()
        await db_sess.flush()

        COMMAND_QUEUE.put_nowait(
            Command(
                command_type=CommandType.NEW_ORDER,
                data=NewSingleOrder(
                    strategy_type=StrategyType.SINGLE,
                    instrument_id=details.instrument_id,
                    order=order.dump_serialised(),
                ),
            )
        )
        return [str(order.order_id)]

    @classmethod
    async def _create_oco_order(
        cls, user_id, db_sess, details: OCOOrderCreate
    ) -> list[str]:
        db_orders = []
        instrument_id = details.legs[0].instrument_id
        for leg_details in details.legs:
            entry_price = leg_details.limit_price or leg_details.stop_price
            if entry_price is None:
                raise ValueError("OCO leg must have a limit_price or stop_price.")
            res = await db_sess.execute(
                insert(Orders)
                .values(
                    user_id=user_id,
                    **{
                        k: (v.value if isinstance(v, Enum) else v)
                        for k, v in leg_details.model_dump().items()
                    },
                )
                .returning(Orders)
            )
            db_orders.append(res.scalar())

        await db_sess.flush()

        COMMAND_QUEUE.put_nowait(
            Command(
                command_type=CommandType.NEW_ORDER,
                data=NewOCOOrder(
                    strategy_type=StrategyType.OCO,
                    instrument_id=instrument_id,
                    legs=[o.dump_serialised() for o in db_orders],
                ),
            )
        )
        return [str(o.order_id) for o in db_orders]

    @classmethod
    async def _create_oto_order(
        cls, user_id, db_sess, details: OTOOrderCreate
    ) -> list[str]:
        parent_details = details.parent
        instrument_id = parent_details.instrument_id
        if parent_details.order_type == OrderType.MARKET:
            entry_price = await cls.fetch_last_trade_price(db_sess, instrument_id)
            if entry_price is None:
                raise ValueError(
                    f"No last trade price for market order on {instrument_id}"
                )

        res = await db_sess.execute(
            insert(Orders)
            .values(
                user_id=user_id,
                **{
                    k: (v.value if isinstance(v, Enum) else v)
                    for k, v in parent_details.model_dump().items()
                },
            )
            .returning(Orders)
        )
        parent_order = res.scalar()

        child_details = details.child
        res = await db_sess.execute(
            insert(Orders)
            .values(
                user_id=user_id,
                **{
                    k: (v.value if isinstance(v, Enum) else v)
                    for k, v in child_details.model_dump().items()
                },
            )
            .returning(Orders)
        )
        child_order = res.scalar()
        await db_sess.flush()

        COMMAND_QUEUE.put_nowait(
            Command(
                command_type=CommandType.NEW_ORDER,
                data=NewOTOOrder(
                    strategy_type=StrategyType.OTO,
                    instrument_id=instrument_id,
                    parent=parent_order.dump_serialised(),
                    child=child_order.dump_serialised(),
                ),
            )
        )
        return [str(parent_order.order_id), str(child_order.order_id)]

    @classmethod
    async def _create_otoco_order(
        cls, user_id, db_sess, details: OTOCOOrderCreate
    ) -> list[str]:
        parent_details = details.parent
        instrument_id = parent_details.instrument_id
        if parent_details.order_type == OrderType.MARKET:
            entry_price = await cls.fetch_last_trade_price(db_sess, instrument_id)
            if entry_price is None:
                raise ValueError(
                    f"No last trade price for market order on {instrument_id}"
                )
            await cls.handle_escrow(
                user_id,
                db_sess,
                instrument_id,
                parent_details.quantity,
                entry_price,
                parent_details.side,
            )

        parent_res = await db_sess.execute(
            insert(Orders)
            .values(
                user_id=user_id,
                **{
                    k: (v.value if isinstance(v, Enum) else v)
                    for k, v in parent_details.model_dump().items()
                },
            )
            .returning(Orders)
        )
        parent_order = parent_res.scalar()

        oco_leg_orders = []
        for leg_details in details.oco_legs:
            res = await db_sess.execute(
                insert(Orders)
                .values(
                    user_id=user_id,
                    **{
                        k: (v.value if isinstance(v, Enum) else v)
                        for k, v in leg_details.model_dump().items()
                    },
                )
                .returning(Orders)
            )
            oco_leg_orders.append(res.scalar())

        await db_sess.flush()

        COMMAND_QUEUE.put_nowait(
            Command(
                command_type=CommandType.NEW_ORDER,
                data=NewOTOCOOrder(
                    strategy_type=StrategyType.OTOCO,
                    instrument_id=instrument_id,
                    parent=parent_order.dump_serialised(),
                    oco_legs=[o.dump_serialised() for o in oco_leg_orders],
                ),
            )
        )
        return [str(parent_order.order_id)] + [str(o.order_id) for o in oco_leg_orders]

    @classmethod
    async def create(cls, user_id: str, details, db_sess: AsyncSession) -> dict:
        """Public entry point to create any order type using a type-to-method map."""
        create_map = {
            OrderCreate: cls._create_order,
            OCOOrderCreate: cls._create_oco_order,
            OTOOrderCreate: cls._create_oto_order,
            OTOCOOrderCreate: cls._create_otoco_order,
        }

        creator = create_map.get(type(details))
        if not creator:
            raise ValueError(f"Unsupported order type: {type(details)}")

        order_ids = await creator(user_id, db_sess, details)
        balances = await cls.fetch_balance(user_id, db_sess)
        await db_sess.commit()
        return {"order_ids": order_ids, **balances}
