# import jinja2
# from jinja2 import Jin

# FA
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Local
import config
from tests.test_config import *
from exceptions import DoesNotExist, InvalidError, DuplicateError
from middleware import RateLimitMiddleware
from routes.accounts import accounts
from routes.stream import stream


app = FastAPI()
app.add_middleware(RateLimitMiddleware)

app.mount("/static", StaticFiles(directory='static'), name="static")
templates = Jinja2Templates(directory='templates')

# Routers
app.include_router(accounts)
app.include_router(stream)


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


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name='index.html'
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app")