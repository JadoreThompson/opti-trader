import jwt
import uuid

from datetime import datetime
from fastapi import HTTPException, Request
from typing import TypedDict
from .config import (
    COOKIE_ALGO, 
    COOKIE_EXP, 
    COOKIE_KEY, 
    COOKIE_SECRET_KEY
)

TOKENS: dict[uuid.UUID, dict]= {}

class JWT(TypedDict):
    sub: str # user_id
    em: str # email
    exp: datetime


def generate_token(payload: JWT) -> str:
    payload['exp'] = datetime.now() + COOKIE_EXP
    return jwt.encode(payload, COOKIE_SECRET_KEY, algorithm=COOKIE_ALGO)


def verify_cookie(req: Request) -> JWT:
    token: str | None = req.cookies.get(COOKIE_KEY, None)
    
    if token is None:
        raise HTTPException(status_code=401, detail="Unauthorised")
    
    try:
        return jwt.decode(token, COOKIE_SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")