from threading import Thread

# Local
from trading_engine.spot import run as run_matching_engine

threads = [
    Thread(target=run_matching_engine, daemon=True),
]

for thread in threads:
    thread.start()
    
for thread in threads:
    thread.join()
