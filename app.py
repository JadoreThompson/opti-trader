# FA
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Local
import config
from tests.test_config import *
from exceptions import DoesNotExist, InvalidError, DuplicateError, InvalidAction
from middleware import RateLimitMiddleware
from routes.portfolio import portfolio
from routes.accounts import accounts
from routes.stream import stream
from routes.instruments import instrument


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

app.mount("/static", StaticFiles(directory='static'), name="static")
templates = Jinja2Templates(directory='templates')


# Routers
app.include_router(accounts)
app.include_router(portfolio)
app.include_router(stream)
app.include_router(instrument)

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
    


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name='index.html'
    )


from engine.db_listener import main as db_listener


def db_listener_wrapper() -> None:
    asyncio.run(db_listener())

def uvicorn_wrapper() -> None:
    uvicorn.run("app:app", port=8000)


if __name__ == "__main__":
    import uvicorn
    import threading
    import sys
    
    try:
        threads = [
            threading.Thread(target=db_listener_wrapper, daemon=True),
            threading.Thread(target=uvicorn_wrapper, daemon=True),
        ]
        
        for thread in threads:
            thread.start()
            
        while True:
            for thread in threads:
                thread.join(timeout=0.1)
            
                if not thread.is_alive():
                    print(f"Thread: {thread.name} died")
    except KeyboardInterrupt:
        sys.exit(0)