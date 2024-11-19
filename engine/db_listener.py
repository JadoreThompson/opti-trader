import asyncpg
import asyncio
import json

# Local
from config import DB_URL
from utils.db import delete_from_internal_cache


class DBListener:
    def __init__(self, dsn: str, cache_channels: list = None) -> None:
        self.dsn = dsn
        self.queue = asyncio.Queue()
        self.channels = set({'orders', 'active_orders'})
        
        if cache_channels:
            for channel in self.channels:
                self.channels.add(channel)
                
        
    async def handler(self, conn, pid, channel, payload) -> None:
        if isinstance(payload, str):
            payload = json.loads(payload)
        
        await self.queue.put(payload['user_id'])
        await asyncio.sleep(0.01)
        
        
    async def process_notifications(self) -> None:
        print('Waiting for DB Notifications...')
        while True:
            user_id = await self.queue.get()
            await delete_from_internal_cache(user_id, list(self.channels))


    async def start(self):
        db_url = self.dsn.replace('+asyncpg', '')
        
        try:
            self.conn = await asyncpg.connect(dsn=db_url)
            await self.conn.add_listener('order_change', self.handler)
            await self.process_notifications()
        except Exception as e:
            print(f"[DB Listener][Start Function] Error: {e}")
        finally:
            # Cleanup
            if hasattr(self, 'conn'):
                await self.conn.remove_listener('order_change', self.handler)
                await self.conn.close()


async def main():
    global DB_URL
    listener = DBListener(DB_URL)
    await listener.start()
