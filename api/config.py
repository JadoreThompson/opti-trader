import argon2
import multiprocessing
from datetime import timedelta

FUTURES_QUEUE: multiprocessing.Queue = None

COOKIE_KEY = 'my-cookie-key'
COOKIE_EXP = timedelta(days=1000)
COOKIE_ALGO = 'HS256'
COOKIE_SECRET_KEY = 'secret'