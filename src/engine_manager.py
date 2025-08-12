import time
from multiprocessing import Process, Queue
from multiprocessing.queues import Queue as MPQueue

from engine import SpotEngine
from event_handler import EventHandler
from utils.db import get_db_session_sync

# Global queues for communication between the API and the engine
command_queue: MPQueue = Queue()
event_queue: MPQueue = Queue()

engine_process: Process | None = None


def run_engine():
    """
    Target function for the engine process.
    Initializes and runs the matching engine.
    """
    print("[INFO] Initializing engine...")
    instrument_ids = ["BTC-USD", "ETH-USD"]  # Can be loaded from DB
    engine = SpotEngine(instrument_ids=instrument_ids)
    
    # Set the event logger queue so the engine can publish events
    engine._ctxs["BTC-USD"].engine.EventLogger.queue = event_queue
    engine._ctxs["ETH-USD"].engine.EventLogger.queue = event_queue

    print("[INFO] Engine started. Listening for commands...")
    while True:
        if not command_queue.empty():
            command = command_queue.get()
            engine.process_command(command)
        else:
            # Prevent busy-waiting
            time.sleep(0.001)


def event_processor():
    """
    Target function for the event processing loop.
    This runs in the main server process (as a background task)
    to process events from the engine.
    """
    print("[INFO] Event processor started. Listening for events...")
    from server.websockets.manager import websocket_manager
    
    event_handler = EventHandler()
    while True:
        if not event_queue.empty():
            event = event_queue.get()
            
            # Persist event to DB
            with get_db_session_sync() as session:
                event_handler.process_event(session, event)
            
            # Broadcast to websockets
            websocket_manager.process_event(event)
        else:
            time.sleep(0.001)


def start_engine():
    """Starts the matching engine in a separate process."""
    global engine_process
    if engine_process is None or not engine_process.is_alive():
        engine_process = Process(target=run_engine)
        engine_process.start()
        print("[INFO] Matching engine process started.")


def stop_engine():
    """Stops the matching engine process."""
    global engine_process
    if engine_process and engine_process.is_alive():
        engine_process.terminate()
        engine_process.join()
        engine_process = None
        print("[INFO] Matching engine process stopped.")