# FA
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

# Local
from exceptions import DoesNotExist, InvalidError, DuplicateError, InvalidAction
from middleware import RateLimitMiddleware
from routes.portfolio import portfolio
from routes.accounts import accounts
from routes.stream import stream
from routes.instruments import instruments
from routes.leaderboard import leaderboard


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
            "http://127.0.0.1:8000",
            "http://localhost:5173",
        ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
app.add_middleware(RateLimitMiddleware)


# Routers
# ^^^^^^^
app.include_router(accounts)
app.include_router(portfolio)
app.include_router(stream)
app.include_router(instruments)
app.include_router(leaderboard)


"""Exception handlers"""
@app.exception_handler(DoesNotExist)
async def does_not_exist_handler(r: Request, e: DoesNotExist):
    return JSONResponse(status_code=404, content={'error': e.message})


@app.exception_handler(InvalidError)
async def does_not_exist_handler(r: Request, e: InvalidError):
    return JSONResponse(status_code=400, content={'error': e.message})


@app.exception_handler(DuplicateError)
async def does_not_exist_handler(r: Request, e: DuplicateError):
    return JSONResponse(status_code=409, content={'error': e.message})


@app.exception_handler(InvalidAction)
async def invalid_action_handler(r: Request, e: InvalidAction):
    return JSONResponse(status_code=401, content={'error': e.message})


@app.exception_handler(RequestValidationError)
async def validation_handler(r: Request, e: RequestValidationError):
    return JSONResponse(status_code=400, content={'error': e._errors[0]['msg']})

    
import asyncio
import logging
from engine.db_listener import main as db_listener
from engine.matching_engine import run as matching_engine

logger = logging.getLogger(__name__)
logging.basicConfig(filename="app.log", level=logging.INFO)

def db_listener_wrapper() -> None:
    asyncio.run(db_listener())

def uvicorn_wrapper() -> None:
    uvicorn.run("app:app", port=8000, host='0.0.0.0', ws_ping_interval=3000.0, ws_ping_timeout=100.0)
    

if __name__ == "__main__":
    import config, engine
    import uvicorn
    import threading
    import sys
    
    try:
        threads = [
            threading.Thread(target=db_listener_wrapper, daemon=True),
            threading.Thread(target=uvicorn_wrapper, daemon=True),
            threading.Thread(target=matching_engine, daemon=True),
        ]
        
        for thread in threads:
            logger.info(f'{thread.name} started')
            thread.start()
            
        while True:
            for thread in threads:
                thread.join(timeout=0.1)
            
                if not thread.is_alive():
                    raise KeyboardInterrupt
    except KeyboardInterrupt:
        sys.exit(0)
        