import json
from config import REDIS_CLIENT
from .controllers import compress_market_data, fetch_market_data
from .models import Timeframe

async def cache_market_data(instrument: str) -> None:
    name = f"{instrument}.data"
    data = await fetch_market_data(instrument, 60 * 60 * 12)

    for tf in Timeframe:
        await REDIS_CLIENT.hset(
            name, tf.value, json.dumps(compress_market_data(tf, data))
        )
