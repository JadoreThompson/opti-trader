import asyncpg, asyncio, json, logging

# Local
from config import LOG_FOLDER
from utils.db import delete_from_internal_cache


logger = logging.getLogger(__name__)

class DBListener:
    _queue = asyncio.Queue()
    _channels = set({'orders', 'active_orders'})
    
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        
    @property
    def dsn(self):
        return self._dsn
        
    def handler(self, conn, pid, channel, payload) -> None:
        if isinstance(payload, str):
            payload = json.loads(payload)
        
        self._queue.put_nowait(payload['user_id'])
        
    async def process_notifications(self) -> None:
        logger.info('Waiting for messages')
        while True:
            try:
                user_id = self._queue.get_nowait()            
                if user_id:
                    delete_from_internal_cache(user_id, list(self._channels))
                    self._queue.task_done()
            except asyncio.queues.QueueEmpty:
                pass
            except Exception as e:
                logger.error(f'{type(e)} - {str(e)}')
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
