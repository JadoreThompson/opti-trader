import os, asyncio
from .queue import Queue
from dotenv import load_dotenv
from collections import defaultdict


load_dotenv()
REDIS_HOST = os.getenv('REDIS_HOST')

# QUEUE: asyncio.Queue = asyncio.Queue()
QUEUE: Queue = Queue()

TICKER = 'APPL'

ASKS: dict[str, dict[float, list]] = defaultdict(dict)
ASKS[TICKER] = defaultdict(list)
ASK_LEVELS = {key: ASKS[key].keys() for key in ASKS}

BIDS: dict[str, dict[float, list]] = defaultdict(dict)
BIDS[TICKER] = defaultdict(list)
BIDS_LEVELS = {key: BIDS[key].keys() for key in BIDS}
"""
{
    ticker: {
        price: [_Order, ...]
    }
}
"""