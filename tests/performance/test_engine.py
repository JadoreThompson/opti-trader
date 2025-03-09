import asyncio
from websockets.asyncio.client import connect
from httpx import Cookies
from ..config import BASE_URL
from ..intergration.test_api import test_user_creation, test_order_creation


async def connect_to_ws(cookies) -> None:
    async with connect(
        BASE_URL.replace("http", "ws") + "/order/ws/",
        additional_headers={"Cookies": cookies},
    ) as ws:
        while True:
            m = await ws.recv()
            print(m)
    ...


async def test_throughput(quantity: int = 1) -> None:
    session, _, cookies = await test_user_creation()
    funcs = []
    # print(dict(cookies))

    for _ in range(quantity):
        funcs.append(test_order_creation(10_000, 0.1, session=session, cookies=cookies))
        print(" ".join([f"{"=".join(item)};" for item in dict(cookies).items()]))
        funcs.append(
            connect_to_ws(
                " ".join([f"{"=".join(item)};" for item in dict(cookies).items()])
            )
        )

    await asyncio.gather(*funcs)
