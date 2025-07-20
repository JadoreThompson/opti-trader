from pprint import pprint
from fastapi import FastAPI, HTTPException, Request
from .exc import JWTError
from .routes import auth_route, order_route

app = FastAPI()


app.include_router(auth_route)
app.include_router(order_route)


@app.exception_handler(JWTError)
async def jwt_error_hanlder(req: Request, exc: JWTError):
    raise HTTPException(status_code=401, detail=str(exc))
