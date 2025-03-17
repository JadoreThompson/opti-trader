import asyncio
import json
import random
import httpx

from faker import Faker
from typing import Any, Optional, AsyncGenerator, Dict, Tuple
from websockets.asyncio.client import connect

from enums import MarketType, OrderType, Side
from ..config import BASE_URL


randnum = lambda: round(random.random() * 100, 2)
fkr = Faker()


async def yield_order_ws(
    cookies: httpx.Cookies,
) -> AsyncGenerator[Dict[str, Any], None]:
    cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])

    async with connect(
        BASE_URL.replace("http", "ws") + "/order/ws",
        additional_headers={"Cookie": cookie_str},
    ) as ws:
        while True:
            msg = await ws.recv()
            yield json.loads(msg)


async def put_modify_order(
    order_id: str, session: httpx.AsyncClient, cookies: httpx.Cookies
) -> Tuple[int, Optional[Dict[str, Any]]]:
    """
    Performs a put requet to the modify order endpoint

    Args:
        session (httpx.AsyncClient)
        cookies (httpx.Cookies)

    Returns:
        status_code (int)
        response json (Optional[dict])
    """
    rsp = await session.put(
        BASE_URL + "/order/modify",
        json={
            "order_id": order_id,
            "take_profit": random.choice([randnum(), None]),
            "stop_loss": random.choice([randnum(), None]),
            "limit_price": random.choice([randnum(), None]),
        },
        cookies=cookies,
    )

    return (
        rsp.status_code,
        rsp.json() if not rsp.is_success else None,
    )


async def put_close_order(
    order_id: str,
    market_type: MarketType,
    session: httpx.AsyncClient,
    cookies: httpx.Cookies,
):
    """
    Performs a put request to close the order

    Args:
        order_id (str): The order id of the order being closed. Used for closing
            futures orders
        market_type (MarketType): The market type of the order. Used for closing Futures
            orders
        session (httpx.AsyncClient)
        cookies (httpx.Cookies)
    """
    if market_type == MarketType.FUTURES:
        payload = {
            "order_id": order_id,
        }
    else:
        payload = {
            "quantity": random.randint(1, 1000),
            "instrument": random.choice(["BTCUSD", "btcusd", "ethusd", "ltc"]),
        }

    rsp = await session.put(BASE_URL + "/order/close", json=payload, cookies=cookies)

    return (
        rsp.status_code,
        rsp.json() if not rsp.is_success else None,
    )


async def test_user_creation() -> tuple[httpx.AsyncClient, int, httpx.Cookies]:
    sess = httpx.AsyncClient()

    payload = {
        "username": fkr.first_name(),
        "email": fkr.email(),
        "password": fkr.word(),
    }
    print(payload)
    rsp = await sess.post(BASE_URL + "/auth/register", json=payload)
    return (
        sess,
        rsp.status_code,
        rsp.cookies,
    )


async def test_order_creation(
    num_orders: int = 10,
    delay: float = None,
    order_type: OrderType = None,
    market_type: MarketType = None,
    session: httpx.AsyncClient = None,
    cookies=None,
) -> list[list[int, Optional[str]]]:
    rtn_value: list[list[int, Optional[str]]] = []

    if session is None or cookies is None:
        session, _, cookies = await test_user_creation()

    await asyncio.sleep(0)

    for _ in range(num_orders):
        print(_)
        await asyncio.sleep(delay if delay is not None else randnum())

        if order_type is None:
            order_type = random.choice([OrderType.LIMIT, OrderType.MARKET])

        if market_type is None:
            market_type = random.choice([MarketType.FUTURES, MarketType.SPOT])

        payload = {
            "quantity": random.randint(1, 50),
            "instrument": "BTCUSD",
            "market_type": market_type,
            "order_type": order_type,
            "side": random.choice([Side.BUY, Side.SELL]),
            "take_profit": random.choice([randnum(), None]),
            "stop_loss": random.choice([randnum(), None]),
        }

        if order_type == OrderType.LIMIT:
            payload["limit_price"] = randnum()

        try:
            rsp = await session.post(
                BASE_URL + "/order/",
                json=payload,
                cookies=cookies,
            )

            val = [rsp.status_code]
            if not rsp.is_success:
                val.append(rsp.json()["detail"])
            rtn_value.append(val)
        except httpx.ReadTimeout:
            break

    await session.aclose()
    return rtn_value


async def test_order_modification(
    num_orders: int = 10,
    delay: float = 0.1,
) -> None:
    session, _, cookies = await test_user_creation()

    asyncio.create_task(
        test_order_creation(num_orders, delay, session=session, cookies=cookies)
    )

    async for msg in yield_order_ws(cookies):
        if "order_id" in msg["content"]:
            res = await put_modify_order(msg["content"]["order_id"], session, cookies)


async def test_order_close(
    num_orders: int = 10,
    delay: float = 0.1,
):
    session, _, cookies = await test_user_creation()

    asyncio.create_task(
        test_order_creation(num_orders, delay, session=session, cookies=cookies)
    )

    async for msg in yield_order_ws(cookies):
        if "order_id" in msg["content"]:
            res = await put_close_order(
                msg["content"]["order_id"],
                msg["content"]["market_type"],
                session,
                cookies,
            )


async def test_order_ws(): ...


async def test_price_ws():
    async with connect(
        BASE_URL.replace("http", "ws") + "/instrument/ws/?instrument=BTCUSD"
    ) as ws:
        while True:
            message = await ws.recv()
