import asyncio

from .performance.test_engine import test_throughput
from .intergration.test_api import test_order_creation


async def run_engine_throughput_test():
    await test_throughput()


async def run_order_test() -> None:
    await asyncio.gather(*[test_order_creation(100_000, 0.1) for _ in range(3)])


if __name__ == "__main__":
    asyncio.run(run_order_test())