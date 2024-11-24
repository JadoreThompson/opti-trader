import asyncio
import random
from faker import Faker
from uuid import UUID
import websockets

# Local
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from enums import OrderType
from config import PH
from db_models import Base, Users
from models import matching_engine_models
from utils.auth import create_jwt_token
from utils.db import get_db_session

# SA
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


# Envs
# ^^^^
faker = Faker()
SOCKET_URL = 'ws://127.0.0.1:8000/stream/trade'


# Funcs
# ^^^^^
async def generate_order_requests(quantity: int = 10) -> list:
    orders = []
    
    for _ in range(quantity):
        order_obj = random.choice([
            matching_engine_models.MarketOrder(
                ticker='APPL',
                quantity=random.randint(1, 5),
            ),
            
            # matching_engine_models.LimitOrder(
            #     ticker='APPL',
            #     quantity=random.randint(20, 50),
            #     limit_price=random.choice([n for n in range(100, 160, 10)])
            # )
        ])
        
        if isinstance(order_obj, matching_engine_models.MarketOrder):
            order_type = OrderType.MARKET
        elif isinstance(order_obj, matching_engine_models.LimitOrder):
            order_type = OrderType.LIMIT
            
        order_req = matching_engine_models.OrderRequest(
            type=order_type, 
            market_order=order_obj if order_type == OrderType.MARKET else None,
            limit_order=order_obj if order_type == OrderType.LIMIT else None
        )
        orders.append(order_req)
        
    return orders


# Tests
# ^^^^^
import json

async def test_create_user():
    async with get_db_session() as sess:
        user = await sess.execute(
            sa.insert(Users)
            .values(**{'email': faker.email(), 'password': PH.hash(faker.pystr())})
            .returning(Users)
        )
        await sess.commit()
        user = user.scalar()
        return user, create_jwt_token({'sub': str(user.user_id)})


async def test_socket(
    divider: int = None,
    close_quantity: int = 20,
    order_quantity: int = 100,
    **kwargs
):
    """
    Connects to socket and creates orders
    
    Args:
        divider (int, optional): How often to sell. Defaults to 5.
        quantity (int, optional): Quantity of shares to purchase. Defaults to 20.
    """
    _, token = await test_create_user()
    orders = await generate_order_requests(order_quantity)
    
    async with websockets.connect(SOCKET_URL) as socket:
        await socket.send(json.dumps({'token': token}))
        m = await socket.recv()
        print('Signing Message: ', m)
        
        for i in range(len(orders)):
            await asyncio.sleep(0.1)
            print(f"{kwargs.get('name', None)} - ", i)
            await socket.send(json.dumps(orders[i].model_dump()))
            
            if divider and i > 0:
                if i % divider == 0:
                    await socket.send(json.dumps({
                        'type': OrderType.CLOSE,
                        'close_order': {
                            'quantity': close_quantity,
                            'ticker': 'APPL'
                        }
                    }))

async def main():
    await asyncio.gather(*[
        test_socket(divider=2, close_quantity=10, order_quantity=1000, name='seller'),
        test_socket(name='buyer', divider=3, order_quantity=500, close_quantity=10)
    ])


asyncio.run(main())
