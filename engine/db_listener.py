import asyncpg
import asyncio
import json
import logging

from collections import deque

# Local
from config import LOG_FOLDER
from utils.db import delete_from_internal_cache


logger = logging.getLogger(__name__)

class DBListener:
    _db_update_queue = asyncio.Queue()
    _order_creation_queue = deque()
    _channels = set({'orders', 'active_orders'})
    
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        
    @property
    def dsn(self):
        return self._dsn
        
    def _order_update_handler(self, conn, pid, channel, payload) -> None:
        if isinstance(payload, str):
            payload = json.loads(payload)
        
        self._db_update_queue.put_nowait(payload['user_id'])
    
    async def _process_update_notifications(self) -> None:
        logger.info('Waiting for messages')
        while True:
            try:
                user_id = self._db_update_queue.get_nowait()            
                if user_id:
                    delete_from_internal_cache(user_id, list(self._channels))
                    self._db_update_queue.task_done()
            except asyncio.queues.QueueEmpty:
                pass
            except Exception as e:
                logger.error(f'{type(e)} - {str(e)}')
                pass
            finally:
                await asyncio.sleep(0.01)
                
    def _order_creation_handler(self, conn, pid, channel, payload) -> None:
        if isinstance(payload, str):
            payload = json.loads(payload)
        
        if isinstance(payload, dict):
            self._order_creation_queue.append(payload)
        
    async def _process_order_creation_notifications(self) -> None:
        while True:
            try:
                item = self._order_creation_queue.popleft()
                print(item)
            except IndexError:
                pass
            except Exception as e:
                print(type(e), str(e))
                
            await asyncio.sleep(0.001)

    async def start(self):
        db_url = self.dsn.replace('+asyncpg', '')
        
        try:
            self._conn = await asyncpg.connect(dsn=db_url)
            await self._conn.add_listener('order_change', self._order_update_handler),
            await self._conn.add_listener('new_order', self._order_creation_handler),    
                      
            await asyncio.gather(*[
                self._process_update_notifications(),
                self._process_order_creation_notifications()
            ])
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
        finally:
            # Cleanup
            if hasattr(self, 'conn'):
                await self._conn.remove_listener('order_change', self._order_update_handler)
                await self._conn.close()
