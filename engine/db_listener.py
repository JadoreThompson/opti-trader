import asyncpg, asyncio, json, logging

# Local
from config import DB_URL
from utils.db import delete_from_internal_cache

logger = logging.getLogger(__name__)


class DBListener:
    def __init__(self, dsn: str, cache_channels: list = None) -> None:
        self.dsn = dsn
        self.queue = asyncio.Queue()
        self.channels = set({'orders', 'active_orders'})
        
        if cache_channels:
            for channel in self.channels:
                self.channels.add(channel)
                
        
    def handler(self, conn, pid, channel, payload) -> None:
        if isinstance(payload, str):
            payload = json.loads(payload)
        
        self.queue.put_nowait(payload['user_id'])
        
        
    async def process_notifications(self) -> None:
        logger.info('Waiting for messages')
        while True:
            try:
                user_id = self.queue.get_nowait()            
                if user_id:
                    delete_from_internal_cache(user_id, list(self.channels))
                    self.queue.task_done()
            except asyncio.queues.QueueEmpty:
                pass
            except Exception as e:
                print('db_listener - process notifications: ', type(e), str(e))
                pass
            finally:
                await asyncio.sleep(0.01)

    async def start(self):
        db_url = self.dsn.replace('+asyncpg', '')
        
        try:
            self.conn = await asyncpg.connect(dsn=db_url)
            await self.conn.add_listener('order_change', self.handler)
            await self.process_notifications()
        except Exception as e:
            logger.error(f'{e}')
        finally:
            # Cleanup
            if hasattr(self, 'conn'):
                await self.conn.remove_listener('order_change', self.handler)
                await self.conn.close()


async def main():
    global DB_URL
    listener = DBListener(DB_URL)
    await listener.start()


if __name__ == '__main__':
    asyncio.run(main()) 
