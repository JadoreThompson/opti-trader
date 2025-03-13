import asyncio

from enums import MarketType
from .intergration.test_api import (
    test_order_close,
    test_order_creation,
    test_order_modification,
    test_user_creation,
)


async def run_create_user_test():
    await asyncio.gather(*[test_user_creation() for _ in range(1)])


async def run_order_creation_test() -> None:
    await asyncio.gather(
        *[
            test_order_creation(1_000_000, 0.1, market_type=MarketType.FUTURES)
            for _ in range(1)
        ]
    )


async def run_order_modification_test() -> None:
    await asyncio.gather(*[test_order_modification(100_000) for _ in range(3)])


async def run_order_close_test():
    await asyncio.gather(*[test_order_close(10_000) for _ in range(5)])


if __name__ == "__main__":
    asyncio.run(run_order_modification_test())
