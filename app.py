# FA
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

# Local
from exceptions import DoesNotExist, DuplicateError, InvalidAction
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


# Exception handlers
# ^^^^^^^^^^^^^^^^^^^
@app.exception_handler(DoesNotExist)
async def does_not_exist_handler(r: Request, e: DoesNotExist):
    return JSONResponse(status_code=404, content={'error': e.message})


@app.exception_handler(DuplicateError)
async def does_not_exist_handler(r: Request, e: DuplicateError):
    return JSONResponse(status_code=409, content={'error': e.message})


@app.exception_handler(InvalidAction)
async def invalid_action_handler(r: Request, e: InvalidAction):
    return JSONResponse(status_code=401, content={'error': e.message})


@app.exception_handler(RequestValidationError)
async def validation_handler(r: Request, e: RequestValidationError):
    return JSONResponse(status_code=400, content={'error': e._errors[0]['msg'].replace('Value error, ', '')})
        