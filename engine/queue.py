class Queue:
    def __init__(self) -> None:
        self._items: list = []
        
    
    async def put(self, item: any) -> None:
        self._items.append(item)

    async def get(self) -> any:
        try:
            return self._items.pop(-1)
        except IndexError:
            while True:
                try:
                    return self._items.pop(-1)
                except IndexError:
                    pass
        