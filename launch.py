from threading import Thread

# Local
import tests.test_config
from engine.matching_engine import run as run_matching_engine
from tests.websocket_test import start as socket_test
from engine.price_scanner import run as run_price

threads = [
    Thread(target=run_price, daemon=True),
    Thread(target=run_matching_engine, daemon=True),
    Thread(target=socket_test, daemon=True)
]

for thread in threads:
    thread.start()
    
for thread in threads:
    thread.join()
