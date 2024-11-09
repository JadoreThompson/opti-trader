import asyncio
import os
import random
import time
from collections import defaultdict
from datetime import datetime
from urllib.parse import quote
from uuid import uuid4
from faker import Faker

# SA
from sqlalchemy import insert, select, delete, NullPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# Local
from db_models import Base, Users, Orders
from enums import OrderType, _InternalOrderType

# DB_URL = "sqlite+aiosqlite:///:memory:"
# DB_ENGINE = create_async_engine(DB_URL)

DB_URL = \
    f"postgresql+asyncpg://{os.getenv("DB_USER")}:{quote(os.getenv('DB_PASSWORD'))}\
@{os.getenv("DB_HOST")}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
DB_ENGINE = create_async_engine(DB_URL, future=True, poolclass=NullPool)

faker = Faker()


def add_ask(price: float, quantity: float, user):
    """Add an ask order to the order book."""
    order_data = {
        "ticker": "BTC/USDT",
        "order_status": random.choice(["not_filled", "partially_filled"]),
        "quantity": quantity,
        "price": price,
        "limit_price": None,
        "stop_loss": None,
        "user_id": user,
        "order_type": random.choice(['close_order', 'market_order']),
        "take_profit": None,
    }
    return order_data



def add_bid(price: float, quantity: float, user):
    """Add a bid order to the order book."""
    order_data = {
        "ticker": "BTC/USDT",
        "order_status": random.choice(["not_filled", "partially_filled"]),
        "quantity": quantity,
        "price": price,
        "limit_price": None,
        "stop_loss": None,
        "user_id": user,
        "order_type": "market_order",
        "take_profit": None,
    }
    return order_data


def generate_fake_user(amount: int = 5) -> list[dict]:
    return [
        {
            "email": faker.email(),
            "password": faker.password()
         }
        for _ in range(amount)
    ]


async def generate_db() -> tuple:
    """
        - Deletes and re-creates the orders and users table in DB
        - Generates x amount of users and y amount of orders for each
            user

    :return: [bids, asks]
    """

    async with DB_ENGINE.begin() as conn:
        await conn.execute(delete(Orders))
        await conn.execute(delete(Users))

        await conn.execute(
            insert(Users)
            .values(generate_fake_user(5))
        )

        users = await conn.execute(select(Users.user_id))

        prices = [random.randint(100, 150) for _ in range(10)]

        for user in users.fetchall():
            bids = []
            asks = []

            for _ in range(100):
                bids.append(add_bid(random.choice(prices), random.randint(1000, 100000), user[0]))
                asks.append(add_ask(random.choice(prices), random.randint(1000, 100000), user[0]))

            bids.extend(asks)

            await conn.execute(
                insert(Orders)
                .values(bids)
            )


        return_bids = defaultdict(list)
        return_asks = defaultdict(list)

        result = await conn.execute(select(Orders))
        orders = result.fetchall()
        i = 0
        for order in orders:
            i += 1
            order = dict(order._mapping)
            order['internal_order_type'] = random.choice([item.value for item in _InternalOrderType])
            
            if order['created_at']:
                if i % 2 == 0:
                    return_bids[order['ticker']][order['price']].append([order['created_at'], order['quantity'], order])
                else:
                    return_asks[order['ticker']][order['price']].append([order['created_at'], order['quantity'], order])

        return return_bids, return_asks


def config():
    """
    Generates n users with n amount of bid and asks in an in-memory
    database
    :return:
    """
    return asyncio.run(generate_db())

# print(config())
