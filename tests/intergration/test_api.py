import asyncio
import random

from typing import Optional
from faker import Faker
from httpx import AsyncClient, Cookies

from enums import MarketType, OrderType, Side
from ..config import BASE_URL


fkr = Faker()

async def test_user_creation() -> tuple[AsyncClient, int, Cookies]:
    sess = AsyncClient()
    
    payload = {
        "username": fkr.first_name(),
        "email": fkr.email(),
        "password": fkr.word(),
    }

    rsp = await sess.post(BASE_URL + "/auth/register", json=payload)
    return sess, rsp.status_code, rsp.cookies


async def test_order_creation(quantity: int = 10, delay: float = None) -> list[list[int, Optional[str]]]:
    randnum = lambda: round(random.random() * 100, 2)
    rtn_value: list[list[int, Optional[str]]] = []

    sess, _, cookies = await test_user_creation()

    for _ in range(quantity):
        await asyncio.sleep(delay or randnum())
        order_type = random.choice([OrderType.LIMIT, OrderType.MARKET])

        payload = {
            "quantity": random.randint(1, 50),
            "instrument": "BTCUSD",
            "market_type": MarketType.FUTURES,
            "order_type": order_type,
            "side": random.choice([Side.BUY, Side.SELL]),
            "take_profit": random.choice([randnum(), None]),
            "stop_loss": random.choice([randnum(), None]),
        }

        if order_type == OrderType.LIMIT:
            payload["limit_price"] = randnum()

        rsp = await sess.post(
            BASE_URL + "/order/",
            json=payload,
            cookies=cookies,
        )
        
        val = [rsp.status_code]
        if not rsp.is_success:
            val.append(rsp.json()['detail'])
        rtn_value.append(val)

    await sess.aclose()
    return rtn_value