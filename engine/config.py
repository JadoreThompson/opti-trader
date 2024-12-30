import os
import asyncio
import logging
import multiprocessing
from dotenv import load_dotenv


logger = logging.getLogger(__name__)


load_dotenv()
REDIS_HOST = os.getenv('REDIS_HOST')
QUEUE = multiprocessing.Queue()