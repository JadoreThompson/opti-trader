import asyncio
from .intergration.test_api import test_order_creation


async def test() -> None:
    await asyncio.gather(*[test_order_creation(100_000, 0.1) for _ in range(3)])


if __name__ == "__main__":
    asyncio.run(test())
