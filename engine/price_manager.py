import asyncio

from r_mutex import LockClient

from config import REDIS_CLIENT

# IN CONSTRUCTION
class PriceManager:
    def __init__(self, lock: LockClient) -> None:
        """
        Args:
            lock (LockClient): Lock Client for the market_data table.
        """
        self._lock = lock
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(...)
    
    def append(self, price: str, instrument: str) -> None:
        ...

    async def update_price(self, price: float):
        self._current_price = price

    async def _publish_price(
        self, price: float, instrument: str
    ) -> None:
        await REDIS_CLIENT.set(f"{instrument}.price", price)
        await REDIS_CLIENT.publish(f"{instrument}.live", price)

        async with self._lock:
            async with get_db_session() as sess:
                await sess.execute(
                    insert(MarketData).values(
                        instrument=instrument,
                        instrument_id=self._instrument_id,
                        time=datetime.now().timestamp(),
                        price=price,
                    )
                )
                await sess.commit()
