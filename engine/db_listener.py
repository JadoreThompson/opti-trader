import asyncpg
import asyncio
import json
import logging

from collections import deque

# Local
from utils.db import delete_from_internal_cache


logger = logging.getLogger(__name__)

class DBListener:
    _queue = asyncio.Queue()
    _order_creation_queue = deque()
    _channels = set({'orders', 'active_orders'})
    
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        
    @property
    def dsn(self):
        return self._dsn
        
    def _handler(self, conn, pid, channel, payload) -> None:
        if isinstance(payload, str):
            payload = json.loads(payload)
        
        self._queue.put_nowait(payload['user_id'])
    
    async def _process_update_notifications(self) -> None:
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
            self._conn = await asyncpg.connect(dsn=db_url)
            await self._conn.add_listener('order_change', self._handler),   
            await self._process_update_notifications(),
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
        finally:
            # Cleanup
            if hasattr(self, 'conn'):
                await self._conn.remove_listener('order_change', self._handler)
                await self._conn.close()
