import argon2
from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import insert, select

from config import PH
from db_models import Users
from utils.db import get_db_session
from .models import LoginCredentials, RegisterCredentials
from ...middleware import generate_token
from ...config import COOKIE_KEY

auth = APIRouter(prefix="/auth", tags=["auth"])

@auth.post("/register")
async def register(body: RegisterCredentials) -> None:
    body.password = PH.hash(body.password)
    async with get_db_session() as sess:
        res = await sess.execute(
            insert(Users)
            .values(body.model_dump())
            .returning(Users)
        )
        user: Users = res.scalar()
        await sess.commit()
        
    resp = Response()
    resp.set_cookie(
        COOKIE_KEY, 
        generate_token({ 
            'sub':  user.username,
            'em': user.email,
        }), 
        # secure=True
    )
    return resp


@auth.post('/login')
async def login(body: LoginCredentials) -> None:
    print(body.model_dump())
    async with get_db_session() as sess:
        res = await sess.execute(
            select(Users)
            .where(Users.email == body.email)
        )
        user: Users = res.scalar()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    try:
        print("Passwords: ", user.password, body.password)
        PH.verify(user.password, body.password)
    except argon2.exceptions.VerifyMismatchError:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    resp = Response()
    resp.set_cookie(
        COOKIE_KEY, 
        generate_token({ 
            'sub':  user.username,
            'em': user.email,
        }), 
        # secure=True
    )
    return resp