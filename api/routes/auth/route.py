from fastapi import APIRouter, Response
from sqlalchemy import insert

from config import COOKIE_KEY
from db_models import Users
from utils.db import get_db_session
from .models import RegisterCredentials
from ...middleware import generate_token

auth = APIRouter(prefix="/auth", tags=["auth"])

@auth.post("/register")
async def register(body: RegisterCredentials):
    async with get_db_session() as sess:
        await sess.execute(
            insert(Users)
            .values(body.model_dump())
        )
        await sess.commit()
        
    res = Response()
    res.set_cookie(COOKIE_KEY)
    return res