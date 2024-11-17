from threading import Thread

# Local
from config import DB_URL
import tests.test_config
from engine.matching_engine import run as run_matching_engine
from engine.db_listener import main as db_listener
from tests.websocket_test import start as socket_test
from engine.price_scanner import run as run_price

threads = [
    # Thread(target=run_price, daemon=True),
    Thread(target=run_matching_engine, daemon=True),
    # Thread(target=socket_test, daemon=True),
    Thread(target=db_listener, args=(DB_URL,), daemon=True),
]

for thread in threads:
    thread.start()
    
for thread in threads:
    thread.join()
