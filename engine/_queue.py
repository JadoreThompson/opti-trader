from asyncio import Lock
from uuid import uuid4
from collections import deque


# TODO: Research a lighter UUID
class Queue:
    def __init__(self) -> None:
        self._lock = Lock()
        self._items: dict[str, any] = {}
        self._item_ids: list = []
        self._get_counter: int = -1
    
    
    async def put(self, item: any) -> None:
        try:
            item_id = str(uuid4())
            self._items[item_id] = item
            self._item_ids.append(item_id)
        except Exception as e:
            print('Put: ', type(e), str(e))


    async def get(self):
        async with self._lock:
            try:
                if not self._item_ids:
                    return
                
                next_index = self._get_counter + 1
                item_id = self._item_ids[next_index]
                
                if item_id in self._items:
                    self._get_counter = next_index
                    return self._items.pop(item_id)
            
            except IndexError:
                return
            except Exception as e:
                print('get: ', type(e), str(e))
            
        
        # try:
        #     if not self._items:
        #         return None            
        #     return self._items.popleft()
        # except IndexError: return None
        # except Exception as e: 
        #     print('Get: ', type(e), str(e))