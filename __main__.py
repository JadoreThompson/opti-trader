import configparser
import multiprocessing
import os
import uvicorn
from urllib.parse import quote


def run_server(queue: multiprocessing.Queue) -> None:
    from api import config
    config.FUTURES_QUEUE = queue
    
    uvicorn.run(
        "api.app:app", 
        host="0.0.0.0", 
        port=8000, 
        # reload=True
    )


def run_engine(queue: multiprocessing.Queue) -> None:
    from engine.futures import FuturesEngine
    engine = FuturesEngine(queue)
    engine.run()


def main():
    queue = multiprocessing.Queue()
    ps = [
        multiprocessing.Process(target=run_server, args=(queue,), name="server"),
        multiprocessing.Process(target=run_engine, args=(queue,), name="engine"),
    ]
    
    for p in ps:
        p.start()

    try:
        while True:
            for p in ps:
                if not p.is_alive():
                    raise Exception(f"{p.name} has died")
    except (Exception, KeyboardInterrupt) as e:
        print(str(e))
        print("Terminating processes")
        
        for p in ps:
            p.terminate()
            p.join()
            print(f"Terminated {p.name}")
                

if __name__ == "__main__":
    main()