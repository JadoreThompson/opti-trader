from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config import CASH_BALANCE_HKEY, REDIS_CLIENT_ASYNC
from db_models import Users
from server.middleware import verify_jwt
from server.typing import JWTPayload
from server.utils import set_cookie
from server.utils.auth import generate_jwt_token
from server.utils.db import depends_db_session
from utils.utils import get_datetime, get_default_cash_balance
from .models import UserCreate


route = APIRouter(prefix="/auth", tags=["auth"])


@route.post("/login")
async def login_user(
    body: UserCreate,
    db_sess: AsyncSession = Depends(depends_db_session),
):
    result = await db_sess.execute(select(Users).where(Users.username == body.username))
    user = result.scalar_one_or_none()
    if user is None or user.password != body.password:
        return JSONResponse(status_code=401, content={"error": "Invalid credentials"})

    rsp = JSONResponse(content={"message": "Logged in successfully."})
    return set_cookie(user.user_id, rsp)


@route.post("/register")
async def register_user(
    body: UserCreate,
    db_sess: AsyncSession = Depends(depends_db_session),
):
    result = await db_sess.execute(select(Users).where(Users.username == body.username))
    if result.scalar_one_or_none():
        return JSONResponse(
            status_code=409, content={"error": "Username already registered"}
        )

    res = await db_sess.execute(
        insert(Users).values(**body.model_dump()).returning(Users.user_id)
    )
    user_id = res.scalar()

    await db_sess.commit()

    # Setting for engine
    await REDIS_CLIENT_ASYNC.hset(
        CASH_BALANCE_HKEY, str(user_id), get_default_cash_balance()
    )

    rsp = JSONResponse(status_code=200, content={"message": "Registered successfully."})
    return set_cookie(user_id, rsp)


@route.get("/me")
async def get_current_user(jwt_payload: JWTPayload = Depends(verify_jwt)):
    pass


@route.get("/me-id")
async def get_current_user_id(jwt_payload: JWTPayload = Depends(verify_jwt)):
    return {"user_id": jwt_payload.sub}


@route.get(
    "/access-token",
    summary="Returns a websocket token to be used to connect to the /ws/orders websocket for order updates",
)
async def get_access_token(jwt: JWTPayload = Depends(verify_jwt)):
    token = generate_jwt_token(
        sub=jwt.sub, exp=get_datetime() + timedelta(minutes=5)
    )
    return {"access_token": token}
