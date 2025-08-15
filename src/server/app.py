from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.exc import JWTError
from .routes import auth_route, instruments_route, orders_route, user_route
from .websockets.route import route as ws_route


app = FastAPI()


app.include_router(auth_route)
app.include_router(instruments_route)
app.include_router(orders_route)
app.include_router(user_route)
app.include_router(ws_route)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.exception_handler(JWTError)
async def jwt_error_hanlder(req: Request, exc: JWTError):
    return JSONResponse(status_code=403, content={"error": str(exc)})
