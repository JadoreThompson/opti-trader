import argon2
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from config import DB_LOCK, PH
from db_models import Users
from utils.db import get_db_session
from .models import LoginCredentials, RegisterCredentials
from ...middleware import JWT, generate_jwt_token, verify_jwt_http
from ...config import JWT_ALIAS

auth = APIRouter(prefix="/auth", tags=["auth"])


@auth.post("/register")
async def register(body: RegisterCredentials) -> None:
    body.password = PH.hash(body.password)

    try:
        async with DB_LOCK:
            async with get_db_session() as sess:
                res = await sess.execute(
                    insert(Users)
                    .values(**body.model_dump(), balance=10_000_000)
                    .returning(Users)
                )
                user: Users = res.scalar()
                await sess.commit()
            resp = Response()
            resp.set_cookie(
                JWT_ALIAS,
                generate_jwt_token(
                    {
                        "sub": str(user.user_id),
                        "em": user.email,
                        "username": user.username,
                    }
                ),
                httponly=True,
                # secure=True
            )
            return resp
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Credentials already exist")


@auth.post("/login")
async def login(body: LoginCredentials) -> None:
    async with DB_LOCK:
        async with get_db_session() as sess:
            res = await sess.execute(select(Users).where(Users.email == body.email))
            user: Users = res.scalar()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    try:
        PH.verify(user.password, body.password)
    except argon2.exceptions.VerifyMismatchError:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    resp = Response()
    resp.set_cookie(
        JWT_ALIAS,
        generate_jwt_token(
            {
                "sub": str(user.user_id),
                "em": user.email,
                "username": user.username,
            }
        ),
        httponly=True,
        # secure=True
    )
    return resp


@auth.get("/verify-token")
async def verify_token(jwt: JWT = Depends(verify_jwt_http)):
    pass


@auth.get("/remove-token")
async def remove_token(jwt: JWT = Depends(verify_jwt_http)):
    res = Response()
    res.delete_cookie(JWT_ALIAS)
    return res
