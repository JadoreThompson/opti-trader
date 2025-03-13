import json

from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy import select
from typing import Optional

from config import REDIS_CLIENT
from db_models import MarketData
from utils.db import get_db_session
from .models import Timeframe


async def fetch_market_data(instrument: str, ago: int) -> list[Optional[MarketData]]:
    async with get_db_session() as sess:
        res = await sess.execute(
            select(MarketData).where(
                (MarketData.instrument == instrument)
                & (
                    MarketData.time
                    > (datetime.now() - timedelta(minutes=ago)).timestamp()
                )
            )
        )
        return res.scalars().all()


def compress_market_data(tf: Timeframe, data: list[MarketData]) -> list[dict]:
    """
    Compresses the market data into a list of OHLC levels partitioned by the amount
    of seconds within the passed timeframe

    Args:
        tf (Timeframe)
        data (list[MarketData])

    Returns:
        list[dict]: OHLC levels
    """
    grouped_data = defaultdict(list)
    timeframe_seconds = tf.get_seconds()

    for entry in data:
        bucket = (entry.time // timeframe_seconds) * timeframe_seconds
        grouped_data[bucket].append(entry)

    return [
        {
            "open": entries[0].price,
            "high": max(e.price for e in entries),
            "low": min(e.price for e in entries),
            "close": entries[-1].price,
            "time": timestamp,
        }
        for timestamp, entries in sorted(grouped_data.items())
    ]


async def generate_ohlc(
    instrument: str, timeframe: Timeframe
) -> list[Optional[dict[str, float | int]]]:
    key = f"{instrument}.data"
    prev: Optional[bytes] = await REDIS_CLIENT.hget(key, timeframe.value)

    if prev is None:
        return []
    
    prev_data: list[dict] = json.loads(prev)
    
    if not prev_data:
        return prev_data

    minutes_diff: int = (
        (datetime.now().timestamp() - prev_data[-1]["time"]) // timeframe.get_seconds()
    ) // timeframe.get_seconds()

    if minutes_diff:
        prev_data.extend(
            compress_market_data(
                timeframe, await fetch_market_data(instrument, minutes_diff)
            )
        )

        await REDIS_CLIENT.hset(
            key,
            timeframe.value,
            json.dumps(prev_data),
        )
        
    return prev_data
