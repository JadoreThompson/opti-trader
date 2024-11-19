import redis
import redis.asyncio.connection
import os
from dotenv import load_dotenv


load_dotenv()

class RedisConnection(redis.asyncio.connection.Connection):
    def __init__(self, *, host: str = os.getenv('REDIS_HOST'), port: str | int = 6379, socket_keepalive: bool = False, socket_keepalive_options: redis.asyncio.connection.Mapping[int, int | bytes] | None = None, socket_type: int = 0, **kwargs):
        super().__init__(host=host, port=port, socket_keepalive=socket_keepalive, socket_keepalive_options=socket_keepalive_options, socket_type=socket_type, **kwargs)