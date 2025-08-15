import asyncio
from datetime import timedelta
import random
from uuid import uuid4
from db_models import Instruments, Orders, Trades, Users
from utils.db import get_db_session
from utils.utils import get_datetime


async def insert_trades(n: int = 10):
    async with get_db_session() as session:
        # ensure we have a user and an instrument
        user = Users(username="testuser2", password="secret")
        
        instrument = await session.get(Instruments, "BTC-USD")
        # instrument = Instruments(
        #     instrument_id="BTC-USD", symbol="BTC-USD", tick_size=0.01
        # )
        session.add_all([user, instrument])
        await session.flush()  # get IDs populated

        # make one parent order
        order = Orders(
            user_id=user.user_id,
            instrument_id=instrument.instrument_id,
            side="ask",
            order_type="market",
            quantity=1.0,
        )
        session.add(order)
        await session.flush()

        # now insert n trades
        trades = []
        base_price = 30000
        for i in range(n):
            trade = Trades(
                trade_id=uuid4(),
                order_id=order.order_id,
                user_id=user.user_id,
                instrument_id=instrument.instrument_id,
                price=base_price + random.uniform(-500, 500),
                quantity=random.uniform(0.01, 1.0),
                liquidity=random.choice(["MAKER", "TAKER"]),
                executed_at=get_datetime() - timedelta(minutes=i),
            )
            trades.append(trade)

        session.add_all(trades)
        await session.commit()
        print(f"Inserted {n} trades.")


async def main():
    # ensure tables exist
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)

    await insert_trades(50)


if __name__ == "__main__":
    asyncio.run(main())