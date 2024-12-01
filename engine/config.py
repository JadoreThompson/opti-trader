import os, asyncio, logging
from ._queue import Queue
from dotenv import load_dotenv
from collections import defaultdict, deque


logger = logging.getLogger(__name__)


load_dotenv()
REDIS_HOST = os.getenv('REDIS_HOST')

QUEUE = asyncio.Queue()
# QUEUE: Queue = Queue()

TICKER = 'APPL'

ASKS = defaultdict(lambda: defaultdict(deque))
ASKS[TICKER] = defaultdict(deque)
ASK_LEVELS = {key: ASKS[key].keys() for key in ASKS}

BIDS = defaultdict(lambda: defaultdict(deque))
BIDS[TICKER] = defaultdict(deque)
BIDS_LEVELS = {key: BIDS[key].keys() for key in BIDS}
"""
{
    ticker: {
        price: [_Order, ...]
    }
}
"""

logger.info('Hi')