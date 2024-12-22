import redis
import redis.asyncio.connection
import os
from dotenv import load_dotenv


load_dotenv()

class AsyncRedisConnection(redis.asyncio.connection.Connection):
    def __init__(
        self, 
        *, 
        host: str = os.getenv('REDIS_HOST'), 
        port: str | int = 6379, 
        socket_keepalive: bool = False, 
        socket_keepalive_options: redis.asyncio.connection.Mapping[int, int | bytes] | None = None, 
        socket_type: int = 0, 
        **kwargs
    ):
        super().__init__(
            host=host, 
            port=port, 
            socket_keepalive=socket_keepalive, 
            socket_keepalive_options=socket_keepalive_options, 
            socket_type=socket_type, 
            **kwargs
        )


class SyncRedisConnection(redis.connection.Connection):
    def __init__(
        self,
        host=os.getenv('REDIS_HOST'), 
        port=6379,
        socket_keepalive=False,
        socket_keepalive_options=None,
        socket_type=0,
        **kwargs
    ):
        super().__init__(
            host,
            port,
            socket_keepalive,
            socket_keepalive_options,
            socket_type,
            **kwargs
        )
