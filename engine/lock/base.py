from redis.asyncio import Redis

class LockBase:
    def __init__(self, client: Redis, key) -> None:
        self._key = key
        self._current_key = f"{self._key}.current"
        self._broadcast_key = f"{self._key}.broadcast"
        self._receiver_key = f"{self._key}.live"
        self._client = client