import multiprocessing
import os
from datetime import timedelta
from dotenv import load_dotenv
from config import BASE_PATH

load_dotenv(dotenv_path=os.path.join(BASE_PATH, '.env'))

FUTURES_QUEUE: multiprocessing.Queue = None

COOKIE_ALIAS = os.getenv("COOKIE_ALIAS")
COOKIE_ALGO = os.getenv("COOKIE_ALGO")
COOKIE_EXP = timedelta(days=1000)
COOKIE_SECRET_KEY = os.getenv("COOKIE_SECRET")
